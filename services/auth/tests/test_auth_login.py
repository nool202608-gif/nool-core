from shared.errors import UnauthorizedError


def test_login_returns_custom_token_for_valid_credentials(client, monkeypatch):
    def fake_authenticate_with_password(email: str, password: str):
        assert email == "schooladmin@test.com"
        assert password == "correct-password"
        from shared.auth import PasswordAuthResult

        return PasswordAuthResult(custom_token="fake-custom-token")

    monkeypatch.setattr(
        "src.services.token_service.authenticate_with_password", fake_authenticate_with_password
    )

    response = client.post(
        "/api/v1/login",
        json={"email": "schooladmin@test.com", "password": "correct-password"},
    )

    assert response.status_code == 200
    assert response.json() == {"customToken": "fake-custom-token"}


def test_login_rejects_wrong_password_with_clean_401(client, monkeypatch):
    def fake_authenticate_with_password(email: str, password: str):
        raise UnauthorizedError("Incorrect email or password.")

    monkeypatch.setattr(
        "src.services.token_service.authenticate_with_password", fake_authenticate_with_password
    )

    response = client.post(
        "/api/v1/login",
        json={"email": "schooladmin@test.com", "password": "wrong-password"},
    )

    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "UNAUTHORIZED"
    assert body["error"]["message"] == "Incorrect email or password."


def test_login_rejects_nonexistent_email_with_the_same_clean_401(client, monkeypatch):
    """Must not leak whether the account exists - same error as a wrong
    password (see shared/auth/providers/firebase.py's enumeration-
    protection note).
    """

    def fake_authenticate_with_password(email: str, password: str):
        raise UnauthorizedError("Incorrect email or password.")

    monkeypatch.setattr(
        "src.services.token_service.authenticate_with_password", fake_authenticate_with_password
    )

    response = client.post(
        "/api/v1/login",
        json={"email": "nobody@example.com", "password": "anything"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Incorrect email or password."


def test_login_rejects_malformed_body(client):
    response = client.post("/api/v1/login", json={"email": "someone@example.com"})

    assert response.status_code == 422
