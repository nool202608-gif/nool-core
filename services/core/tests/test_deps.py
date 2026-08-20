import pytest

from shared.auth import AuthenticatedUser
from shared.errors import UnauthorizedError

from src.api.deps import get_current_user


def test_get_current_user_rejects_missing_header(_core_env):
    with pytest.raises(UnauthorizedError):
        get_current_user(authorization=None)


def test_get_current_user_rejects_malformed_header(_core_env):
    with pytest.raises(UnauthorizedError):
        get_current_user(authorization="Token abc")


def test_get_current_user_rejects_invalid_token(_core_env, monkeypatch):
    def fake_verify(token: str):
        raise UnauthorizedError("Invalid or expired authentication token.")

    monkeypatch.setattr("src.api.deps.verify_id_token", fake_verify)

    with pytest.raises(UnauthorizedError):
        get_current_user(authorization="Bearer bad-token")


def test_get_current_user_returns_user_for_valid_token(_core_env, monkeypatch):
    def fake_verify(token: str):
        assert token == "good-token"
        return AuthenticatedUser(uid="uid-1", email="teacher@example.com", claims={})

    monkeypatch.setattr("src.api.deps.verify_id_token", fake_verify)

    user = get_current_user(authorization="Bearer good-token")

    assert user.uid == "uid-1"
    assert user.email == "teacher@example.com"
