"""Shared analytics computation for one school - extracted from
school_admin.py's GET /school/analytics so a Super Admin can compute the
exact same, real, non-snapshotted numbers for an explicit school_id (see
requirements.md's usage-insight hierarchy: Platform -> School -> Class).
Every number here is computed live from real rows at read time - no
snapshot table, so it's always exactly consistent, same guarantee
MasteryTrendPointOut's docstring already makes.
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas.bloom import BloomScore
from src.api.schemas.school_admin import ClassBreakdownOut, MasteryTrendPointOut, SchoolAnalyticsOut
from src.domain.models import (
    BloomLevel,
    Homework,
    SchoolClass,
    StudentTestResult,
    StudentTestResultBloomScore,
    TopicPerformance,
    VoiceTest,
)


async def compute_school_analytics(session: AsyncSession, school_id: UUID | str) -> SchoolAnalyticsOut:
    classes_result = await session.execute(select(SchoolClass).where(SchoolClass.school_id == school_id))
    classes = classes_result.scalars().all()

    school_mastery_row = await session.execute(
        select(func.avg(StudentTestResult.mastery_percent))
        .join(VoiceTest, VoiceTest.id == StudentTestResult.test_id)
        .join(SchoolClass, SchoolClass.id == VoiceTest.class_id)
        .where(SchoolClass.school_id == school_id)
    )
    school_mastery_avg = school_mastery_row.scalar_one_or_none()

    class_breakdown = []
    for c in classes:
        mastery_row = await session.execute(
            select(func.avg(StudentTestResult.mastery_percent))
            .join(VoiceTest, VoiceTest.id == StudentTestResult.test_id)
            .where(VoiceTest.class_id == c.id)
        )
        mastery_avg = mastery_row.scalar_one_or_none()

        improvement_row = await session.execute(
            select(func.avg(TopicPerformance.after_percent - TopicPerformance.before_percent))
            .join(Homework, Homework.id == TopicPerformance.homework_id)
            .where(
                Homework.class_id == c.id,
                TopicPerformance.before_percent.is_not(None),
                TopicPerformance.after_percent.is_not(None),
            )
        )
        improvement_avg = improvement_row.scalar_one_or_none()

        class_breakdown.append(
            ClassBreakdownOut(
                class_id=str(c.id), label=f"Class {c.grade} · {c.section}",
                mastery_avg_percent=round(mastery_avg) if mastery_avg is not None else 0,
                improvement_percent=round(improvement_avg) if improvement_avg is not None else 0,
            )
        )

    bloom_averages = []
    for level in BloomLevel:
        bloom_row = await session.execute(
            select(func.avg(StudentTestResultBloomScore.percent))
            .join(
                StudentTestResult,
                StudentTestResult.id == StudentTestResultBloomScore.student_test_result_id,
            )
            .join(VoiceTest, VoiceTest.id == StudentTestResult.test_id)
            .join(SchoolClass, SchoolClass.id == VoiceTest.class_id)
            .where(SchoolClass.school_id == school_id, StudentTestResultBloomScore.bloom_level == level)
        )
        percent = bloom_row.scalar_one_or_none()
        bloom_averages.append(BloomScore(level=level, percent=round(percent) if percent is not None else None))

    week_expr = func.date_trunc("week", VoiceTest.created_at)
    trend_rows = await session.execute(
        select(week_expr, func.avg(StudentTestResult.mastery_percent), func.count(StudentTestResult.id))
        .select_from(StudentTestResult)
        .join(VoiceTest, VoiceTest.id == StudentTestResult.test_id)
        .join(SchoolClass, SchoolClass.id == VoiceTest.class_id)
        .where(SchoolClass.school_id == school_id)
        .group_by(week_expr)
        .order_by(week_expr)
    )
    mastery_trend = [
        MasteryTrendPointOut(
            period_label=week_start.strftime("%b %-d"),
            mastery_avg_percent=round(avg_mastery) if avg_mastery is not None else 0,
            test_count=count,
        )
        for week_start, avg_mastery, count in trend_rows.all()[-8:]
    ]

    return SchoolAnalyticsOut(
        school_mastery_avg_percent=round(school_mastery_avg) if school_mastery_avg is not None else 0,
        class_breakdown=class_breakdown,
        bloom_averages=bloom_averages,
        mastery_trend=mastery_trend,
    )
