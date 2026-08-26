import pytest
from fastapi.testclient import TestClient

from shared.auth import reset_identity_provider


@pytest.fixture(autouse=True)
def _reset_identity_provider():
    reset_identity_provider()
    yield
    reset_identity_provider()


@pytest.fixture
def client():
    from src.main import create_app

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
