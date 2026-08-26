import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def get_database_url() -> str:
    """Builds the migration connection string from the environment.

    Uses the sync psycopg2 driver (Alembic's norm) even though the
    application uses asyncpg at runtime. No credentials are ever hardcoded
    here - everything comes from POSTGRES_* / DATABASE_URL env vars, the
    same ones the core service itself reads.
    """
    url = os.environ.get("DATABASE_URL")
    if url:
        return url

    user = os.environ["POSTGRES_USER"]
    password = os.environ["POSTGRES_PASSWORD"]
    db = os.environ["POSTGRES_DB"]
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"


config.set_main_option("sqlalchemy.url", get_database_url())

# Importing src.domain.models registers every ORM model on Base.metadata
# (see that package's __init__.py) - this is the only import needed to
# enable autogenerate. Only resolvable inside the core container / with
# PYTHONPATH set to the repo root, same as the app itself (see
# services/core/Dockerfile's PYTHONPATH=/app).
from src.domain.models import Base  # noqa: E402

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
