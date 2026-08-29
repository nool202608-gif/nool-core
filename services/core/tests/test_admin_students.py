"""Super Admin's cross-tenant Student management (src/api/routes/admin.py)
- mirrors school_admin.py's own Students section, but scoped by an explicit
school_id (list/create/bulk-create/export) or not scoped at all (a
student_id is globally unique, so Super Admin can act on any student at
any school). Real rows against the dev Postgres via db_session, same
pattern as test_admin_teachers.py.
"""

import uuid

import pytest

from shared.errors import ConflictError, NotFoundError

from src.api.routes import admin
from src.api.schemas.school_admin import CreateStudentIn, SendCredentialsEmailIn, UpdateStudentIn
from src.domain.models import Plan, Role, School, SchoolClass, StudentPoints, StudentProfile, Subscription, User, UserStatus
from src.services import user_provisioning
from datetime import datetime, timedelta, timezone


@pytest.fixture(autouse=True)
def _fake_provisioning(monkeypatch):
    def fake_create(*, email, display_name, role):
        return user_provisioning.ProvisionedUser(firebase_uid=f"uid-{email}", temp_password="TempPass123")

    monkeypatch.setattr(admin, "create_firebase_user", fake_create)


async def _seed_super_admin(db_session) -> User:
    super_admin = User(
        firebase_uid=f"super-{uuid.uuid4()}", email=f"{uuid.uuid4()}@example.com",
        display_name="Super", role=Role.SUPER_ADMIN, school_id=None, status=UserStatus.ACTIVE,
    )
    db_session.add(super_admin)
    await db_session.flush()
    return super_admin


async def _seed_school(db_session, *, student_limit: int | None = None) -> School:
    school = School(name=f"School-{uuid.uuid4()}", board="CBSE", city="Bengaluru", contact_email="a@b.com")
    db_session.add(school)
    await db_session.flush()

    if student_limit is not None:
        plan = Plan(name=f"Plan-{uuid.uuid4()}", price_label="x", teacher_limit=100, student_limit=student_limit)
        db_session.add(plan)
        await db_session.flush()
        db_session.add(
            Subscription(
                school_id=school.id, plan_id=plan.id, renews_at=datetime.now(timezone.utc) + timedelta(days=30)
            )
        )
        await db_session.flush()
    return school


async def _seed_class(db_session, school_id, *, grade=5, section=None) -> SchoolClass:
    section = section or f"S{uuid.uuid4().hex[:6]}"
    school_class = SchoolClass(school_id=school_id, grade=grade, section=section)
    db_session.add(school_class)
    await db_session.flush()
    return school_class


async def _seed_student(db_session, school_id, class_id, *, display_name="Student", roll_number=1) -> User:
    student = User(
        firebase_uid=f"student-{uuid.uuid4()}", email=f"{uuid.uuid4()}@example.com",
        display_name=display_name, role=Role.STUDENT, school_id=school_id, status=UserStatus.ACTIVE,
    )
    db_session.add(student)
    await db_session.flush()
    db_session.add(StudentProfile(user_id=student.id, class_id=class_id, roll_number=roll_number))
    await db_session.flush()
    return student


async def test_list_students_as_admin_scoped_to_one_school_only(db_session):
    super_admin = await _seed_super_admin(db_session)
    school_a = await _seed_school(db_session)
    school_b = await _seed_school(db_session)
    class_a = await _seed_class(db_session, school_a.id)
    class_b = await _seed_class(db_session, school_b.id)
    await _seed_student(db_session, school_a.id, class_a.id, display_name="Student A")
    await _seed_student(db_session, school_b.id, class_b.id, display_name="Student B")

    result = await admin.list_students_as_admin(str(school_a.id), class_id=None, _=super_admin, session=db_session)

    assert result.total == 1
    assert result.items[0].display_name == "Student A"


async def test_list_students_as_admin_unknown_school_404s(db_session):
    super_admin = await _seed_super_admin(db_session)
    with pytest.raises(NotFoundError):
        await admin.list_students_as_admin(str(uuid.uuid4()), class_id=None, _=super_admin, session=db_session)


async def test_list_students_as_admin_class_id_filter_narrows_results(db_session):
    """The exact scenario the classId query-param alias bug would silently
    break - without `alias="classId"` this filter would never bind and
    both students would come back regardless of the query param.
    """
    super_admin = await _seed_super_admin(db_session)
    school = await _seed_school(db_session)
    class_1 = await _seed_class(db_session, school.id)
    class_2 = await _seed_class(db_session, school.id)
    await _seed_student(db_session, school.id, class_1.id, display_name="In Class 1", roll_number=1)
    await _seed_student(db_session, school.id, class_2.id, display_name="In Class 2", roll_number=1)

    result = await admin.list_students_as_admin(
        str(school.id), class_id=str(class_1.id), _=super_admin, session=db_session
    )

    assert result.total == 1
    assert result.items[0].display_name == "In Class 1"


async def test_create_student_as_admin_respects_that_schools_plan_limit(db_session):
    super_admin = await _seed_super_admin(db_session)
    school = await _seed_school(db_session, student_limit=1)
    school_class = await _seed_class(db_session, school.id)

    result = await admin.create_student_as_admin(
        str(school.id),
        CreateStudentIn(display_name="S1", email=f"{uuid.uuid4()}@example.com", class_id=str(school_class.id), roll_number=1),
        actor=super_admin, session=db_session,
    )
    assert result.status == "ACTIVE"
    assert result.temp_password == "TempPass123"

    with pytest.raises(ConflictError):
        await admin.create_student_as_admin(
            str(school.id),
            CreateStudentIn(
                display_name="S2", email=f"{uuid.uuid4()}@example.com", class_id=str(school_class.id), roll_number=2
            ),
            actor=super_admin, session=db_session,
        )


async def test_create_student_as_admin_unrestricted_with_no_subscription(db_session):
    super_admin = await _seed_super_admin(db_session)
    school = await _seed_school(db_session)
    school_class = await _seed_class(db_session, school.id)

    result = await admin.create_student_as_admin(
        str(school.id),
        CreateStudentIn(display_name="S1", email=f"{uuid.uuid4()}@example.com", class_id=str(school_class.id), roll_number=1),
        actor=super_admin, session=db_session,
    )
    assert result.status == "ACTIVE"


async def test_update_student_as_admin_no_school_filter(db_session):
    super_admin = await _seed_super_admin(db_session)
    school = await _seed_school(db_session)
    school_class = await _seed_class(db_session, school.id)
    student = await _seed_student(db_session, school.id, school_class.id)

    out = await admin.update_student_as_admin(
        str(student.id), UpdateStudentIn(display_name="Renamed"), actor=super_admin, session=db_session
    )
    assert out.display_name == "Renamed"


async def test_update_student_as_admin_unknown_student_404s(db_session):
    super_admin = await _seed_super_admin(db_session)
    with pytest.raises(NotFoundError):
        await admin.update_student_as_admin(
            str(uuid.uuid4()), UpdateStudentIn(display_name="X"), actor=super_admin, session=db_session
        )


async def test_reset_student_password_as_admin_issues_new_temp_password(db_session, monkeypatch):
    super_admin = await _seed_super_admin(db_session)
    school = await _seed_school(db_session)
    school_class = await _seed_class(db_session, school.id)
    student = await _seed_student(db_session, school.id, school_class.id)
    student.must_change_password = False
    await db_session.flush()

    def fake_reset(*, firebase_uid, role):
        return "NewTempPass456"

    monkeypatch.setattr(admin, "reset_password", fake_reset)

    out = await admin.reset_student_password_as_admin(str(student.id), actor=super_admin, session=db_session)

    assert out.temp_password == "NewTempPass456"
    assert student.must_change_password is True


async def test_send_student_credentials_email_as_admin_no_smtp_conflicts(db_session):
    """No SMTP configured in the test environment, so send_email raises
    ConflictError rather than silently no-op'ing - confirming this
    cross-tenant path calls through to the same real send_email.
    """
    super_admin = await _seed_super_admin(db_session)
    school = await _seed_school(db_session)
    school_class = await _seed_class(db_session, school.id)
    student = await _seed_student(db_session, school.id, school_class.id)

    with pytest.raises(ConflictError):
        await admin.send_student_credentials_email_as_admin(
            str(student.id),
            SendCredentialsEmailIn(subject="Hi", message="Your password", temp_password="x"),
            actor=super_admin, session=db_session,
        )


async def test_delete_student_as_admin_blocks_when_student_has_activity(db_session):
    super_admin = await _seed_super_admin(db_session)
    school = await _seed_school(db_session)
    school_class = await _seed_class(db_session, school.id)
    student = await _seed_student(db_session, school.id, school_class.id)
    db_session.add(StudentPoints(student_id=student.id, points=10))
    await db_session.flush()

    with pytest.raises(ConflictError):
        await admin.delete_student_as_admin(str(student.id), actor=super_admin, session=db_session)


async def test_delete_student_as_admin_deletes_when_no_activity(db_session):
    super_admin = await _seed_super_admin(db_session)
    school = await _seed_school(db_session)
    school_class = await _seed_class(db_session, school.id)
    student = await _seed_student(db_session, school.id, school_class.id)

    result = await admin.delete_student_as_admin(str(student.id), actor=super_admin, session=db_session)
    assert result == {"deleted": True}

    # Idempotent: deleting again (already gone) still reports deleted=True.
    result2 = await admin.delete_student_as_admin(str(student.id), actor=super_admin, session=db_session)
    assert result2 == {"deleted": True}


async def test_export_students_as_admin_returns_csv(db_session):
    super_admin = await _seed_super_admin(db_session)
    school = await _seed_school(db_session)
    school_class = await _seed_class(db_session, school.id)
    await _seed_student(db_session, school.id, school_class.id, display_name="CSV Student")

    response = await admin.export_students_as_admin(str(school.id), _=super_admin, session=db_session)
    body = response.body.decode()
    assert "CSV Student" in body
    assert response.media_type == "text/csv"
