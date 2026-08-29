from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.errors import NotFoundError

from src.api.deps import get_db_session, require_feature, require_role
from src.api.schemas.bloom import BloomDelta
from src.api.schemas.improvement import (
    ClassImprovementOut,
    StudentImprovementOut,
    StudentImprovementStatus,
    StudentImprovementSummaryOut,
    TopicImprovementOut,
)
from src.domain.models import (
    Feature,
    Homework,
    RetestAttempt,
    RetestBloomComparison,
    Role,
    StudentRetestStatus,
    TopicPerformance,
    User,
)
from src.repositories.lookups import get_test_in_school

router = APIRouter(prefix="/api/v1", tags=["improvement"])


async def _homework_for_test(session: AsyncSession, test_id) -> Homework:
    result = await session.execute(select(Homework).where(Homework.test_id == test_id))
    hw = result.scalar_one_or_none()
    if hw is None:
        raise NotFoundError("No Homework has been generated from this Test yet.")
    return hw


async def _bloom_improvement_for(session: AsyncSession, attempt_ids: list) -> list[BloomDelta]:
    from src.domain.models import BloomLevel

    if not attempt_ids:
        return [BloomDelta(level=level, before=None, after=None) for level in BloomLevel]
    result = await session.execute(
        select(RetestBloomComparison).where(RetestBloomComparison.retest_attempt_id.in_(attempt_ids))
    )
    rows = result.scalars().all()
    by_level: dict = {}
    for row in rows:
        by_level.setdefault(row.bloom_level, []).append(row)
    deltas = []
    for level in BloomLevel:
        entries = by_level.get(level, [])
        before_vals = [e.before for e in entries if e.before is not None]
        after_vals = [e.after for e in entries if e.after is not None]
        deltas.append(
            BloomDelta(
                level=level,
                before=round(sum(before_vals) / len(before_vals)) if before_vals else None,
                after=round(sum(after_vals) / len(after_vals)) if after_vals else None,
            )
        )
    return deltas


async def _topic_improvement_for(session: AsyncSession, test_id, homework_id) -> list[TopicImprovementOut]:
    result = await session.execute(
        select(TopicPerformance).where(
            TopicPerformance.test_id == test_id, TopicPerformance.homework_id == homework_id
        )
    )
    return [
        TopicImprovementOut(
            topic_label=t.topic_label, before_percent=t.before_percent, after_percent=t.after_percent
        )
        for t in result.scalars().all()
    ]


@router.get("/tests/{test_id}/improvement/class")
async def get_class_improvement(
    test_id: str,
    user: User = Depends(require_role(Role.TEACHER)),
    _feature: User = Depends(require_feature(Feature.IMPROVEMENT_ANALYSIS)),
    session: AsyncSession = Depends(get_db_session),
) -> ClassImprovementOut:
    test = await get_test_in_school(session, test_id, user.school_id)
    hw = await _homework_for_test(session, test.id)

    result = await session.execute(select(RetestAttempt).where(RetestAttempt.homework_id == hw.id))
    attempts = result.scalars().all()
    completed = [a for a in attempts if a.status == StudentRetestStatus.RESULT_READY]

    baseline_vals = [a.baseline_percent for a in completed if a.baseline_percent is not None]
    retest_vals = [a.retest_percent for a in completed if a.retest_percent is not None]
    baseline_percent = round(sum(baseline_vals) / len(baseline_vals)) if baseline_vals else 0
    retest_percent = round(sum(retest_vals) / len(retest_vals)) if retest_vals else 0

    return ClassImprovementOut(
        test_id=str(test.id),
        homework_id=str(hw.id),
        homework_gap_topic=hw.gap_topic,
        baseline_percent=baseline_percent,
        retest_percent=retest_percent,
        improvement_percent=retest_percent - baseline_percent,
        assigned_count=hw.assigned_count,
        retested_count=len(completed),
        bloom_improvement=await _bloom_improvement_for(session, [a.id for a in completed]),
        topic_improvement=await _topic_improvement_for(session, test.id, hw.id),
        students=[
            StudentImprovementSummaryOut(
                student_id=str(a.student_id),
                status=(
                    StudentImprovementStatus.RETEST_COMPLETE
                    if a.status == StudentRetestStatus.RESULT_READY
                    else StudentImprovementStatus.RETEST_INCOMPLETE
                ),
                before_percent=a.baseline_percent or 0,
                after_percent=a.retest_percent,
            )
            for a in attempts
        ],
    )


@router.get("/tests/{test_id}/improvement/students/{student_id}")
async def get_student_improvement(
    test_id: str,
    student_id: str,
    user: User = Depends(require_role(Role.TEACHER)),
    _feature: User = Depends(require_feature(Feature.IMPROVEMENT_ANALYSIS)),
    session: AsyncSession = Depends(get_db_session),
) -> StudentImprovementOut:
    test = await get_test_in_school(session, test_id, user.school_id)
    hw = await _homework_for_test(session, test.id)

    result = await session.execute(
        select(RetestAttempt).where(
            RetestAttempt.homework_id == hw.id, RetestAttempt.student_id == student_id
        )
    )
    attempt = result.scalar_one_or_none()
    if attempt is None:
        raise NotFoundError("This student has no Retest attempt for this Test's Homework.")

    status = (
        StudentImprovementStatus.RETEST_COMPLETE
        if attempt.status == StudentRetestStatus.RESULT_READY
        else StudentImprovementStatus.RETEST_INCOMPLETE
    )
    return StudentImprovementOut(
        student_id=student_id,
        test_id=str(test.id),
        homework_id=str(hw.id),
        homework_gap_topic=hw.gap_topic,
        status=status,
        before_percent=attempt.baseline_percent or 0,
        after_percent=attempt.retest_percent,
        bloom_improvement=await _bloom_improvement_for(session, [attempt.id]),
        topic_improvement=await _topic_improvement_for(session, test.id, hw.id),
    )
