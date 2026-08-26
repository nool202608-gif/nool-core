from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.errors import ConflictError, NotFoundError

from src.api.deps import get_db_session, require_role
from src.api.schemas.common import ListEnvelope
from src.api.schemas.homework import (
    AssignHomeworkIn,
    CreateHomeworkIn,
    HomeworkOut,
    HomeworkQuestionOut,
    UpdateHomeworkQuestionIn,
)
from src.api.schemas.roster import AssignmentTarget
from src.domain.models import (
    AssignmentTargetMode,
    Homework,
    HomeworkBloomDistribution,
    HomeworkDataset,
    HomeworkQuestion,
    HomeworkStatus,
    HomeworkTargetStudent,
    Role,
    School,
    SchoolClass,
    TestStatus,
    User,
    VoiceTest,
)
from src.repositories.lookups import get_homework_in_school
from src.services.bloom_defaults import resolve_bloom_targets
from src.services.content_generator import get_content_generator

router = APIRouter(prefix="/api/v1", tags=["homework"])


async def _serialize(session: AsyncSession, hw: Homework) -> HomeworkOut:
    datasets = await session.execute(
        select(HomeworkDataset.dataset_id).where(HomeworkDataset.homework_id == hw.id)
    )
    dataset_ids = [str(row[0]) for row in datasets.all()]

    distribution = await session.execute(
        select(HomeworkBloomDistribution).where(HomeworkBloomDistribution.homework_id == hw.id)
    )
    from src.api.schemas.bloom import BloomTarget

    bloom_distribution = [
        BloomTarget(level=d.bloom_level, value=d.value) for d in distribution.scalars().all()
    ]

    student_ids: list[str] | None = None
    if hw.target_mode == AssignmentTargetMode.SPECIFIC_STUDENTS:
        targets = await session.execute(
            select(HomeworkTargetStudent.student_id).where(HomeworkTargetStudent.homework_id == hw.id)
        )
        student_ids = [str(row[0]) for row in targets.all()]

    return HomeworkOut(
        id=str(hw.id),
        test_id=str(hw.test_id),
        class_id=str(hw.class_id),
        gap_topic=hw.gap_topic,
        gap_mastery_percent=hw.gap_mastery_percent,
        dataset_ids=dataset_ids,
        total_questions=hw.total_questions,
        difficulty=hw.difficulty,
        bloom_distribution=bloom_distribution,
        target=AssignmentTarget(mode=hw.target_mode, student_ids=student_ids),
        completion_window_hours=hw.completion_window_hours,
        status=hw.status,
        assigned_count=hw.assigned_count,
        completed_count=hw.completed_count,
    )


@router.get("/homework")
async def list_homework(
    user: User = Depends(require_role(Role.TEACHER)),
    session: AsyncSession = Depends(get_db_session),
) -> ListEnvelope[HomeworkOut]:
    result = await session.execute(
        select(Homework)
        .join(SchoolClass, SchoolClass.id == Homework.class_id)
        .where(SchoolClass.school_id == user.school_id)
    )
    items = [await _serialize(session, hw) for hw in result.scalars().all()]
    return ListEnvelope(items=items, total=len(items))


@router.get("/homework/{homework_id}")
async def get_homework(
    homework_id: str,
    user: User = Depends(require_role(Role.TEACHER)),
    session: AsyncSession = Depends(get_db_session),
) -> HomeworkOut:
    hw = await get_homework_in_school(session, homework_id, user.school_id)
    return await _serialize(session, hw)


@router.post("/homework", status_code=201, summary="Create (GENERATING)")
async def create_homework(
    body: CreateHomeworkIn,
    user: User = Depends(require_role(Role.TEACHER)),
    session: AsyncSession = Depends(get_db_session),
) -> HomeworkOut:
    test_result = await session.execute(
        select(VoiceTest)
        .join(SchoolClass, SchoolClass.id == VoiceTest.class_id)
        .where(VoiceTest.id == body.test_id, SchoolClass.school_id == user.school_id)
    )
    test = test_result.scalar_one_or_none()
    if test is None:
        raise NotFoundError(f'No Test with id "{body.test_id}" in your school.')
    if test.status != TestStatus.RESULTS_READY:
        raise ConflictError("Source Test isn't RESULTS_READY.")

    hw = Homework(
        test_id=test.id,
        class_id=test.class_id,
        gap_topic="",
        gap_mastery_percent=0,
        total_questions=body.total_questions,
        difficulty=body.difficulty,
        target_mode=AssignmentTargetMode.WHOLE_CLASS,
        status=HomeworkStatus.GENERATING,
    )
    session.add(hw)
    await session.flush()

    for dataset_id in body.dataset_ids:
        session.add(HomeworkDataset(homework_id=hw.id, dataset_id=dataset_id))
    school = await session.get(School, user.school_id)
    for target in resolve_bloom_targets(school, body.bloom_distribution):
        session.add(
            HomeworkBloomDistribution(homework_id=hw.id, bloom_level=target.level, value=target.value)
        )

    await session.commit()
    await session.refresh(hw)
    return await _serialize(session, hw)


@router.post("/homework/{homework_id}/generate")
async def generate_homework(
    homework_id: str,
    user: User = Depends(require_role(Role.TEACHER)),
    session: AsyncSession = Depends(get_db_session),
) -> HomeworkOut:
    hw = await get_homework_in_school(session, homework_id, user.school_id)

    distribution = await session.execute(
        select(HomeworkBloomDistribution).where(HomeworkBloomDistribution.homework_id == hw.id)
    )
    bloom_levels = [d.bloom_level for d in distribution.scalars().all()]

    generator = get_content_generator()
    questions = generator.generate_questions(
        topic=hw.gap_topic or "this topic", bloom_levels=bloom_levels, count=hw.total_questions
    )
    dataset_row = await session.execute(
        select(HomeworkDataset.dataset_id).where(HomeworkDataset.homework_id == hw.id).limit(1)
    )
    dataset_id = dataset_row.scalar_one_or_none()

    for order, q in enumerate(questions, start=1):
        session.add(
            HomeworkQuestion(
                homework_id=hw.id,
                order=order,
                bloom_level=q.bloom_level,
                dataset_id=dataset_id,
                text=q.text,
                answer=q.answer,
            )
        )
    hw.status = HomeworkStatus.REVIEW
    await session.commit()
    await session.refresh(hw)
    return await _serialize(session, hw)


@router.get("/homework/{homework_id}/questions")
async def list_homework_questions(
    homework_id: str,
    user: User = Depends(require_role(Role.TEACHER)),
    session: AsyncSession = Depends(get_db_session),
) -> ListEnvelope[HomeworkQuestionOut]:
    await get_homework_in_school(session, homework_id, user.school_id)
    result = await session.execute(
        select(HomeworkQuestion)
        .where(HomeworkQuestion.homework_id == homework_id)
        .order_by(HomeworkQuestion.order)
    )
    items = [
        HomeworkQuestionOut(
            id=str(q.id),
            homework_id=homework_id,
            order=q.order,
            bloom_level=q.bloom_level,
            dataset_id=str(q.dataset_id),
            text=q.text,
            answer=q.answer,
        )
        for q in result.scalars().all()
    ]
    return ListEnvelope(items=items, total=len(items))


async def _questions_out(session: AsyncSession, homework_id: str) -> ListEnvelope[HomeworkQuestionOut]:
    result = await session.execute(
        select(HomeworkQuestion)
        .where(HomeworkQuestion.homework_id == homework_id)
        .order_by(HomeworkQuestion.order)
    )
    items = [
        HomeworkQuestionOut(
            id=str(q.id),
            homework_id=homework_id,
            order=q.order,
            bloom_level=q.bloom_level,
            dataset_id=str(q.dataset_id),
            text=q.text,
            answer=q.answer,
        )
        for q in result.scalars().all()
    ]
    return ListEnvelope(items=items, total=len(items))


@router.patch("/homework/{homework_id}/questions/{question_id}")
async def update_homework_question(
    homework_id: str,
    question_id: str,
    body: UpdateHomeworkQuestionIn,
    user: User = Depends(require_role(Role.TEACHER)),
    session: AsyncSession = Depends(get_db_session),
) -> ListEnvelope[HomeworkQuestionOut]:
    hw = await get_homework_in_school(session, homework_id, user.school_id)
    if hw.status != HomeworkStatus.REVIEW:
        raise ConflictError("Homework isn't in REVIEW.")
    result = await session.execute(
        select(HomeworkQuestion).where(
            HomeworkQuestion.id == question_id, HomeworkQuestion.homework_id == homework_id
        )
    )
    question = result.scalar_one_or_none()
    if question is None:
        raise NotFoundError(f'No question "{question_id}" on this Homework.')
    question.text = body.text
    await session.commit()
    return await _questions_out(session, homework_id)


@router.delete("/homework/{homework_id}/questions/{question_id}")
async def delete_homework_question(
    homework_id: str,
    question_id: str,
    user: User = Depends(require_role(Role.TEACHER)),
    session: AsyncSession = Depends(get_db_session),
) -> ListEnvelope[HomeworkQuestionOut]:
    await get_homework_in_school(session, homework_id, user.school_id)
    result = await session.execute(
        select(HomeworkQuestion).where(
            HomeworkQuestion.id == question_id, HomeworkQuestion.homework_id == homework_id
        )
    )
    question = result.scalar_one_or_none()
    if question is not None:
        await session.delete(question)
        await session.commit()
    return await _questions_out(session, homework_id)


@router.post("/homework/{homework_id}/questions/{question_id}/replace")
async def replace_homework_question(
    homework_id: str,
    question_id: str,
    user: User = Depends(require_role(Role.TEACHER)),
    session: AsyncSession = Depends(get_db_session),
) -> ListEnvelope[HomeworkQuestionOut]:
    hw = await get_homework_in_school(session, homework_id, user.school_id)
    result = await session.execute(
        select(HomeworkQuestion).where(
            HomeworkQuestion.id == question_id, HomeworkQuestion.homework_id == homework_id
        )
    )
    question = result.scalar_one_or_none()
    if question is None:
        raise NotFoundError(f'No question "{question_id}" on this Homework.')

    generator = get_content_generator()
    candidates = generator.generate_replacement_candidates(
        topic=hw.gap_topic or "this topic",
        bloom_level=question.bloom_level,
        exclude_text=question.text,
        count=1,
    )
    if candidates:
        question.text = candidates[0]
    await session.commit()
    return await _questions_out(session, homework_id)


@router.post("/homework/{homework_id}/assign")
async def assign_homework(
    homework_id: str,
    body: AssignHomeworkIn,
    user: User = Depends(require_role(Role.TEACHER)),
    session: AsyncSession = Depends(get_db_session),
) -> HomeworkOut:
    hw = await get_homework_in_school(session, homework_id, user.school_id)
    hw.target_mode = body.target.mode
    hw.completion_window_hours = body.completion_window_hours
    hw.status = HomeworkStatus.ASSIGNED

    if body.target.mode == AssignmentTargetMode.SPECIFIC_STUDENTS:
        for student_id in body.target.student_ids or []:
            session.add(HomeworkTargetStudent(homework_id=hw.id, student_id=student_id))

    await session.commit()
    await session.refresh(hw)
    return await _serialize(session, hw)
