"""Feature entitlements (requirements.md §7.14) - the `require_feature`
dependency, the plan-only logic in src/services/feature_entitlements.py,
and the admin GET/PUT endpoints that set Plan.enabled_features. Real rows
against the dev Postgres via the db_session fixture, same pattern as
test_subscription_limits.py.

Deliberately a single control point (the plan/subscription), not also
settable per-school - see Plan.enabled_features' docstring.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from shared.auth import AuthenticatedUser
from shared.errors import ForbiddenError

from src.api.deps import require_feature
from src.api.routes import admin, profile
from src.api.schemas.features import UpdateFeaturesIn
from src.domain.models import AuditLog, Feature, Plan, Role, School, Subscription, User, UserStatus
from src.services.feature_entitlements import effective_enabled_features, is_feature_enabled


async def _seed_school(db_session) -> School:
    school = School(name="Test School", board="CBSE", city="Bengaluru", contact_email="a@b.com")
    db_session.add(school)
    await db_session.flush()
    return school


async def _seed_school_with_plan(db_session, *, enabled_features=None) -> tuple[School, Plan]:
    plan = Plan(
        name=f"Plan-{uuid.uuid4()}", price_label="x", teacher_limit=10, student_limit=100,
        enabled_features=enabled_features,
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


async def _seed_teacher(db_session, school_id) -> User:
    teacher = User(
        firebase_uid=f"teacher-{uuid.uuid4()}", email=f"{uuid.uuid4()}@example.com",
        display_name="Teacher", role=Role.TEACHER, school_id=school_id, status=UserStatus.ACTIVE,
    )
    db_session.add(teacher)
    await db_session.flush()
    return teacher


async def _seed_super_admin(db_session) -> User:
    super_admin = User(
        firebase_uid=f"super-{uuid.uuid4()}", email=f"{uuid.uuid4()}@example.com",
        display_name="Super", role=Role.SUPER_ADMIN, school_id=None, status=UserStatus.ACTIVE,
    )
    db_session.add(super_admin)
    await db_session.flush()
    return super_admin


# --- effective_enabled_features / is_feature_enabled (plan-only) ---

def test_effective_features_none_when_plan_has_no_restriction():
    assert effective_enabled_features(plan=None) is None

    plan = Plan(name="p", price_label="x", teacher_limit=1, student_limit=1)
    assert effective_enabled_features(plan=plan) is None


def test_effective_features_reflects_the_plans_allow_list():
    plan = Plan(
        name="p", price_label="x", teacher_limit=1, student_limit=1,
        enabled_features=["question_paper", "voice_test"],
    )
    assert effective_enabled_features(plan=plan) == [Feature.QUESTION_PAPER, Feature.VOICE_TEST]


def test_is_feature_enabled_respects_the_plans_allow_list():
    plan = Plan(name="p", price_label="x", teacher_limit=1, student_limit=1, enabled_features=["question_paper"])
    assert is_feature_enabled(Feature.QUESTION_PAPER, plan=plan) is True
    assert is_feature_enabled(Feature.VOICE_TEST, plan=plan) is False


# --- require_feature dependency ---

async def test_require_feature_allows_when_no_plan_restriction(db_session):
    school, _ = await _seed_school_with_plan(db_session)
    teacher = await _seed_teacher(db_session, school.id)

    result = await require_feature(Feature.VOICE_TEST)(user=teacher, session=db_session)

    assert result.id == teacher.id


async def test_require_feature_blocks_when_plan_excludes_it(db_session):
    school, _ = await _seed_school_with_plan(db_session, enabled_features=["question_paper"])
    teacher = await _seed_teacher(db_session, school.id)

    with pytest.raises(ForbiddenError):
        await require_feature(Feature.VOICE_TEST)(user=teacher, session=db_session)


async def test_require_feature_allows_when_plan_includes_it(db_session):
    school, _ = await _seed_school_with_plan(db_session, enabled_features=["question_paper", "voice_test"])
    teacher = await _seed_teacher(db_session, school.id)

    result = await require_feature(Feature.VOICE_TEST)(user=teacher, session=db_session)

    assert result.id == teacher.id


async def test_require_feature_allows_a_school_with_no_subscription_yet(db_session):
    """No Subscription row (mid-onboarding) -> get_active_plan returns
    None -> treated as unrestricted, same posture as plan-limit checks
    elsewhere (see subscription_repository.get_active_plan's docstring).
    """
    school = await _seed_school(db_session)
    teacher = await _seed_teacher(db_session, school.id)

    result = await require_feature(Feature.VOICE_TEST)(user=teacher, session=db_session)

    assert result.id == teacher.id


async def test_require_feature_never_blocks_a_user_with_no_school(db_session):
    """Super Admin has no school_id - entitlements are a school-scoping
    concept, not a role one, so this must never raise for them.
    """
    super_admin = await _seed_super_admin(db_session)

    result = await require_feature(Feature.VOICE_TEST)(user=super_admin, session=db_session)

    assert result.id == super_admin.id


# --- Admin plan-features endpoints ---

async def test_admin_get_plan_features_defaults_to_none(db_session):
    _, plan = await _seed_school_with_plan(db_session)
    super_admin = await _seed_super_admin(db_session)

    out = await admin.get_plan_features(str(plan.id), _=super_admin, session=db_session)

    assert out.enabled_features is None


async def test_admin_update_plan_features_persists_and_audits(db_session):
    _, plan = await _seed_school_with_plan(db_session)
    super_admin = await _seed_super_admin(db_session)

    out = await admin.update_plan_features(
        str(plan.id), UpdateFeaturesIn(enabled_features=[Feature.QUESTION_PAPER]),
        actor=super_admin, session=db_session,
    )

    assert out.enabled_features == [Feature.QUESTION_PAPER]

    log = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.action == "plan.features_updated", AuditLog.target_id == str(plan.id))
        )
    ).scalar_one()
    assert log.detail == "all features -> question_paper"


async def test_admin_update_plan_features_back_to_all(db_session):
    _, plan = await _seed_school_with_plan(db_session, enabled_features=["question_paper"])
    super_admin = await _seed_super_admin(db_session)

    out = await admin.update_plan_features(
        str(plan.id), UpdateFeaturesIn(enabled_features=None), actor=super_admin, session=db_session,
    )

    assert out.enabled_features is None
    await db_session.refresh(plan)
    assert plan.enabled_features is None


# --- GET /api/v1/me exposes the effective set (what nool-apps' meClient
# reads to hide nav items - see services/api/meClient.ts) - and it flows
# from the plan/subscription with no separate school step. ---

async def test_get_me_reports_effective_features_from_the_plan(db_session):
    school, _ = await _seed_school_with_plan(db_session, enabled_features=["question_paper"])
    teacher = await _seed_teacher(db_session, school.id)

    response = await profile.get_me(
        user=AuthenticatedUser(uid=teacher.firebase_uid, email=teacher.email, claims={}), session=db_session,
    )

    assert response.profile is not None
    assert response.profile.enabled_features == [Feature.QUESTION_PAPER]


async def test_get_me_reports_none_when_the_plan_has_no_restriction(db_session):
    school, _ = await _seed_school_with_plan(db_session)
    teacher = await _seed_teacher(db_session, school.id)

    response = await profile.get_me(
        user=AuthenticatedUser(uid=teacher.firebase_uid, email=teacher.email, claims={}), session=db_session,
    )

    assert response.profile is not None
    assert response.profile.enabled_features is None
