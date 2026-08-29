"""Super Admin's cross-tenant Teacher management (src/api/routes/admin.py)
- mirrors school_admin.py's own Teachers section, but scoped by an explicit
school_id (list/invite/bulk-invite/export) or not scoped at all (a
teacher_id is globally unique, so Super Admin can act on any teacher at
any school). Real rows against the dev Postgres via db_session, same
pattern as test_subscription_limits.py/test_school_oversight.py.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from shared.errors import ConflictError, NotFoundError

from src.api.routes import admin
from src.api.schemas.school_admin import (
    InviteTeacherIn,
    SendCredentialsEmailIn,
    UpdateTeacherIn,
    UpdateTeacherStatusIn,
)
from src.domain.models import (
    AssistantMessage,
    ChatRole,
    Plan,
    Role,
    School,
    Subscription,
    User,
    UserStatus,
)
from src.services import user_provisioning


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


async def _seed_school(db_session, *, teacher_limit: int | None = None) -> School:
    school = School(name=f"School-{uuid.uuid4()}", board="CBSE", city="Bengaluru", contact_email="a@b.com")
    db_session.add(school)
    await db_session.flush()

    if teacher_limit is not None:
        plan = Plan(name=f"Plan-{uuid.uuid4()}", price_label="x", teacher_limit=teacher_limit, student_limit=100)
        db_session.add(plan)
        await db_session.flush()
        db_session.add(
            Subscription(
                school_id=school.id, plan_id=plan.id, renews_at=datetime.now(timezone.utc) + timedelta(days=30)
            )
        )
        await db_session.flush()
    return school


async def _seed_teacher(db_session, school_id, *, display_name="Teacher") -> User:
    teacher = User(
        firebase_uid=f"teacher-{uuid.uuid4()}", email=f"{uuid.uuid4()}@example.com",
        display_name=display_name, role=Role.TEACHER, school_id=school_id, status=UserStatus.ACTIVE,
    )
    db_session.add(teacher)
    await db_session.flush()
    return teacher


async def test_list_teachers_as_admin_scoped_to_one_school_only(db_session):
    super_admin = await _seed_super_admin(db_session)
    school_a = await _seed_school(db_session)
    school_b = await _seed_school(db_session)
    await _seed_teacher(db_session, school_a.id, display_name="Teacher A")
    await _seed_teacher(db_session, school_b.id, display_name="Teacher B")

    result = await admin.list_teachers_as_admin(str(school_a.id), _=super_admin, session=db_session)

    assert result.total == 1
    assert result.items[0].display_name == "Teacher A"


async def test_list_teachers_as_admin_unknown_school_404s(db_session):
    super_admin = await _seed_super_admin(db_session)
    with pytest.raises(NotFoundError):
        await admin.list_teachers_as_admin(str(uuid.uuid4()), _=super_admin, session=db_session)


async def test_invite_teacher_as_admin_respects_that_schools_plan_limit(db_session):
    super_admin = await _seed_super_admin(db_session)
    school = await _seed_school(db_session, teacher_limit=1)

    email1 = f"{uuid.uuid4()}@example.com"
    result = await admin.invite_teacher_as_admin(
        str(school.id), InviteTeacherIn(email=email1, display_name="T1"), actor=super_admin, session=db_session
    )
    assert result.status == "ACTIVE"
    assert result.temp_password == "TempPass123"

    with pytest.raises(ConflictError):
        await admin.invite_teacher_as_admin(
            str(school.id),
            InviteTeacherIn(email=f"{uuid.uuid4()}@example.com", display_name="T2"),
            actor=super_admin, session=db_session,
        )


async def test_invite_teacher_as_admin_unrestricted_with_no_subscription(db_session):
    super_admin = await _seed_super_admin(db_session)
    school = await _seed_school(db_session)

    result = await admin.invite_teacher_as_admin(
        str(school.id),
        InviteTeacherIn(email=f"{uuid.uuid4()}@example.com", display_name="T1"),
        actor=super_admin, session=db_session,
    )
    assert result.status == "ACTIVE"


async def test_update_teacher_status_as_admin_round_trips(db_session):
    super_admin = await _seed_super_admin(db_session)
    school = await _seed_school(db_session)
    teacher = await _seed_teacher(db_session, school.id)

    out = await admin.update_teacher_status_as_admin(
        str(teacher.id), UpdateTeacherStatusIn(status=UserStatus.DEACTIVATED), actor=super_admin, session=db_session
    )
    assert out.status == UserStatus.DEACTIVATED

    out2 = await admin.update_teacher_status_as_admin(
        str(teacher.id), UpdateTeacherStatusIn(status=UserStatus.ACTIVE), actor=super_admin, session=db_session
    )
    assert out2.status == UserStatus.ACTIVE


async def test_update_teacher_as_admin_no_school_filter(db_session):
    super_admin = await _seed_super_admin(db_session)
    school = await _seed_school(db_session)
    teacher = await _seed_teacher(db_session, school.id)

    out = await admin.update_teacher_as_admin(
        str(teacher.id), UpdateTeacherIn(display_name="Renamed"), actor=super_admin, session=db_session
    )
    assert out.display_name == "Renamed"


async def test_update_teacher_as_admin_unknown_teacher_404s(db_session):
    super_admin = await _seed_super_admin(db_session)
    with pytest.raises(NotFoundError):
        await admin.update_teacher_as_admin(
            str(uuid.uuid4()), UpdateTeacherIn(display_name="X"), actor=super_admin, session=db_session
        )


async def test_reset_teacher_password_as_admin_issues_new_temp_password(db_session, monkeypatch):
    super_admin = await _seed_super_admin(db_session)
    school = await _seed_school(db_session)
    teacher = await _seed_teacher(db_session, school.id)
    teacher.must_change_password = False
    await db_session.flush()

    def fake_reset(*, firebase_uid, role):
        return "NewTempPass456"

    monkeypatch.setattr(admin, "reset_password", fake_reset)

    out = await admin.reset_teacher_password_as_admin(str(teacher.id), actor=super_admin, session=db_session)

    assert out.temp_password == "NewTempPass456"
    assert teacher.must_change_password is True


async def test_send_teacher_credentials_email_as_admin_no_smtp_conflicts(db_session):
    """No SMTP configured in the test environment, so send_email raises
    ConflictError rather than silently no-op'ing - same behavior
    school_admin.py's own endpoint has, just confirming this cross-tenant
    path calls through to the same real send_email.
    """
    super_admin = await _seed_super_admin(db_session)
    school = await _seed_school(db_session)
    teacher = await _seed_teacher(db_session, school.id)

    with pytest.raises(ConflictError):
        await admin.send_teacher_credentials_email_as_admin(
            str(teacher.id),
            SendCredentialsEmailIn(subject="Hi", message="Your password", temp_password="x"),
            actor=super_admin, session=db_session,
        )


async def test_delete_teacher_as_admin_blocks_when_teacher_has_content(db_session):
    super_admin = await _seed_super_admin(db_session)
    school = await _seed_school(db_session)
    teacher = await _seed_teacher(db_session, school.id)
    db_session.add(AssistantMessage(teacher_id=teacher.id, role=ChatRole.USER, text="hi"))
    await db_session.flush()

    with pytest.raises(ConflictError):
        await admin.delete_teacher_as_admin(str(teacher.id), actor=super_admin, session=db_session)


async def test_delete_teacher_as_admin_deletes_when_no_content(db_session):
    super_admin = await _seed_super_admin(db_session)
    school = await _seed_school(db_session)
    teacher = await _seed_teacher(db_session, school.id)

    result = await admin.delete_teacher_as_admin(str(teacher.id), actor=super_admin, session=db_session)
    assert result == {"deleted": True}

    # Idempotent: deleting again (already gone) still reports deleted=True.
    result2 = await admin.delete_teacher_as_admin(str(teacher.id), actor=super_admin, session=db_session)
    assert result2 == {"deleted": True}


async def test_export_teachers_as_admin_returns_csv(db_session):
    super_admin = await _seed_super_admin(db_session)
    school = await _seed_school(db_session)
    await _seed_teacher(db_session, school.id, display_name="CSV Teacher")

    response = await admin.export_teachers_as_admin(str(school.id), _=super_admin, session=db_session)
    body = response.body.decode()
    assert "CSV Teacher" in body
    assert response.media_type == "text/csv"
