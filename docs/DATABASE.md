# Database

## Local development

PostgreSQL runs as the `postgres` Compose service (official `postgres:16-alpine`
image) with:

- a persistent named Docker volume (`nool_core_postgres_data`)
- database name/user/password from environment variables (`POSTGRES_DB`,
  `POSTGRES_USER`, `POSTGRES_PASSWORD` in `.env`)
- a `pg_isready`-based health check
- no credentials hardcoded anywhere in source

Data persists across `docker compose down` / `docker compose up`. It is only
destroyed by `docker compose down -v` - see the warning in
`docs/DEVELOPMENT.md`.

Services connect over the Compose network using the hostname `postgres`,
never `localhost`:

```
postgresql://<user>:<password>@postgres:5432/<database>
```

`services/core/src/config/settings.py` builds this connection string (using
the `asyncpg` driver) from environment variables - see
`services/core/README.md`.

## Production

Docker PostgreSQL is for local development only. Production uses a managed
PostgreSQL instance unless explicitly decided otherwise. The application
must not depend on Docker-specific database behavior - all access goes
through the standard `postgresql://` connection string and SQLAlchemy, so
swapping in a managed instance is just a config change.

## Migrations

Alembic migration tooling lives in `database/` - see `database/README.md`
for the full workflow. No product schema exists yet (see `CLAUDE.md`'s
"Current Goal"); migrations will be added as Core's domain models land.

## Identity model

PostgreSQL stores application-level identity; Firebase is only the identity
*provider*. Never use email as the primary key for a user - use a stable
internal ID and store the Firebase UID as an external reference:

```
Firebase UID -> nool User (id, firebase_uid, role, school_id, profile)
```

This table does not exist yet - it will be introduced via a migration once
Core's user domain is implemented.
