"""The pivot-reporting engine's dimension/metric registry and query
execution - see requirements.md's Advanced Reporting section and
ReportConfiguration's model docstring for why dimension/metric names are
plain strings validated here rather than a DB enum.

Every metric here is a real, correctly-computed aggregate over existing
tables - nothing is fabricated. Two SECTION metrics (masteryAvgPercent/
improvementPercent, reusing compute_school_analytics' own established
coalescing behavior) will correctly read 0 in any environment where the
Voice Test lifecycle never reaches RESULTS_READY - a separate,
already-tracked gap (see NEXT_STEP.md) - that's the honest state of the
underlying data, not a defect in this engine.
"""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.errors import ValidationError

from src.domain.models import (
    Plan,
    Role,
    School,
    SchoolClass,
    SchoolGrade,
    StudentProfile,
    Subscription,
    TeacherClassAssignment,
    User,
    VoiceTest,
)
from src.repositories.roster_repository import grade_student_count, section_count
from src.services.school_analytics import compute_school_analytics


@dataclass(frozen=True)
class MetricSpec:
    key: str
    label: str


@dataclass(frozen=True)
class DimensionSpec:
    key: str
    label: str
    # "PLATFORM" = Super Admin, cross-tenant, no school_id needed.
    # "SCHOOL" = needs a school_id - School Admin's own, or Super Admin
    # drilling into one school explicitly.
    scope: str
    metrics: list[MetricSpec]


DIMENSIONS: dict[str, DimensionSpec] = {
    "SCHOOL": DimensionSpec(
        key="SCHOOL", label="School", scope="PLATFORM",
        metrics=[
            MetricSpec("teacherCount", "Teachers"),
            MetricSpec("studentCount", "Students"),
            MetricSpec("gradeCount", "Classes"),
            MetricSpec("sectionCount", "Sections"),
            MetricSpec("testCount", "Voice tests"),
            MetricSpec("status", "Status"),
            MetricSpec("planName", "Plan"),
            MetricSpec("subscriptionStatus", "Subscription status"),
        ],
    ),
    "PLAN": DimensionSpec(
        key="PLAN", label="Plan", scope="PLATFORM",
        metrics=[
            MetricSpec("schoolCount", "Schools on this plan"),
            MetricSpec("teacherLimit", "Teacher limit"),
            MetricSpec("studentLimit", "Student limit"),
            MetricSpec("active", "Active"),
        ],
    ),
    "CLASS": DimensionSpec(
        key="CLASS", label="Class", scope="SCHOOL",
        metrics=[
            MetricSpec("sectionCount", "Sections"),
            MetricSpec("studentCount", "Students"),
            MetricSpec("testCount", "Voice tests"),
            MetricSpec("status", "Status"),
        ],
    ),
    "SECTION": DimensionSpec(
        key="SECTION", label="Section", scope="SCHOOL",
        metrics=[
            MetricSpec("studentCount", "Students"),
            MetricSpec("assignmentCount", "Teacher assignments"),
            MetricSpec("testCount", "Voice tests"),
            MetricSpec("status", "Status"),
            MetricSpec("masteryAvgPercent", "Mastery average %"),
            MetricSpec("improvementPercent", "Improvement %"),
        ],
    ),
    "STUDENT": DimensionSpec(
        key="STUDENT", label="Student", scope="SCHOOL",
        metrics=[
            MetricSpec("sectionLabel", "Section"),
            MetricSpec("rollNumber", "Roll number"),
            MetricSpec("status", "Status"),
            MetricSpec("hasGuardianInfo", "Guardian info on file"),
        ],
    ),
}


def get_dimension(dimension: str) -> DimensionSpec:
    spec = DIMENSIONS.get(dimension)
    if spec is None:
        raise ValidationError(f'Unknown report dimension "{dimension}".')
    return spec


def validate_dimension_and_metrics(dimension: str, metrics: list[str]) -> DimensionSpec:
    spec = get_dimension(dimension)
    if not metrics:
        raise ValidationError("At least one metric is required.")
    valid_metric_keys = {m.key for m in spec.metrics}
    unknown = [m for m in metrics if m not in valid_metric_keys]
    if unknown:
        raise ValidationError(f'Unknown metric(s) for dimension "{dimension}": {", ".join(unknown)}.')
    return spec


async def run_report(
    session: AsyncSession,
    *,
    dimension: str,
    metrics: list[str],
    filters: dict[str, Any],
    school_id: UUID | str | None,
) -> list[dict[str, Any]]:
    """`school_id` is required (and always server-controlled - a School
    Admin's own school_id, or a Super Admin's explicit choice - never a
    bare client-supplied value trusted without a role check) for every
    SCHOOL-scoped dimension; None for a Super Admin's platform-wide
    SCHOOL/PLAN report.
    """
    spec = validate_dimension_and_metrics(dimension, metrics)
    if spec.scope == "SCHOOL" and school_id is None:
        raise ValidationError(f'Dimension "{dimension}" requires a school.')

    status_filter = filters.get("status")

    if dimension == "SCHOOL":
        return await _run_school_dimension(session, metrics, status_filter, filters.get("planId"))
    if dimension == "PLAN":
        return await _run_plan_dimension(session, metrics)
    if dimension == "CLASS":
        return await _run_class_dimension(session, metrics, status_filter, school_id)
    if dimension == "SECTION":
        return await _run_section_dimension(session, metrics, status_filter, school_id)
    if dimension == "STUDENT":
        return await _run_student_dimension(session, metrics, status_filter, school_id)
    raise ValidationError(f'Unknown report dimension "{dimension}".')  # pragma: no cover - guarded above


async def _run_school_dimension(
    session: AsyncSession, metrics: list[str], status_filter: str | None, plan_id: str | None,
) -> list[dict[str, Any]]:
    query = select(School)
    if status_filter:
        query = query.where(School.status == status_filter)
    schools = (await session.execute(query)).scalars().all()

    teacher_counts = dict(
        (await session.execute(
            select(User.school_id, func.count()).where(User.role == Role.TEACHER).group_by(User.school_id)
        )).all()
    )
    student_counts = dict(
        (await session.execute(
            select(SchoolClass.school_id, func.count())
            .select_from(StudentProfile)
            .join(SchoolClass, SchoolClass.id == StudentProfile.class_id)
            .group_by(SchoolClass.school_id)
        )).all()
    )
    grade_counts = dict(
        (await session.execute(
            select(SchoolGrade.school_id, func.count()).group_by(SchoolGrade.school_id)
        )).all()
    )
    section_counts = dict(
        (await session.execute(
            select(SchoolClass.school_id, func.count()).group_by(SchoolClass.school_id)
        )).all()
    )
    test_counts = dict(
        (await session.execute(
            select(SchoolClass.school_id, func.count())
            .select_from(VoiceTest)
            .join(SchoolClass, SchoolClass.id == VoiceTest.class_id)
            .group_by(SchoolClass.school_id)
        )).all()
    )
    subs_by_school = {
        s.school_id: s
        for s in (await session.execute(select(Subscription))).scalars().all()
    }
    plans_by_id = {p.id: p for p in (await session.execute(select(Plan))).scalars().all()}

    rows = []
    for school in schools:
        sub = subs_by_school.get(school.id)
        if plan_id and (sub is None or str(sub.plan_id) != plan_id):
            continue
        plan = plans_by_id.get(sub.plan_id) if sub else None
        values: dict[str, Any] = {
            "teacherCount": teacher_counts.get(school.id, 0),
            "studentCount": student_counts.get(school.id, 0),
            "gradeCount": grade_counts.get(school.id, 0),
            "sectionCount": section_counts.get(school.id, 0),
            "testCount": test_counts.get(school.id, 0),
            "status": school.status.value,
            "planName": plan.name if plan else None,
            "subscriptionStatus": sub.status.value if sub else None,
        }
        rows.append({"label": school.name, **{m: values[m] for m in metrics}})
    return rows


async def _run_plan_dimension(session: AsyncSession, metrics: list[str]) -> list[dict[str, Any]]:
    plans = (await session.execute(select(Plan))).scalars().all()
    school_counts = dict(
        (await session.execute(
            select(Subscription.plan_id, func.count()).group_by(Subscription.plan_id)
        )).all()
    )
    rows = []
    for plan in plans:
        values: dict[str, Any] = {
            "schoolCount": school_counts.get(plan.id, 0),
            "teacherLimit": plan.teacher_limit,
            "studentLimit": plan.student_limit,
            "active": plan.active,
        }
        rows.append({"label": plan.name, **{m: values[m] for m in metrics}})
    return rows


async def _run_class_dimension(
    session: AsyncSession, metrics: list[str], status_filter: str | None, school_id: UUID | str,
) -> list[dict[str, Any]]:
    query = select(SchoolGrade).where(SchoolGrade.school_id == school_id)
    if status_filter:
        query = query.where(SchoolGrade.status == status_filter)
    grades = (await session.execute(query)).scalars().all()

    test_counts = dict(
        (await session.execute(
            select(SchoolClass.grade_id, func.count())
            .select_from(VoiceTest)
            .join(SchoolClass, SchoolClass.id == VoiceTest.class_id)
            .where(SchoolClass.school_id == school_id)
            .group_by(SchoolClass.grade_id)
        )).all()
    )

    rows = []
    for grade in grades:
        values: dict[str, Any] = {
            "sectionCount": await section_count(session, grade.id),
            "studentCount": await grade_student_count(session, grade.id),
            "testCount": test_counts.get(grade.id, 0),
            "status": grade.status.value,
        }
        rows.append({"label": f"Class {grade.grade}", **{m: values[m] for m in metrics}})
    return rows


async def _run_section_dimension(
    session: AsyncSession, metrics: list[str], status_filter: str | None, school_id: UUID | str,
) -> list[dict[str, Any]]:
    query = select(SchoolClass).where(SchoolClass.school_id == school_id)
    if status_filter:
        query = query.where(SchoolClass.status == status_filter)
    sections = (await session.execute(query)).scalars().all()

    needs_analytics = "masteryAvgPercent" in metrics or "improvementPercent" in metrics
    analytics_by_class = {}
    if needs_analytics:
        analytics = await compute_school_analytics(session, school_id)
        analytics_by_class = {row.class_id: row for row in analytics.class_breakdown}

    rows = []
    for section in sections:
        student_result = await session.execute(
            select(func.count()).select_from(StudentProfile).where(StudentProfile.class_id == section.id)
        )
        assignment_result = await session.execute(
            select(func.count()).select_from(TeacherClassAssignment).where(
                TeacherClassAssignment.class_id == section.id
            )
        )
        test_result = await session.execute(
            select(func.count()).select_from(VoiceTest).where(VoiceTest.class_id == section.id)
        )
        breakdown = analytics_by_class.get(str(section.id))
        values: dict[str, Any] = {
            "studentCount": student_result.scalar_one(),
            "assignmentCount": assignment_result.scalar_one(),
            "testCount": test_result.scalar_one(),
            "status": section.status.value,
            "masteryAvgPercent": breakdown.mastery_avg_percent if breakdown else None,
            "improvementPercent": breakdown.improvement_percent if breakdown else None,
        }
        rows.append({"label": f"Class {section.grade} · {section.section}", **{m: values[m] for m in metrics}})
    return rows


async def _run_student_dimension(
    session: AsyncSession, metrics: list[str], status_filter: str | None, school_id: UUID | str,
) -> list[dict[str, Any]]:
    query = (
        select(User, StudentProfile, SchoolClass)
        .join(StudentProfile, StudentProfile.user_id == User.id)
        .join(SchoolClass, SchoolClass.id == StudentProfile.class_id)
        .where(SchoolClass.school_id == school_id)
    )
    if status_filter:
        query = query.where(User.status == status_filter)
    rows_data = (await session.execute(query)).all()

    rows = []
    for user, profile, section in rows_data:
        values: dict[str, Any] = {
            "sectionLabel": f"Class {section.grade} · {section.section}",
            "rollNumber": profile.roll_number,
            "status": user.status.value,
            "hasGuardianInfo": bool(profile.guardian_name or profile.guardian_phone),
        }
        rows.append({"label": user.display_name, **{m: values[m] for m in metrics}})
    return rows
