from shared.auth import AuthenticatedUser
from shared.errors import UnauthorizedError


def test_me_requires_authorization_header(client):
    response = client.get("/api/v1/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_me_rejects_malformed_authorization_header(client):
    response = client.get("/api/v1/me", headers={"Authorization": "Token abc"})

    assert response.status_code == 401


def test_me_rejects_invalid_token(client, monkeypatch):
    def fake_verify(token: str):
        raise UnauthorizedError("Invalid or expired authentication token.")

    monkeypatch.setattr("src.services.token_service.verify_id_token", fake_verify)

    response = client.get("/api/v1/me", headers={"Authorization": "Bearer bad-token"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_me_returns_user_for_valid_token(client, monkeypatch):
    def fake_verify(token: str):
        assert token == "good-token"
        return AuthenticatedUser(uid="uid-123", email="student@example.com", claims={})

    monkeypatch.setattr("src.services.token_service.verify_id_token", fake_verify)

    response = client.get("/api/v1/me", headers={"Authorization": "Bearer good-token"})

    assert response.status_code == 200
    assert response.json() == {"uid": "uid-123", "email": "student@example.com"}
