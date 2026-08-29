import uuid
from datetime import datetime, timezone

import pytest

from shared.auth import AuthenticatedUser
from shared.errors import ForbiddenError, UnauthorizedError

from src.api.deps import get_current_app_user, get_current_user
from src.domain.models import Plan, Role, School, SchoolStatus, Subscription, SubscriptionStatus, User, UserStatus


async def _seed_school(db_session, *, status=SchoolStatus.ACTIVE) -> School:
    school = School(
        name=f"School-{uuid.uuid4()}", board="CBSE", city="Bengaluru", contact_email="a@b.com", status=status,
    )
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


async def _seed_plan(db_session) -> Plan:
    plan = Plan(
        name=f"Plan-{uuid.uuid4()}", price_label="$0", teacher_limit=10, student_limit=100,
        test_limit=None, question_paper_limit=None, active=True,
    )
    db_session.add(plan)
    await db_session.flush()
    return plan


async def _seed_subscription(db_session, school_id, *, status: SubscriptionStatus) -> Subscription:
    plan = await _seed_plan(db_session)
    subscription = Subscription(
        school_id=school_id, plan_id=plan.id, status=status, renews_at=datetime.now(timezone.utc),
    )
    db_session.add(subscription)
    await db_session.flush()
    return subscription


def test_get_current_user_rejects_missing_header(_core_env):
    with pytest.raises(UnauthorizedError):
        get_current_user(authorization=None)


def test_get_current_user_rejects_malformed_header(_core_env):
    with pytest.raises(UnauthorizedError):
        get_current_user(authorization="Token abc")


def test_get_current_user_rejects_invalid_token(_core_env, monkeypatch):
    def fake_verify(token: str):
        raise UnauthorizedError("Invalid or expired authentication token.")

    monkeypatch.setattr("src.api.deps.verify_token", fake_verify)

    with pytest.raises(UnauthorizedError):
        get_current_user(authorization="Bearer bad-token")


def test_get_current_user_returns_user_for_valid_token(_core_env, monkeypatch):
    def fake_verify(token: str):
        assert token == "good-token"
        return AuthenticatedUser(uid="uid-1", email="teacher@example.com", claims={})

    monkeypatch.setattr("src.api.deps.verify_token", fake_verify)

    user = get_current_user(authorization="Bearer good-token")

    assert user.uid == "uid-1"
    assert user.email == "teacher@example.com"


# --- get_current_app_user: school suspension / subscription-status enforcement ---
# Previously a real gap: SUSPENDED schools and CANCELED/PAST_DUE subscriptions
# didn't actually block anything despite the School detail page's own copy in
# nool-super-admin claiming suspension "cuts off API access ... enforced
# server-side." See deps.py's get_current_app_user for the fix.


async def test_get_current_app_user_allows_active_school_no_subscription_yet(db_session):
    """Mid-onboarding grace period - no Subscription row yet is not a block,
    same precedent as get_active_plan's own docstring."""
    school = await _seed_school(db_session, status=SchoolStatus.ACTIVE)
    admin_user = await _seed_school_admin(db_session, school.id)

    result = await get_current_app_user(
        user=AuthenticatedUser(uid=admin_user.firebase_uid, email=admin_user.email, claims={}),
        session=db_session,
    )
    assert result.id == admin_user.id


async def test_get_current_app_user_blocks_suspended_school(db_session):
    school = await _seed_school(db_session, status=SchoolStatus.SUSPENDED)
    admin_user = await _seed_school_admin(db_session, school.id)

    with pytest.raises(ForbiddenError):
        await get_current_app_user(
            user=AuthenticatedUser(uid=admin_user.firebase_uid, email=admin_user.email, claims={}),
            session=db_session,
        )


@pytest.mark.parametrize("status", [SubscriptionStatus.CANCELED, SubscriptionStatus.PAST_DUE])
async def test_get_current_app_user_blocks_inactive_subscription(db_session, status):
    school = await _seed_school(db_session, status=SchoolStatus.ACTIVE)
    admin_user = await _seed_school_admin(db_session, school.id)
    await _seed_subscription(db_session, school.id, status=status)

    with pytest.raises(ForbiddenError):
        await get_current_app_user(
            user=AuthenticatedUser(uid=admin_user.firebase_uid, email=admin_user.email, claims={}),
            session=db_session,
        )


@pytest.mark.parametrize("status", [SubscriptionStatus.TRIAL, SubscriptionStatus.ACTIVE])
async def test_get_current_app_user_allows_active_or_trial_subscription(db_session, status):
    school = await _seed_school(db_session, status=SchoolStatus.ACTIVE)
    admin_user = await _seed_school_admin(db_session, school.id)
    await _seed_subscription(db_session, school.id, status=status)

    result = await get_current_app_user(
        user=AuthenticatedUser(uid=admin_user.firebase_uid, email=admin_user.email, claims={}),
        session=db_session,
    )
    assert result.id == admin_user.id


async def test_get_current_app_user_never_blocks_super_admin(db_session):
    """A Super Admin has no school_id - the whole check is skipped."""
    super_admin = User(
        firebase_uid=f"super-{uuid.uuid4()}", email=f"{uuid.uuid4()}@example.com",
        display_name="Super", role=Role.SUPER_ADMIN, school_id=None, status=UserStatus.ACTIVE,
    )
    db_session.add(super_admin)
    await db_session.flush()

    result = await get_current_app_user(
        user=AuthenticatedUser(uid=super_admin.firebase_uid, email=super_admin.email, claims={}),
        session=db_session,
    )
    assert result.id == super_admin.id
