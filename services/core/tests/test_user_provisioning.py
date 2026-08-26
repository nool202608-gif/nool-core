"""src/services/user_provisioning.py - mocks firebase_admin.auth directly
(same monkeypatch style as services/auth/tests/test_firebase_auth.py)
rather than hitting real Firebase, since this module's whole job is
translating Admin SDK calls/errors, not proving Firebase itself works.
"""

from types import SimpleNamespace

import pytest
from firebase_admin import auth as firebase_auth

from shared.errors import ConflictError

from src.domain.models import Role
from src.services import user_provisioning


@pytest.fixture(autouse=True)
def _fake_default_app(monkeypatch):
    # create_firebase_user/clear_must_change_password_claim both call
    # firebase_admin.get_app() rather than initializing their own - see
    # that module's docstring for why. Faked here so tests don't depend
    # on a real Firebase app being initialized in this process.
    monkeypatch.setattr(user_provisioning.firebase_admin, "get_app", lambda: "fake-app")


def test_create_firebase_user_generates_a_real_looking_temp_password(monkeypatch):
    captured = {}

    def fake_create_user(*, email, password, display_name, app):
        captured["password"] = password
        return SimpleNamespace(uid="new-uid-123")

    monkeypatch.setattr(firebase_auth, "create_user", fake_create_user)
    monkeypatch.setattr(firebase_auth, "set_custom_user_claims", lambda uid, claims, app: None)

    result = user_provisioning.create_firebase_user(
        email="a@school.edu", display_name="A Teacher", role=Role.TEACHER
    )

    assert result.firebase_uid == "new-uid-123"
    assert result.temp_password == captured["password"]
    assert len(result.temp_password) >= 8


def test_create_firebase_user_sets_role_and_must_change_password_claims(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        firebase_auth, "create_user", lambda **kwargs: SimpleNamespace(uid="new-uid-123")
    )

    def fake_set_claims(uid, claims, app):
        captured["uid"] = uid
        captured["claims"] = claims

    monkeypatch.setattr(firebase_auth, "set_custom_user_claims", fake_set_claims)

    user_provisioning.create_firebase_user(email="a@school.edu", display_name="A", role=Role.STUDENT)

    assert captured["uid"] == "new-uid-123"
    assert captured["claims"] == {"role": "STUDENT", "mustChangePassword": True}


def test_create_firebase_user_maps_email_already_exists_to_conflict_error(monkeypatch):
    def fake_create_user(**kwargs):
        raise firebase_auth.EmailAlreadyExistsError("exists", None, None)

    monkeypatch.setattr(firebase_auth, "create_user", fake_create_user)

    with pytest.raises(ConflictError):
        user_provisioning.create_firebase_user(email="dup@school.edu", display_name="A", role=Role.TEACHER)


def test_reset_password_sets_a_new_password_on_the_existing_account(monkeypatch):
    captured = {}

    def fake_update_user(uid, *, password, app):
        captured["uid"] = uid
        captured["password"] = password

    monkeypatch.setattr(firebase_auth, "update_user", fake_update_user)
    monkeypatch.setattr(firebase_auth, "set_custom_user_claims", lambda uid, claims, app: None)

    temp_password = user_provisioning.reset_password(firebase_uid="uid-1", role=Role.TEACHER)

    assert captured["uid"] == "uid-1"
    assert captured["password"] == temp_password
    assert len(temp_password) >= 8


def test_reset_password_re_flags_must_change_password_and_preserves_role(monkeypatch):
    captured = {}

    monkeypatch.setattr(firebase_auth, "update_user", lambda uid, *, password, app: None)

    def fake_set_claims(uid, claims, app):
        captured["uid"] = uid
        captured["claims"] = claims

    monkeypatch.setattr(firebase_auth, "set_custom_user_claims", fake_set_claims)

    user_provisioning.reset_password(firebase_uid="uid-2", role=Role.STUDENT)

    assert captured["uid"] == "uid-2"
    assert captured["claims"] == {"role": "STUDENT", "mustChangePassword": True}


def test_clear_must_change_password_claim_preserves_role(monkeypatch):
    captured = {}

    def fake_set_claims(uid, claims, app):
        captured["uid"] = uid
        captured["claims"] = claims

    monkeypatch.setattr(firebase_auth, "set_custom_user_claims", fake_set_claims)

    user_provisioning.clear_must_change_password_claim(firebase_uid="uid-1", role=Role.SCHOOL_ADMIN)

    assert captured["uid"] == "uid-1"
    assert captured["claims"] == {"role": "SCHOOL_ADMIN", "mustChangePassword": False}
