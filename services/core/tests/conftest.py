import pytest
from fastapi.testclient import TestClient

from shared.auth import reset_firebase_state


@pytest.fixture(autouse=True)
def _core_env(monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "test_user")
    monkeypatch.setenv("POSTGRES_PASSWORD", "test_password")
    monkeypatch.setenv("POSTGRES_DB", "test_db")
    monkeypatch.setenv("POSTGRES_HOST", "postgres")


@pytest.fixture(autouse=True)
def _reset_firebase():
    reset_firebase_state()
    yield
    reset_firebase_state()


@pytest.fixture
def client(_core_env):
    from src.main import create_app

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
