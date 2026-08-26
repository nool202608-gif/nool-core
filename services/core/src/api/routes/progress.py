from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db_session, require_role
from src.api.schemas.bloom import BloomScore
from src.api.schemas.progress import (
    NextBestFocusOut,
    StudentProgressOverviewOut,
    SubjectProgressSummaryOut,
    SubjectTestSummaryOut,
    TrajectoryPointOut,
)
from src.domain.models import (
    BloomLevel,
    Role,
    StudentTestResult,
    StudentTestResultBloomScore,
    Subject,
    User,
    VoiceTest,
)

router = APIRouter(prefix="/api/v1", tags=["progress"])


@router.get("/me/progress")
async def get_my_progress(
    user: User = Depends(require_role(Role.STUDENT)),
    session: AsyncSession = Depends(get_db_session),
) -> StudentProgressOverviewOut:
    result_ids_rows = await session.execute(
        select(StudentTestResult.id).where(StudentTestResult.student_id == user.id)
    )
    result_ids = [row[0] for row in result_ids_rows.all()]

    bloom_mastery: list[BloomScore]
    if result_ids:
        averages_rows = await session.execute(
            select(StudentTestResultBloomScore.bloom_level, func.avg(StudentTestResultBloomScore.percent))
            .where(StudentTestResultBloomScore.student_test_result_id.in_(result_ids))
            .group_by(StudentTestResultBloomScore.bloom_level)
        )
        averages = {level: pct for level, pct in averages_rows.all() if pct is not None}
        bloom_mastery = [
            BloomScore(level=level, percent=round(averages[level]) if level in averages else None)
            for level in BloomLevel
        ]
    else:
        bloom_mastery = [BloomScore(level=level, percent=None) for level in BloomLevel]

    subject_rows = await session.execute(
        select(Subject, func.avg(StudentTestResult.mastery_percent), func.count(StudentTestResult.id))
        .join(VoiceTest, VoiceTest.subject_id == Subject.id)
        .join(StudentTestResult, StudentTestResult.test_id == VoiceTest.id)
        .where(StudentTestResult.student_id == user.id)
        .group_by(Subject.id)
    )
    subject_summaries = [
        SubjectProgressSummaryOut(
            subject_id=str(subject.id),
            subject_label=subject.name,
            tests_count=count,
            concepts_tracked=0,
            score_percent=round(avg_pct or 0),
            score_trend_label="",
            strongest_concept="",
            strongest_concept_percent=0,
            focus_concept="",
            focus_concept_percent=0,
        )
        for subject, avg_pct, count in subject_rows.all()
    ]

    return StudentProgressOverviewOut(
        bloom_mastery=bloom_mastery,
        subject_summaries=subject_summaries,
        subject_tests=[
            SubjectTestSummaryOut(
                subject_id=s.subject_id, label=s.subject_label, test_type="Test", score_percent=s.score_percent, trend_label=""
            )
            for s in subject_summaries
        ],
        trajectory=[TrajectoryPointOut(label="Now", mastery_percent=round(sum(b.percent or 0 for b in bloom_mastery) / len(bloom_mastery)))],
        trajectory_gain_label="",
        next_best_focus=NextBestFocusOut(label="", message=""),
    )
