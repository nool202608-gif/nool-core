"""Authorization-boundary tests for the new require_role/get_current_app_user
foundation - covers what CLAUDE.md's Testing section requires
("authentication failures, authorization failures, valid authentication").

Two layers, deliberately kept separate:
- The 403 role-rejection tests below override get_current_app_user
  directly via TestClient (no real DB touched - require_role's check
  raises before the route body ever runs a query, so these are
  host-portable, same monkeypatch spirit as the existing test_deps.py).
- Everything that needs a real row (get_current_app_user's DB lookup,
  school-scoped query isolation) calls the function directly as a plain
  coroutine against the real db_session fixture, rather than through
  TestClient - TestClient/httpx runs the ASGI app in its own event loop
  (a separate anyio portal thread), which would conflict with the loop
  pytest-asyncio's db_session fixture is bound to if the same session
  were shared across that boundary.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from shared.auth import AuthenticatedUser
from shared.errors import NotFoundError, UnauthorizedError

from src.api.deps import get_current_app_user
from src.api.routes import roster
from src.domain.models import Role, School, SchoolClass, User, UserStatus


def _fake_user(role: Role) -> User:
    return User(
        id=uuid.uuid4(),
        firebase_uid="fake-uid",
        email="fake@example.com",
        display_name="Fake User",
        role=role,
        school_id=uuid.uuid4(),
        status=UserStatus.ACTIVE,
    )


@pytest.fixture
def client_as(_core_env):
    def _make(role: Role) -> TestClient:
        from src.main import create_app

        app = create_app()
        app.dependency_overrides[get_current_app_user] = lambda: _fake_user(role)
        return TestClient(app)

    return _make


def test_teacher_route_rejects_student_role(client_as):
    client = client_as(Role.STUDENT)
    response = client.get("/api/v1/classes", headers={"Authorization": "Bearer x"})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_student_only_route_rejects_teacher_role(client_as):
    client = client_as(Role.TEACHER)
    response = client.get("/api/v1/me/dashboard", headers={"Authorization": "Bearer x"})

    assert response.status_code == 403


async def _seed_school(db_session) -> School:
    school = School(name="Test School", board="CBSE", city="Bengaluru", contact_email="a@b.com")
    db_session.add(school)
    await db_session.flush()
    return school


async def _seed_user(db_session, *, role: Role, school_id=None) -> User:
    firebase_uid = f"uid-{uuid.uuid4()}"
    user = User(
        firebase_uid=firebase_uid,
        email=f"{firebase_uid}@example.com",
        display_name="Test User",
        role=role,
        school_id=school_id,
        status=UserStatus.ACTIVE,
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def test_get_current_app_user_resolves_a_real_row(db_session):
    school = await _seed_school(db_session)
    teacher = await _seed_user(db_session, role=Role.TEACHER, school_id=school.id)

    resolved = await get_current_app_user(
        user=AuthenticatedUser(uid=teacher.firebase_uid, email=None, claims={}), session=db_session
    )

    assert resolved.id == teacher.id
    assert resolved.role == Role.TEACHER


async def test_get_current_app_user_rejects_unknown_firebase_uid(db_session):
    with pytest.raises(UnauthorizedError):
        await get_current_app_user(
            user=AuthenticatedUser(uid="no-such-uid", email=None, claims={}), session=db_session
        )


async def test_class_lookup_is_scoped_to_callers_school(db_session):
    school_a = await _seed_school(db_session)
    school_b = await _seed_school(db_session)
    other_class = SchoolClass(school_id=school_b.id, grade=9, section="Z")
    db_session.add(other_class)
    await db_session.flush()

    with pytest.raises(NotFoundError):
        await roster.get_class_in_school(db_session, str(other_class.id), school_a.id)

    # But it resolves fine when scoped to the school it actually belongs to.
    found = await roster.get_class_in_school(db_session, str(other_class.id), school_b.id)
    assert found.id == other_class.id
