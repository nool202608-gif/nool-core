import pytest
from pydantic import ValidationError

from src.config.settings import CoreSettings


def test_database_url_uses_postgres_hostname_not_localhost(monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "u")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p")
    monkeypatch.setenv("POSTGRES_DB", "d")
    monkeypatch.setenv("POSTGRES_HOST", "postgres")

    settings = CoreSettings()

    assert settings.database_url == "postgresql+asyncpg://u:p@postgres:5432/d"
    assert "localhost" not in settings.database_url


def test_missing_required_database_settings_raises(monkeypatch):
    monkeypatch.delenv("POSTGRES_USER", raising=False)
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    monkeypatch.delenv("POSTGRES_DB", raising=False)

    with pytest.raises(ValidationError):
        CoreSettings()
