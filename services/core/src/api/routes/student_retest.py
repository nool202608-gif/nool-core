from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.errors import ConflictError, NotFoundError

from src.api.deps import get_db_session, require_role
from src.api.schemas.bloom import BloomDelta
from src.api.schemas.student_retest import (
    EstimatedMinutes,
    ProcessRetestResultIn,
    RetestEntryOut,
    RetestEntryResponse,
    RetestResultOut,
)
from src.domain.models import (
    BloomLevel,
    Homework,
    RetestAttempt,
    RetestBloomComparison,
    Role,
    StudentHomeworkProgress,
    StudentRetestStatus,
    StudentTestResult,
    Subject,
    User,
    VoiceTest,
)

router = APIRouter(prefix="/api/v1", tags=["retest-student"])


@router.get("/me/retest")
async def get_my_retest(
    user: User = Depends(require_role(Role.STUDENT)),
    session: AsyncSession = Depends(get_db_session),
) -> RetestEntryResponse:
    """entry: null when Homework Q&A isn't confirmed complete yet - a real
    precondition, not an error.
    """
    result = await session.execute(
        select(StudentHomeworkProgress, Homework)
        .join(Homework, Homework.id == StudentHomeworkProgress.homework_id)
        .where(StudentHomeworkProgress.student_id == user.id, StudentHomeworkProgress.qa_completed.is_(True))
        .limit(1)
    )
    row = result.first()
    if row is None:
        return RetestEntryResponse(entry=None)
    _, hw = row

    subject_result = await session.execute(
        select(Subject.name)
        .join(VoiceTest, VoiceTest.subject_id == Subject.id)
        .where(VoiceTest.id == hw.test_id)
    )
    subject_label = subject_result.scalar_one_or_none() or ""

    attempt_result = await session.execute(
        select(RetestAttempt).where(RetestAttempt.homework_id == hw.id, RetestAttempt.student_id == user.id)
    )
    attempt = attempt_result.scalar_one_or_none()
    attempts_used = attempt.attempts_used if attempt else 0

    entry = RetestEntryOut(
        homework_id=str(hw.id),
        original_test_id=str(hw.test_id),
        subject_label=subject_label,
        topic_label=hw.gap_topic,
        estimated_minutes=EstimatedMinutes(min=8, max=10),
        max_attempts=1,
        attempts_used=attempts_used,
    )
    return RetestEntryResponse(entry=entry)


@router.post("/me/retest/{homework_id}/result", summary="Process a completed Retest session")
async def process_retest_result(
    homework_id: str,
    body: ProcessRetestResultIn,
    user: User = Depends(require_role(Role.STUDENT)),
    session: AsyncSession = Depends(get_db_session),
) -> RetestResultOut:
    result = await session.execute(
        select(RetestAttempt).where(
            RetestAttempt.homework_id == homework_id, RetestAttempt.student_id == user.id
        )
    )
    attempt = result.scalar_one_or_none()
    if attempt is not None and attempt.attempts_used >= 1:
        raise ConflictError("This Retest has already been attempted.")

    hw_result = await session.execute(select(Homework).where(Homework.id == homework_id))
    hw = hw_result.scalar_one_or_none()
    if hw is None:
        raise NotFoundError(f'No Homework with id "{homework_id}".')

    baseline_result = await session.execute(
        select(StudentTestResult.mastery_percent).where(
            StudentTestResult.test_id == hw.test_id, StudentTestResult.student_id == user.id
        )
    )
    baseline_percent = baseline_result.scalar_one_or_none() or 0
    retest_percent = (
        round(100 * body.questions_answered / body.total_questions) if body.total_questions else 0
    )

    if attempt is None:
        attempt = RetestAttempt(homework_id=homework_id, student_id=user.id)
        session.add(attempt)
    attempt.status = StudentRetestStatus.RESULT_READY
    attempt.attempts_used = 1
    attempt.baseline_percent = baseline_percent
    attempt.retest_percent = retest_percent
    attempt.improvement_percent = retest_percent - baseline_percent
    attempt.completed_at = datetime.now(timezone.utc)
    await session.flush()

    subject_result = await session.execute(
        select(Subject.name)
        .join(VoiceTest, VoiceTest.subject_id == Subject.id)
        .where(VoiceTest.id == hw.test_id)
    )
    subject_label = subject_result.scalar_one_or_none() or ""

    bloom_comparison = [BloomDelta(level=level, before=None, after=None) for level in BloomLevel]
    for delta in bloom_comparison:
        session.add(
            RetestBloomComparison(
                retest_attempt_id=attempt.id, bloom_level=delta.level, before=delta.before, after=delta.after
            )
        )

    await session.commit()
    return RetestResultOut(
        homework_id=str(hw.id),
        original_test_id=str(hw.test_id),
        subject_label=subject_label,
        topic_label=hw.gap_topic,
        baseline_percent=baseline_percent,
        retest_percent=retest_percent,
        improvement_percent=attempt.improvement_percent,
        bloom_comparison=bloom_comparison,
    )
