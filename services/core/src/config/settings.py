from shared.config import BaseServiceSettings


class CoreSettings(BaseServiceSettings):
    service_name: str = "core"

    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_host: str = "postgres"
    postgres_port: int = 5432

    firebase_project_id: str | None = None
    firebase_credentials_path: str | None = None

    @property
    def database_url(self) -> str:
        """Async SQLAlchemy connection string.

        Always resolves to the ``postgres`` Compose service hostname inside
        containers - never localhost - per CLAUDE.md.
        """
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


def get_settings() -> CoreSettings:
    """Reads settings from the environment on every call so tests can vary
    env vars per-case without dealing with cache invalidation.
    """
    return CoreSettings()
