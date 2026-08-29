"""The pivot-reporting engine: src/services/reporting.py's dimension/metric
registry + execution, plus both route surfaces (school_admin.py's own-school
reports, admin.py's cross-tenant reports + configuration persistence +
cross-school sharing). Real rows against the dev Postgres via db_session,
same pattern as test_grades.py.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from shared.errors import ForbiddenError, NotFoundError, ValidationError

from src.api.routes import admin, school_admin
from src.api.schemas.reporting import CreateReportConfigurationIn, CreateReportShareIn, RunReportIn
from src.domain.models import (
    Plan,
    ReportConfiguration,
    ReportShare,
    Role,
    School,
    SchoolClass,
    SchoolGrade,
    SchoolStatus,
    StudentProfile,
    Subscription,
    SubscriptionStatus,
    User,
    UserStatus,
)
from src.services import reporting


async def _seed_super_admin(db_session) -> User:
    super_admin = User(
        firebase_uid=f"super-{uuid.uuid4()}", email=f"{uuid.uuid4()}@example.com",
        display_name="Super", role=Role.SUPER_ADMIN, school_id=None, status=UserStatus.ACTIVE,
    )
    db_session.add(super_admin)
    await db_session.flush()
    return super_admin


async def _seed_school(db_session) -> School:
    school = School(name=f"School-{uuid.uuid4()}", board="CBSE", city="Bengaluru", contact_email="a@b.com")
    db_session.add(school)
    await db_session.flush()
    return school


async def _seed_school_admin(db_session, school_id) -> User:
    admin_user = User(
        firebase_uid=f"admin-{uuid.uuid4()}", email=f"{uuid.uuid4()}@example.com",
        display_name="Admin", role=Role.SCHOOL_ADMIN, school_id=school_id, status=UserStatus.ACTIVE,
    )
    db_session.add(admin_user)
    await db_session.flush()
    return admin_user


async def _seed_grade(db_session, school_id, *, grade=5) -> SchoolGrade:
    school_grade = SchoolGrade(school_id=school_id, grade=grade)
    db_session.add(school_grade)
    await db_session.flush()
    return school_grade


async def _seed_section(db_session, school_id, *, grade=5, section=None, grade_id=None) -> SchoolClass:
    section = section or f"S{uuid.uuid4().hex[:8]}"
    school_class = SchoolClass(school_id=school_id, grade=grade, section=section, grade_id=grade_id)
    db_session.add(school_class)
    await db_session.flush()
    return school_class


async def _seed_student(db_session, school_id, class_id, *, roll_number=1) -> User:
    student = User(
        firebase_uid=f"student-{uuid.uuid4()}", email=f"{uuid.uuid4()}@example.com",
        display_name="Student", role=Role.STUDENT, school_id=school_id, status=UserStatus.ACTIVE,
    )
    db_session.add(student)
    await db_session.flush()
    db_session.add(StudentProfile(user_id=student.id, class_id=class_id, roll_number=roll_number))
    await db_session.flush()
    return student


async def _seed_plan(db_session) -> Plan:
    plan = Plan(
        name=f"Plan-{uuid.uuid4()}", price_label="$0", teacher_limit=10, student_limit=100,
        test_limit=None, question_paper_limit=None, active=True,
    )
    db_session.add(plan)
    await db_session.flush()
    return plan


async def _seed_subscription(db_session, school_id, plan_id, *, status=SubscriptionStatus.ACTIVE) -> Subscription:
    sub = Subscription(school_id=school_id, plan_id=plan_id, status=status, renews_at=datetime.now(timezone.utc))
    db_session.add(sub)
    await db_session.flush()
    return sub


# --- Dimension/metric validation --------------------------------------------


def test_validate_dimension_and_metrics_rejects_unknown_dimension():
    with pytest.raises(ValidationError):
        reporting.validate_dimension_and_metrics("NOT_A_DIMENSION", ["studentCount"])


def test_validate_dimension_and_metrics_rejects_unknown_metric():
    with pytest.raises(ValidationError):
        reporting.validate_dimension_and_metrics("SCHOOL", ["notAMetric"])


def test_validate_dimension_and_metrics_rejects_empty_metrics():
    with pytest.raises(ValidationError):
        reporting.validate_dimension_and_metrics("SCHOOL", [])


def test_validate_dimension_and_metrics_accepts_valid_input():
    spec = reporting.validate_dimension_and_metrics("SCHOOL", ["studentCount", "teacherCount"])
    assert spec.key == "SCHOOL"


# --- run_report: SCHOOL dimension (platform-wide) ---------------------------


async def test_run_report_school_dimension_counts_are_real(db_session):
    school = await _seed_school(db_session)
    admin_user = await _seed_school_admin(db_session, school.id)
    grade = await _seed_grade(db_session, school.id)
    section = await _seed_section(db_session, school.id, grade_id=grade.id)
    await _seed_student(db_session, school.id, section.id)

    rows = await reporting.run_report(
        db_session, dimension="SCHOOL", metrics=["teacherCount", "studentCount", "gradeCount", "sectionCount"],
        filters={}, school_id=None,
    )
    row = next(r for r in rows if r["label"] == school.name)
    assert row["studentCount"] == 1
    assert row["gradeCount"] == 1
    assert row["sectionCount"] == 1


async def test_run_report_school_dimension_filters_by_status(db_session):
    active_school = await _seed_school(db_session)
    suspended_school = School(
        name=f"Suspended-{uuid.uuid4()}", board="CBSE", city="B", contact_email="a@b.com",
        status=SchoolStatus.SUSPENDED,
    )
    db_session.add(suspended_school)
    await db_session.flush()

    rows = await reporting.run_report(
        db_session, dimension="SCHOOL", metrics=["status"], filters={"status": "SUSPENDED"}, school_id=None,
    )
    labels = {r["label"] for r in rows}
    assert suspended_school.name in labels
    assert active_school.name not in labels


async def test_run_report_school_dimension_filters_by_plan(db_session):
    school_a = await _seed_school(db_session)
    school_b = await _seed_school(db_session)
    plan = await _seed_plan(db_session)
    await _seed_subscription(db_session, school_a.id, plan.id)

    rows = await reporting.run_report(
        db_session, dimension="SCHOOL", metrics=["planName"], filters={"planId": str(plan.id)}, school_id=None,
    )
    labels = {r["label"] for r in rows}
    assert school_a.name in labels
    assert school_b.name not in labels


async def test_run_report_school_dimension_reflects_subscription_status(db_session):
    school = await _seed_school(db_session)
    plan = await _seed_plan(db_session)
    await _seed_subscription(db_session, school.id, plan.id, status=SubscriptionStatus.CANCELED)

    rows = await reporting.run_report(
        db_session, dimension="SCHOOL", metrics=["subscriptionStatus", "planName"], filters={}, school_id=None,
    )
    row = next(r for r in rows if r["label"] == school.name)
    assert row["subscriptionStatus"] == "CANCELED"
    assert row["planName"] == plan.name


# --- run_report: PLAN dimension ---------------------------------------------


async def test_run_report_plan_dimension_counts_schools(db_session):
    plan = await _seed_plan(db_session)
    school_a = await _seed_school(db_session)
    school_b = await _seed_school(db_session)
    await _seed_subscription(db_session, school_a.id, plan.id)
    await _seed_subscription(db_session, school_b.id, plan.id)

    rows = await reporting.run_report(
        db_session, dimension="PLAN", metrics=["schoolCount", "teacherLimit"], filters={}, school_id=None,
    )
    row = next(r for r in rows if r["label"] == plan.name)
    assert row["schoolCount"] == 2
    assert row["teacherLimit"] == plan.teacher_limit


# --- run_report: SCHOOL-scoped dimensions require a school_id --------------


async def test_run_report_school_scoped_dimension_requires_school_id():
    with pytest.raises(ValidationError):
        await reporting.run_report(
            None, dimension="CLASS", metrics=["studentCount"], filters={}, school_id=None,
        )


async def test_run_report_class_dimension(db_session):
    school = await _seed_school(db_session)
    grade = await _seed_grade(db_session, school.id, grade=9)
    section_a = await _seed_section(db_session, school.id, grade=9, grade_id=grade.id)
    await _seed_section(db_session, school.id, grade=9, grade_id=grade.id)
    await _seed_student(db_session, school.id, section_a.id)

    rows = await reporting.run_report(
        db_session, dimension="CLASS", metrics=["sectionCount", "studentCount"], filters={}, school_id=school.id,
    )
    row = next(r for r in rows if r["label"] == f"Class {grade.grade}")
    assert row["sectionCount"] == 2
    assert row["studentCount"] == 1


async def test_run_report_class_dimension_scoped_to_one_school(db_session):
    school_a = await _seed_school(db_session)
    school_b = await _seed_school(db_session)
    await _seed_grade(db_session, school_a.id, grade=6)
    await _seed_grade(db_session, school_b.id, grade=7)

    rows = await reporting.run_report(
        db_session, dimension="CLASS", metrics=["status"], filters={}, school_id=school_a.id,
    )
    assert len(rows) == 1
    assert rows[0]["label"] == "Class 6"


async def test_run_report_section_dimension_real_counts(db_session):
    school = await _seed_school(db_session)
    section = await _seed_section(db_session, school.id, grade=8, section="A")
    student_a = await _seed_student(db_session, school.id, section.id, roll_number=1)
    await _seed_student(db_session, school.id, section.id, roll_number=2)

    rows = await reporting.run_report(
        db_session, dimension="SECTION", metrics=["studentCount", "assignmentCount"], filters={},
        school_id=school.id,
    )
    row = next(r for r in rows if r["label"] == "Class 8 · A")
    assert row["studentCount"] == 2
    assert row["assignmentCount"] == 0
    assert student_a is not None  # seeded, used above for count


async def test_run_report_section_dimension_mastery_metrics_default_to_zero_when_unassessed(db_session):
    """Honest state, not a bug: no StudentTestResult rows exist without a
    completed Voice Test, so this correctly reads 0 (compute_school_analytics'
    own established coalescing behavior, reused as-is here) rather than a
    fabricated non-zero number."""
    school = await _seed_school(db_session)
    await _seed_section(db_session, school.id, grade=8, section="B")

    rows = await reporting.run_report(
        db_session, dimension="SECTION", metrics=["masteryAvgPercent", "improvementPercent"], filters={},
        school_id=school.id,
    )
    assert rows[0]["masteryAvgPercent"] == 0
    assert rows[0]["improvementPercent"] == 0


async def test_run_report_student_dimension(db_session):
    school = await _seed_school(db_session)
    section = await _seed_section(db_session, school.id, grade=4, section="C")
    student = await _seed_student(db_session, school.id, section.id, roll_number=7)

    rows = await reporting.run_report(
        db_session, dimension="STUDENT", metrics=["sectionLabel", "rollNumber", "hasGuardianInfo"], filters={},
        school_id=school.id,
    )
    row = next(r for r in rows if r["label"] == student.display_name)
    assert row["sectionLabel"] == "Class 4 · C"
    assert row["rollNumber"] == 7
    assert row["hasGuardianInfo"] is False


# --- Routes: Super Admin -----------------------------------------------------


async def test_run_report_as_admin_route(db_session):
    super_admin = await _seed_super_admin(db_session)
    school = await _seed_school(db_session)

    result = await admin.run_report_as_admin(
        RunReportIn(dimension="SCHOOL", metrics=["studentCount"], filters={}),
        _=super_admin, session=db_session,
    )
    assert any(r["label"] == school.name for r in result.rows)


async def test_create_list_delete_report_config_as_admin(db_session):
    super_admin = await _seed_super_admin(db_session)

    created = await admin.create_report_config_as_admin(
        CreateReportConfigurationIn(name="My report", dimension="SCHOOL", metrics=["studentCount"]),
        actor=super_admin, session=db_session,
    )
    assert created.name == "My report"

    listed = await admin.list_report_configs_as_admin(actor=super_admin, session=db_session)
    assert any(c.id == created.id for c in listed.items)

    result = await admin.delete_report_config_as_admin(created.id, actor=super_admin, session=db_session)
    assert result == {"deleted": True}
    listed_after = await admin.list_report_configs_as_admin(actor=super_admin, session=db_session)
    assert not any(c.id == created.id for c in listed_after.items)


async def test_create_report_config_rejects_invalid_dimension(db_session):
    super_admin = await _seed_super_admin(db_session)
    with pytest.raises(ValidationError):
        await admin.create_report_config_as_admin(
            CreateReportConfigurationIn(name="Bad", dimension="NOPE", metrics=["x"]),
            actor=super_admin, session=db_session,
        )


async def test_report_configs_are_owner_scoped_for_admin(db_session):
    admin_a = await _seed_super_admin(db_session)
    admin_b = await _seed_super_admin(db_session)
    await admin.create_report_config_as_admin(
        CreateReportConfigurationIn(name="A's report", dimension="SCHOOL", metrics=["studentCount"]),
        actor=admin_a, session=db_session,
    )

    listed_b = await admin.list_report_configs_as_admin(actor=admin_b, session=db_session)
    assert listed_b.total == 0


async def test_delete_report_config_unknown_id_404s(db_session):
    super_admin = await _seed_super_admin(db_session)
    with pytest.raises(NotFoundError):
        await admin._get_own_report_config(db_session, str(uuid.uuid4()), super_admin.id)


# --- Sharing -----------------------------------------------------------------


async def test_share_report_and_school_admin_sees_it(db_session):
    super_admin = await _seed_super_admin(db_session)
    school = await _seed_school(db_session)
    admin_user = await _seed_school_admin(db_session, school.id)

    config = await admin.create_report_config_as_admin(
        CreateReportConfigurationIn(name="Shared report", dimension="SCHOOL", metrics=["studentCount"]),
        actor=super_admin, session=db_session,
    )
    share = await admin.create_report_share_as_admin(
        config.id, CreateReportShareIn(shared_with_school_id=str(school.id), access_level="VIEW_EXPORT"),
        actor=super_admin, session=db_session,
    )
    assert share.shared_with_school_name == school.name

    shared = await school_admin.list_shared_reports(user=admin_user, session=db_session)
    assert shared.total == 1
    assert shared.items[0].share_id == share.id
    assert shared.items[0].access_level == "VIEW_EXPORT"

    run_result = await school_admin.run_shared_report(share.id, user=admin_user, session=db_session)
    assert run_result.dimension == "SCHOOL"


async def test_shared_report_not_visible_to_a_different_school(db_session):
    super_admin = await _seed_super_admin(db_session)
    school_a = await _seed_school(db_session)
    school_b = await _seed_school(db_session)
    admin_b = await _seed_school_admin(db_session, school_b.id)

    config = await admin.create_report_config_as_admin(
        CreateReportConfigurationIn(name="Report", dimension="SCHOOL", metrics=["studentCount"]),
        actor=super_admin, session=db_session,
    )
    await admin.create_report_share_as_admin(
        config.id, CreateReportShareIn(shared_with_school_id=str(school_a.id)),
        actor=super_admin, session=db_session,
    )

    shared = await school_admin.list_shared_reports(user=admin_b, session=db_session)
    assert shared.total == 0


async def test_expired_share_is_not_visible_or_runnable(db_session):
    super_admin = await _seed_super_admin(db_session)
    school = await _seed_school(db_session)
    admin_user = await _seed_school_admin(db_session, school.id)

    config = await admin.create_report_config_as_admin(
        CreateReportConfigurationIn(name="Expiring", dimension="SCHOOL", metrics=["studentCount"]),
        actor=super_admin, session=db_session,
    )
    db_session.add(ReportShare(
        report_configuration_id=config.id, shared_by=super_admin.id, shared_with_school_id=school.id,
        access_level="VIEW", expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    ))
    await db_session.flush()
    expired = (await db_session.execute(
        select(ReportShare).where(ReportShare.report_configuration_id == config.id)
    )).scalar_one()

    shared = await school_admin.list_shared_reports(user=admin_user, session=db_session)
    assert shared.total == 0

    with pytest.raises(NotFoundError):
        await school_admin.run_shared_report(str(expired.id), user=admin_user, session=db_session)


async def test_view_only_share_cannot_be_exported(db_session):
    super_admin = await _seed_super_admin(db_session)
    school = await _seed_school(db_session)
    admin_user = await _seed_school_admin(db_session, school.id)

    config = await admin.create_report_config_as_admin(
        CreateReportConfigurationIn(name="View only", dimension="SCHOOL", metrics=["studentCount"]),
        actor=super_admin, session=db_session,
    )
    share = await admin.create_report_share_as_admin(
        config.id, CreateReportShareIn(shared_with_school_id=str(school.id), access_level="VIEW"),
        actor=super_admin, session=db_session,
    )

    with pytest.raises(ForbiddenError):
        await school_admin.export_shared_report(share.id, user=admin_user, session=db_session)


async def test_revoke_report_share(db_session):
    super_admin = await _seed_super_admin(db_session)
    school = await _seed_school(db_session)
    admin_user = await _seed_school_admin(db_session, school.id)

    config = await admin.create_report_config_as_admin(
        CreateReportConfigurationIn(name="Revocable", dimension="SCHOOL", metrics=["studentCount"]),
        actor=super_admin, session=db_session,
    )
    share = await admin.create_report_share_as_admin(
        config.id, CreateReportShareIn(shared_with_school_id=str(school.id)),
        actor=super_admin, session=db_session,
    )

    result = await admin.delete_report_share_as_admin(share.id, actor=super_admin, session=db_session)
    assert result == {"deleted": True}

    shared = await school_admin.list_shared_reports(user=admin_user, session=db_session)
    assert shared.total == 0


async def test_deleting_report_config_also_deletes_its_shares(db_session):
    super_admin = await _seed_super_admin(db_session)
    school = await _seed_school(db_session)

    config = await admin.create_report_config_as_admin(
        CreateReportConfigurationIn(name="Cascade", dimension="SCHOOL", metrics=["studentCount"]),
        actor=super_admin, session=db_session,
    )
    await admin.create_report_share_as_admin(
        config.id, CreateReportShareIn(shared_with_school_id=str(school.id)),
        actor=super_admin, session=db_session,
    )

    await admin.delete_report_config_as_admin(config.id, actor=super_admin, session=db_session)

    remaining = await db_session.execute(
        select(ReportShare).where(ReportShare.report_configuration_id == config.id)
    )
    assert remaining.scalar_one_or_none() is None


# --- Routes: School Admin -----------------------------------------------------


async def test_school_report_dimensions_excludes_platform_scope(db_session):
    dims = await school_admin.list_school_report_dimensions(_=None)
    keys = {d.key for d in dims}
    assert "SCHOOL" not in keys
    assert "PLAN" not in keys
    assert "SECTION" in keys


async def test_run_school_report_forces_own_school(db_session):
    school_a = await _seed_school(db_session)
    school_b = await _seed_school(db_session)
    admin_a = await _seed_school_admin(db_session, school_a.id)
    await _seed_grade(db_session, school_a.id, grade=3)
    await _seed_grade(db_session, school_b.id, grade=4)

    result = await school_admin.run_school_report(
        RunReportIn(dimension="CLASS", metrics=["status"], school_id=str(school_b.id)),
        user=admin_a, session=db_session,
    )
    labels = {r["label"] for r in result.rows}
    assert labels == {"Class 3"}


async def test_school_report_config_scoped_to_school_not_owner(db_session):
    school = await _seed_school(db_session)
    admin_a = await _seed_school_admin(db_session, school.id)
    admin_b = await _seed_school_admin(db_session, school.id)

    created = await school_admin.create_school_report_config(
        CreateReportConfigurationIn(name="Team report", dimension="SECTION", metrics=["studentCount"]),
        user=admin_a, session=db_session,
    )
    listed_by_other_admin_same_school = await school_admin.list_school_report_configs(
        user=admin_b, session=db_session
    )
    assert any(c.id == created.id for c in listed_by_other_admin_same_school.items)


async def test_school_report_config_not_visible_to_another_school(db_session):
    school_a = await _seed_school(db_session)
    school_b = await _seed_school(db_session)
    admin_a = await _seed_school_admin(db_session, school_a.id)
    admin_b = await _seed_school_admin(db_session, school_b.id)

    await school_admin.create_school_report_config(
        CreateReportConfigurationIn(name="A only", dimension="SECTION", metrics=["studentCount"]),
        user=admin_a, session=db_session,
    )
    listed_b = await school_admin.list_school_report_configs(user=admin_b, session=db_session)
    assert listed_b.total == 0
