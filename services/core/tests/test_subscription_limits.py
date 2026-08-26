"""Seat/content limit enforcement - real rows against the dev Postgres via
the db_session fixture (see tests/conftest.py), same pattern as
test_authorization.py's school-scoping tests. Route handlers are called
directly as coroutines rather than through TestClient, for the same
event-loop-isolation reason test_authorization.py documents.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from shared.errors import ConflictError

from src.api.routes import school_admin
from src.api.schemas.school_admin import InviteTeacherIn
from src.domain.models import Plan, School, Subscription, User, UserStatus
from src.services import user_provisioning


@pytest.fixture(autouse=True)
def _fake_provisioning(monkeypatch):
    def fake_create(*, email, display_name, role):
        return user_provisioning.ProvisionedUser(firebase_uid=f"uid-{email}", temp_password="TempPass123")

    monkeypatch.setattr(school_admin, "create_firebase_user", fake_create)


async def _seed_school_with_plan(db_session, *, teacher_limit: int) -> tuple[School, Plan]:
    plan = Plan(
        name=f"Plan-{uuid.uuid4()}", price_label="x", teacher_limit=teacher_limit, student_limit=100,
    )
    db_session.add(plan)
    await db_session.flush()

    school = School(name="Test School", board="CBSE", city="Bengaluru", contact_email="a@b.com")
    db_session.add(school)
    await db_session.flush()

    db_session.add(
        Subscription(
            school_id=school.id, plan_id=plan.id, renews_at=datetime.now(timezone.utc) + timedelta(days=30)
        )
    )
    await db_session.flush()
    return school, plan


async def _seed_school_admin(db_session, school_id) -> User:
    admin = User(
        firebase_uid=f"admin-{uuid.uuid4()}", email=f"{uuid.uuid4()}@example.com",
        display_name="Admin", role=school_admin.Role.SCHOOL_ADMIN, school_id=school_id,
        status=UserStatus.ACTIVE,
    )
    db_session.add(admin)
    await db_session.flush()
    return admin


async def test_invite_teacher_succeeds_under_the_limit(db_session):
    school, _ = await _seed_school_with_plan(db_session, teacher_limit=2)
    admin = await _seed_school_admin(db_session, school.id)

    result = await school_admin.invite_teacher(
        InviteTeacherIn(email="t1@example.com", display_name="T1"), user=admin, session=db_session
    )

    assert result.status == "ACTIVE"
    assert result.temp_password == "TempPass123"


async def test_invite_teacher_rejected_at_the_limit(db_session):
    school, _ = await _seed_school_with_plan(db_session, teacher_limit=1)
    admin = await _seed_school_admin(db_session, school.id)

    await school_admin.invite_teacher(
        InviteTeacherIn(email="t1@example.com", display_name="T1"), user=admin, session=db_session
    )

    with pytest.raises(ConflictError):
        await school_admin.invite_teacher(
            InviteTeacherIn(email="t2@example.com", display_name="T2"), user=admin, session=db_session
        )


async def test_school_subscription_shows_usage_vs_limits(db_session):
    """GET /school/subscription surfaces usage proactively, instead of only
    ever as a 409 at the moment a limit is hit - a null test_limit/
    question_paper_limit (unlimited) must render as None, not 0 or a
    fabricated large number.
    """
    plan = Plan(
        name=f"Plan-{uuid.uuid4()}", price_label="x", teacher_limit=5, student_limit=50,
        test_limit=10, question_paper_limit=None,
    )
    db_session.add(plan)
    await db_session.flush()

    school = School(name="Usage School", board="CBSE", city="Bengaluru", contact_email="a@b.com")
    db_session.add(school)
    await db_session.flush()

    db_session.add(
        Subscription(
            school_id=school.id, plan_id=plan.id, renews_at=datetime.now(timezone.utc) + timedelta(days=30)
        )
    )
    await db_session.flush()

    admin = await _seed_school_admin(db_session, school.id)
    await school_admin.invite_teacher(
        InviteTeacherIn(email="t1@example.com", display_name="T1"), user=admin, session=db_session
    )

    result = await school_admin.get_school_subscription(user=admin, session=db_session)

    assert result.plan_name == plan.name
    assert result.teacher_count == 1
    assert result.teacher_limit == 5
    assert result.student_count == 0
    assert result.student_limit == 50
    assert result.test_count == 0
    assert result.test_limit == 10
    assert result.question_paper_count == 0
    assert result.question_paper_limit is None


async def test_invite_teacher_unrestricted_with_no_subscription(db_session):
    """A school with no Subscription row yet (e.g. mid-onboarding, or one
    of the pre-existing schools from before subscriptions were wired up)
    has no plan to enforce - get_active_plan returns None, so no limit
    check applies.
    """
    school = School(name="No Sub School", board="CBSE", city="Bengaluru", contact_email="a@b.com")
    db_session.add(school)
    await db_session.flush()
    admin = await _seed_school_admin(db_session, school.id)

    result = await school_admin.invite_teacher(
        InviteTeacherIn(email="t1@example.com", display_name="T1"), user=admin, session=db_session
    )
    assert result.status == "ACTIVE"
