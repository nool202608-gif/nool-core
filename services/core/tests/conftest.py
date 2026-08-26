import os
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from shared.auth import reset_identity_provider


def _dotenv_values(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def _real_postgres_env() -> dict[str, str]:
    """Captured at collection time, before _core_env's per-test monkeypatch
    shadows these with fake values - db_session needs real credentials to
    reach the actual dev Postgres (see that fixture below).

    Inside the core container, POSTGRES_* env vars are already real
    (injected by compose.yml) and POSTGRES_HOST="postgres" resolves on
    the Compose network. Running `pytest` directly on the host, neither
    is true - fall back to the repo root's .env (POSTGRES_USER/PASSWORD/DB)
    and localhost:${POSTGRES_PORT_HOST:-5433}, the port
    compose.override.yml already publishes for exactly this kind of
    direct-from-host access.
    """
    if os.environ.get("POSTGRES_USER") and os.environ.get("POSTGRES_HOST"):
        return {
            "user": os.environ["POSTGRES_USER"],
            "password": os.environ.get("POSTGRES_PASSWORD", ""),
            "db": os.environ.get("POSTGRES_DB", ""),
            "host": os.environ["POSTGRES_HOST"],
            "port": os.environ.get("POSTGRES_PORT", "5432"),
        }

    dotenv = _dotenv_values(Path(__file__).resolve().parents[3] / ".env")
    if not dotenv.get("POSTGRES_USER"):
        return {}
    return {
        "user": dotenv["POSTGRES_USER"],
        "password": dotenv.get("POSTGRES_PASSWORD", ""),
        "db": dotenv.get("POSTGRES_DB", ""),
        "host": "localhost",
        "port": dotenv.get("POSTGRES_PORT_HOST", "5433"),
    }


_REAL_POSTGRES_ENV = _real_postgres_env()


@pytest.fixture(autouse=True)
def _core_env(monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "test_user")
    monkeypatch.setenv("POSTGRES_PASSWORD", "test_password")
    monkeypatch.setenv("POSTGRES_DB", "test_db")
    monkeypatch.setenv("POSTGRES_HOST", "postgres")


@pytest.fixture(autouse=True)
def _reset_identity_provider():
    reset_identity_provider()
    yield
    reset_identity_provider()


@pytest.fixture
def client(_core_env):
    from src.main import create_app

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


@pytest_asyncio.fixture
async def db_session():
    """A real AsyncSession against the actual dev Postgres, wrapped in an
    outer transaction that's rolled back at the end of the test - so
    tests can freely INSERT/UPDATE without leaving fixture data behind.

    Skips (doesn't fail) if Postgres isn't reachable with real
    credentials - e.g. when running `pytest` directly on the host, where
    the `postgres` hostname doesn't resolve. Run these for real via
    `docker compose exec core pytest`, matching database/README.md's
    migration workflow.
    """
    if not _REAL_POSTGRES_ENV.get("user"):
        pytest.skip("Real POSTGRES_* credentials not available in this environment.")

    url = (
        f"postgresql+asyncpg://{_REAL_POSTGRES_ENV['user']}:{_REAL_POSTGRES_ENV['password']}"
        f"@{_REAL_POSTGRES_ENV['host']}:{_REAL_POSTGRES_ENV['port']}/{_REAL_POSTGRES_ENV['db']}"
    )
    engine = create_async_engine(url)
    try:
        connection = await engine.connect()
    except OSError:
        pytest.skip("Could not reach the dev Postgres container from this environment.")
        return

    transaction = await connection.begin()
    session = AsyncSession(bind=connection, expire_on_commit=False)
    try:
        yield session
    finally:
        await session.close()
        await transaction.rollback()
        await connection.close()
        await engine.dispose()
