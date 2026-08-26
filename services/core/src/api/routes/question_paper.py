from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.errors import ConflictError, NotFoundError, ValidationError

from src.api.deps import get_db_session, require_role
from src.api.schemas.bloom import BloomTarget
from src.api.schemas.common import ListEnvelope
from src.api.schemas.dataset import DatasetShare
from src.api.schemas.question_paper import (
    CreateQuestionPaperIn,
    PaperDifficultyTarget,
    PaperRules,
    PaperSection,
    PaperValidationOut,
    QuestionPaperOut,
    QuestionPaperQuestionCandidateOut,
    QuestionPaperQuestionOut,
    ReorderQuestionsIn,
    UpdateQuestionPaperQuestionIn,
)
from src.domain.models import (
    QuestionPaper,
    QuestionPaperBloomDistribution,
    QuestionPaperChapter,
    QuestionPaperDatasetShare,
    QuestionPaperDifficultyDistribution,
    QuestionPaperQuestion,
    QuestionPaperSection,
    QuestionPaperStatus,
    QuestionPaperTopic,
    QuestionPaperValidation,
    Role,
    School,
    User,
)
from src.repositories.subscription_repository import get_active_plan
from src.repositories.usage_repository import count_question_papers
from src.services.bloom_defaults import resolve_bloom_targets
from src.services.content_generator import get_content_generator

router = APIRouter(prefix="/api/v1", tags=["question-papers"])


async def _get_paper_in_school(session: AsyncSession, paper_id: str, school_id) -> QuestionPaper:
    result = await session.execute(
        select(QuestionPaper).where(QuestionPaper.id == paper_id, QuestionPaper.school_id == school_id)
    )
    paper = result.scalar_one_or_none()
    if paper is None:
        raise NotFoundError(f'No Question Paper with id "{paper_id}".')
    return paper


async def _serialize(session: AsyncSession, paper: QuestionPaper) -> QuestionPaperOut:
    shares = await session.execute(
        select(QuestionPaperDatasetShare).where(QuestionPaperDatasetShare.paper_id == paper.id)
    )
    chapters = await session.execute(
        select(QuestionPaperChapter.chapter_id).where(QuestionPaperChapter.paper_id == paper.id)
    )
    topics = await session.execute(
        select(QuestionPaperTopic.topic_id).where(QuestionPaperTopic.paper_id == paper.id)
    )
    sections = await session.execute(
        select(QuestionPaperSection).where(QuestionPaperSection.paper_id == paper.id)
    )
    bloom_dist = await session.execute(
        select(QuestionPaperBloomDistribution).where(QuestionPaperBloomDistribution.paper_id == paper.id)
    )
    difficulty_dist = await session.execute(
        select(QuestionPaperDifficultyDistribution).where(
            QuestionPaperDifficultyDistribution.paper_id == paper.id
        )
    )
    validation_row = await session.execute(
        select(QuestionPaperValidation).where(QuestionPaperValidation.paper_id == paper.id)
    )
    validation = validation_row.scalar_one_or_none()

    return QuestionPaperOut(
        id=str(paper.id),
        name=paper.name,
        exam_type=paper.exam_type,
        board=paper.board,
        grade=paper.grade,
        language=paper.language,
        subject_id=str(paper.subject_id),
        dataset_shares=[
            DatasetShare(dataset_id=str(s.dataset_id), percent=s.percent) for s in shares.scalars().all()
        ],
        chapter_ids=[str(row[0]) for row in chapters.all()],
        topic_ids=[str(row[0]) for row in topics.all()],
        total_marks=paper.total_marks,
        duration_minutes=paper.duration_minutes,
        sections=[
            PaperSection(label=s.label, question_count=s.question_count, marks_each=s.marks_each)
            for s in sections.scalars().all()
        ],
        bloom_distribution=[
            BloomTarget(level=d.bloom_level, value=d.value) for d in bloom_dist.scalars().all()
        ],
        difficulty_distribution=[
            PaperDifficultyTarget(level=d.level, value=d.value) for d in difficulty_dist.scalars().all()
        ],
        question_types=paper.question_types or [],
        rules=PaperRules(
            allow_internal_choice=paper.allow_internal_choice,
            avoid_duplicate_concepts=paper.avoid_duplicate_concepts,
            respect_chapter_weightage=paper.respect_chapter_weightage,
            avoid_recent_repetition=paper.avoid_recent_repetition,
        ),
        status=paper.status,
        validation=(
            PaperValidationOut(
                coverage_percent=validation.coverage_percent,
                marks_accounted_for=validation.marks_accounted_for,
                duplicate_count=validation.duplicate_count,
                quality_percent=validation.quality_percent,
                issues=validation.issues,
            )
            if validation is not None
            else None
        ),
        custom_header_text=paper.custom_header_text,
        logo_data_uri=paper.logo_data_uri,
        instructions=paper.instructions,
    )


async def _apply_body(session: AsyncSession, paper: QuestionPaper, body: CreateQuestionPaperIn) -> None:
    paper.name = body.name
    paper.exam_type = body.exam_type
    paper.board = body.board
    paper.grade = body.grade
    paper.language = body.language
    paper.subject_id = body.subject_id
    paper.total_marks = body.total_marks
    paper.duration_minutes = body.duration_minutes
    paper.question_types = body.question_types
    paper.custom_header_text = body.custom_header_text
    paper.logo_data_uri = body.logo_data_uri
    paper.instructions = body.instructions
    paper.status = QuestionPaperStatus.DRAFT

    for model, existing_field in (
        (QuestionPaperDatasetShare, "paper_id"),
        (QuestionPaperChapter, "paper_id"),
        (QuestionPaperTopic, "paper_id"),
        (QuestionPaperSection, "paper_id"),
        (QuestionPaperBloomDistribution, "paper_id"),
        (QuestionPaperDifficultyDistribution, "paper_id"),
    ):
        existing = await session.execute(select(model).where(getattr(model, existing_field) == paper.id))
        for row in existing.scalars().all():
            await session.delete(row)
    await session.flush()

    for share in body.dataset_shares or []:
        session.add(
            QuestionPaperDatasetShare(paper_id=paper.id, dataset_id=share.dataset_id, percent=share.percent)
        )
    for chapter_id in body.chapter_ids or []:
        session.add(QuestionPaperChapter(paper_id=paper.id, chapter_id=chapter_id))
    for topic_id in body.topic_ids or []:
        session.add(QuestionPaperTopic(paper_id=paper.id, topic_id=topic_id))
    for section in body.sections or []:
        session.add(
            QuestionPaperSection(
                paper_id=paper.id,
                label=section.label,
                question_count=section.question_count,
                marks_each=section.marks_each,
            )
        )
    school = await session.get(School, paper.school_id)
    for target in resolve_bloom_targets(school, body.bloom_distribution):
        session.add(
            QuestionPaperBloomDistribution(paper_id=paper.id, bloom_level=target.level, value=target.value)
        )
    for target in body.difficulty_distribution or []:
        session.add(
            QuestionPaperDifficultyDistribution(paper_id=paper.id, level=target.level, value=target.value)
        )


@router.get("/question-papers")
async def list_papers(
    user: User = Depends(require_role(Role.TEACHER)),
    session: AsyncSession = Depends(get_db_session),
) -> ListEnvelope[QuestionPaperOut]:
    result = await session.execute(select(QuestionPaper).where(QuestionPaper.school_id == user.school_id))
    items = [await _serialize(session, p) for p in result.scalars().all()]
    return ListEnvelope(items=items, total=len(items))


@router.get("/question-papers/{paper_id}")
async def get_paper(
    paper_id: str,
    user: User = Depends(require_role(Role.TEACHER)),
    session: AsyncSession = Depends(get_db_session),
) -> QuestionPaperOut:
    paper = await _get_paper_in_school(session, paper_id, user.school_id)
    return await _serialize(session, paper)


@router.post("/question-papers", status_code=201, summary="Create (DRAFT)")
async def create_paper(
    body: CreateQuestionPaperIn,
    user: User = Depends(require_role(Role.TEACHER)),
    session: AsyncSession = Depends(get_db_session),
) -> QuestionPaperOut:
    plan = await get_active_plan(session, user.school_id)
    if plan is not None and plan.question_paper_limit is not None:
        if await count_question_papers(session, user.school_id) >= plan.question_paper_limit:
            raise ConflictError(f"Your plan allows up to {plan.question_paper_limit} Question Papers.")

    # The NOT NULL scalar columns (name/examType/board/grade/language/
    # subjectId) must be set before this flush, not only inside
    # _apply_body afterward - _apply_body needs paper.id already assigned
    # (id has no server-side default, only a Python-side one SQLAlchemy
    # only applies at flush) to attach child rows, so the flush has to
    # come first; leaving these columns unset until then violates their
    # NOT NULL constraint on insert.
    paper = QuestionPaper(
        school_id=user.school_id, created_by=user.id, status=QuestionPaperStatus.DRAFT,
        name=body.name, exam_type=body.exam_type, board=body.board, grade=body.grade,
        language=body.language, subject_id=body.subject_id,
    )
    session.add(paper)
    await session.flush()
    await _apply_body(session, paper, body)
    await session.commit()
    await session.refresh(paper)
    return await _serialize(session, paper)


@router.put("/question-papers/{paper_id}", summary="Overwrite blueprint")
async def update_paper(
    paper_id: str,
    body: CreateQuestionPaperIn,
    user: User = Depends(require_role(Role.TEACHER)),
    session: AsyncSession = Depends(get_db_session),
) -> QuestionPaperOut:
    paper = await _get_paper_in_school(session, paper_id, user.school_id)
    await _apply_body(session, paper, body)
    await session.commit()
    await session.refresh(paper)
    return await _serialize(session, paper)


@router.post("/question-papers/{paper_id}/generate")
async def generate_paper(
    paper_id: str,
    user: User = Depends(require_role(Role.TEACHER)),
    session: AsyncSession = Depends(get_db_session),
) -> QuestionPaperOut:
    paper = await _get_paper_in_school(session, paper_id, user.school_id)

    bloom_dist = await session.execute(
        select(QuestionPaperBloomDistribution).where(QuestionPaperBloomDistribution.paper_id == paper.id)
    )
    bloom_levels = [d.bloom_level for d in bloom_dist.scalars().all()]
    target_count = paper.total_marks or 10

    generator = get_content_generator()
    questions = generator.generate_questions(
        topic=paper.name, bloom_levels=bloom_levels, count=target_count
    )

    existing = await session.execute(
        select(QuestionPaperQuestion).where(QuestionPaperQuestion.paper_id == paper.id)
    )
    for row in existing.scalars().all():
        await session.delete(row)
    await session.flush()

    for order, q in enumerate(questions, start=1):
        session.add(
            QuestionPaperQuestion(
                paper_id=paper.id, order=order, bloom_level=q.bloom_level, marks=1, text=q.text
            )
        )

    existing_validation = await session.execute(
        select(QuestionPaperValidation).where(QuestionPaperValidation.paper_id == paper.id)
    )
    validation = existing_validation.scalar_one_or_none()
    coverage_percent = 100 if questions else 0
    issues: list[str] = [] if questions else ["No questions could be generated for this configuration."]
    if validation is None:
        validation = QuestionPaperValidation(paper_id=paper.id)
        session.add(validation)
    validation.coverage_percent = coverage_percent
    validation.marks_accounted_for = len(questions)
    validation.duplicate_count = 0
    validation.quality_percent = 100 if questions else 0
    validation.issues = issues

    paper.status = QuestionPaperStatus.REVIEW if questions else QuestionPaperStatus.VALIDATION_FAILED
    await session.commit()
    await session.refresh(paper)
    return await _serialize(session, paper)


async def _paper_questions_out(session: AsyncSession, paper_id: str) -> ListEnvelope[QuestionPaperQuestionOut]:
    result = await session.execute(
        select(QuestionPaperQuestion)
        .where(QuestionPaperQuestion.paper_id == paper_id)
        .order_by(QuestionPaperQuestion.order)
    )
    items = [
        QuestionPaperQuestionOut(
            id=str(q.id), paper_id=paper_id, order=q.order, bloom_level=q.bloom_level, marks=q.marks, text=q.text
        )
        for q in result.scalars().all()
    ]
    return ListEnvelope(items=items, total=len(items))


@router.get("/question-papers/{paper_id}/questions")
async def list_paper_questions(
    paper_id: str,
    user: User = Depends(require_role(Role.TEACHER)),
    session: AsyncSession = Depends(get_db_session),
) -> ListEnvelope[QuestionPaperQuestionOut]:
    await _get_paper_in_school(session, paper_id, user.school_id)
    return await _paper_questions_out(session, paper_id)


@router.patch("/question-papers/{paper_id}/questions/{question_id}")
async def update_paper_question(
    paper_id: str,
    question_id: str,
    body: UpdateQuestionPaperQuestionIn,
    user: User = Depends(require_role(Role.TEACHER)),
    session: AsyncSession = Depends(get_db_session),
) -> ListEnvelope[QuestionPaperQuestionOut]:
    paper = await _get_paper_in_school(session, paper_id, user.school_id)
    if paper.status != QuestionPaperStatus.REVIEW:
        raise ConflictError("Paper isn't in REVIEW.")
    result = await session.execute(
        select(QuestionPaperQuestion).where(
            QuestionPaperQuestion.id == question_id, QuestionPaperQuestion.paper_id == paper_id
        )
    )
    question = result.scalar_one_or_none()
    if question is None:
        raise NotFoundError(f'No question "{question_id}" on this paper.')
    question.text = body.text
    await session.commit()
    return await _paper_questions_out(session, paper_id)


@router.get("/question-papers/{paper_id}/questions/{question_id}/candidates", summary="Shuffle picker")
async def get_question_candidates(
    paper_id: str,
    question_id: str,
    user: User = Depends(require_role(Role.TEACHER)),
    session: AsyncSession = Depends(get_db_session),
) -> ListEnvelope[QuestionPaperQuestionCandidateOut]:
    paper = await _get_paper_in_school(session, paper_id, user.school_id)
    if paper.status != QuestionPaperStatus.REVIEW:
        raise ConflictError("Paper isn't in REVIEW.")
    result = await session.execute(
        select(QuestionPaperQuestion).where(
            QuestionPaperQuestion.id == question_id, QuestionPaperQuestion.paper_id == paper_id
        )
    )
    question = result.scalar_one_or_none()
    if question is None:
        raise NotFoundError(f'No question "{question_id}" on this paper.')

    generator = get_content_generator()
    candidates = generator.generate_replacement_candidates(
        topic=paper.name, bloom_level=question.bloom_level, exclude_text=question.text, count=3
    )
    items = [
        QuestionPaperQuestionCandidateOut(id=f"{question_id}-alt-{i + 1}", text=text)
        for i, text in enumerate(candidates)
    ]
    return ListEnvelope(items=items, total=len(items))


@router.put("/question-papers/{paper_id}/questions/order")
async def reorder_questions(
    paper_id: str,
    body: ReorderQuestionsIn,
    user: User = Depends(require_role(Role.TEACHER)),
    session: AsyncSession = Depends(get_db_session),
) -> ListEnvelope[QuestionPaperQuestionOut]:
    await _get_paper_in_school(session, paper_id, user.school_id)
    result = await session.execute(
        select(QuestionPaperQuestion).where(QuestionPaperQuestion.paper_id == paper_id)
    )
    questions = {str(q.id): q for q in result.scalars().all()}
    if set(body.ordered_question_ids) != set(questions.keys()):
        raise ValidationError("orderedQuestionIds doesn't match the paper's current question set exactly.")

    for order, question_id in enumerate(body.ordered_question_ids, start=1):
        questions[question_id].order = order
    await session.commit()
    return await _paper_questions_out(session, paper_id)


@router.post("/question-papers/{paper_id}/finalize")
async def finalize_paper(
    paper_id: str,
    user: User = Depends(require_role(Role.TEACHER)),
    session: AsyncSession = Depends(get_db_session),
) -> QuestionPaperOut:
    paper = await _get_paper_in_school(session, paper_id, user.school_id)
    paper.status = QuestionPaperStatus.FINALIZED
    await session.commit()
    await session.refresh(paper)
    return await _serialize(session, paper)
