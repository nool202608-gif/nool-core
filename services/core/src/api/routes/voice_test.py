from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.errors import ConflictError, ForbiddenError, ValidationError

from src.api.deps import get_db_session, require_role
from src.api.schemas.common import ListEnvelope
from src.api.schemas.roster import AssignmentTarget
from src.api.schemas.voice_test import CreateTestIn, VoiceTestOut
from src.domain.models import (
    AssignmentTargetMode,
    Role,
    SchoolClass,
    TestStatus,
    User,
    VoiceTest,
    VoiceTestBloomLevel,
    VoiceTestTargetStudent,
)
from src.repositories.lookups import get_test_in_school
from src.repositories.roster_repository import teaches_class_subject
from src.repositories.subscription_repository import get_active_plan
from src.repositories.usage_repository import count_tests

router = APIRouter(prefix="/api/v1", tags=["voice-tests"])


async def _serialize(session: AsyncSession, test: VoiceTest) -> VoiceTestOut:
    bloom_result = await session.execute(
        select(VoiceTestBloomLevel.bloom_level).where(VoiceTestBloomLevel.test_id == test.id)
    )
    bloom_levels = [row[0] for row in bloom_result.all()]

    student_ids: list[str] | None = None
    if test.target_mode == AssignmentTargetMode.SPECIFIC_STUDENTS:
        targets = await session.execute(
            select(VoiceTestTargetStudent.student_id).where(VoiceTestTargetStudent.test_id == test.id)
        )
        student_ids = [str(row[0]) for row in targets.all()]

    return VoiceTestOut(
        id=str(test.id),
        class_id=str(test.class_id),
        subject_id=str(test.subject_id),
        chapter_id=str(test.chapter_id),
        topic_id=str(test.topic_id) if test.topic_id else None,
        bloom_levels=bloom_levels,
        duration_minutes=test.duration_minutes,
        completion_window_hours=test.completion_window_hours,
        target=AssignmentTarget(mode=test.target_mode, student_ids=student_ids),
        status=test.status,
        assigned_count=test.assigned_count,
        completed_count=test.completed_count,
        created_at=test.created_at,
    )


@router.get("/tests")
async def list_tests(
    user: User = Depends(require_role(Role.TEACHER)),
    session: AsyncSession = Depends(get_db_session),
) -> ListEnvelope[VoiceTestOut]:
    result = await session.execute(
        select(VoiceTest)
        .join(SchoolClass, SchoolClass.id == VoiceTest.class_id)
        .where(SchoolClass.school_id == user.school_id)
    )
    tests = result.scalars().all()
    items = [await _serialize(session, t) for t in tests]
    return ListEnvelope(items=items, total=len(items))


@router.get("/tests/{test_id}")
async def get_test(
    test_id: str,
    user: User = Depends(require_role(Role.TEACHER)),
    session: AsyncSession = Depends(get_db_session),
) -> VoiceTestOut:
    test = await get_test_in_school(session, test_id, user.school_id)
    return await _serialize(session, test)


@router.post("/tests", status_code=201, summary="Create a Test (DRAFT)")
async def create_test(
    body: CreateTestIn,
    user: User = Depends(require_role(Role.TEACHER)),
    session: AsyncSession = Depends(get_db_session),
) -> VoiceTestOut:
    if not await teaches_class_subject(session, user.id, body.class_id, body.subject_id):
        raise ForbiddenError("You don't teach that subject in that class.")
    if body.target.mode == AssignmentTargetMode.SPECIFIC_STUDENTS and not body.target.student_ids:
        raise ValidationError("target.studentIds must be non-empty when mode is SPECIFIC_STUDENTS.")

    plan = await get_active_plan(session, user.school_id)
    if plan is not None and plan.test_limit is not None:
        if await count_tests(session, user.school_id) >= plan.test_limit:
            raise ConflictError(f"Your plan allows up to {plan.test_limit} Voice Tests.")

    test = VoiceTest(
        class_id=body.class_id,
        subject_id=body.subject_id,
        chapter_id=body.chapter_id,
        topic_id=body.topic_id,
        duration_minutes=body.duration_minutes,
        completion_window_hours=body.completion_window_hours,
        target_mode=body.target.mode,
        status=TestStatus.DRAFT,
    )
    session.add(test)
    await session.flush()

    for level in body.bloom_levels:
        session.add(VoiceTestBloomLevel(test_id=test.id, bloom_level=level))
    if body.target.mode == AssignmentTargetMode.SPECIFIC_STUDENTS:
        for student_id in body.target.student_ids or []:
            session.add(VoiceTestTargetStudent(test_id=test.id, student_id=student_id))

    await session.commit()
    await session.refresh(test)
    return await _serialize(session, test)


@router.post("/tests/{test_id}/schedule", summary="Make the Test live")
async def schedule_test(
    test_id: str,
    user: User = Depends(require_role(Role.TEACHER)),
    session: AsyncSession = Depends(get_db_session),
) -> VoiceTestOut:
    test = await get_test_in_school(session, test_id, user.school_id)
    if test.status != TestStatus.DRAFT:
        raise ConflictError("Test isn't in a schedulable state.")
    test.status = TestStatus.SCHEDULED
    await session.commit()
    await session.refresh(test)
    return await _serialize(session, test)
