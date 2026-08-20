# Development

## Prerequisites

- Docker and Docker Compose v2
- Python 3.12+ (only needed for running a service outside Docker)

## First-time setup

```bash
cp .env.example .env
# edit .env - at minimum set POSTGRES_PASSWORD to something non-default
```

## Running the stack

```bash
docker compose up --build   # build images and start everything
docker compose up           # start without rebuilding
docker compose ps           # see service status/health
docker compose logs -f      # tail logs from all services
docker compose logs -f core # tail logs from one service
docker compose down         # stop and remove containers (data persists)
```

The stack is reachable through NGINX at `http://localhost:8080` (or
whatever `NGINX_PORT` is set to):

```bash
curl http://localhost:8080/health
curl http://localhost:8080/auth/health
curl http://localhost:8080/auth/ready
curl http://localhost:8080/api/health
curl http://localhost:8080/api/ready
```

Auth, Core, and PostgreSQL are not published to the host in `compose.yml`
(production-shaped) - only NGINX is. `compose.override.yml` is auto-loaded
alongside it for local dev and additionally publishes PostgreSQL on
`localhost:5433` (override with `POSTGRES_PORT_HOST`) so you can point a GUI
client (TablePlus, DBeaver, pgAdmin, ...) or `psql` directly at it:

```
Host:     localhost
Port:     5433
User:     <POSTGRES_USER from .env>
Password: <POSTGRES_PASSWORD from .env>
Database: <POSTGRES_DB from .env>
```

```bash
psql "postgresql://$POSTGRES_USER:$POSTGRES_PASSWORD@localhost:5433/$POSTGRES_DB"
```

Delete or ignore `compose.override.yml` for a production-shaped deploy -
services stay internal-only without it.

### Destructive: resetting the database

```bash
docker compose down -v   # also deletes the postgres_data volume
```

This permanently deletes all local database data. Do not run it unless you
intend to start from an empty database.

## Running a service outside Docker

Each service can run standalone against your own PostgreSQL/Firebase
config - see `services/auth/README.md` and `services/core/README.md` for
exact commands. Both need `shared/` importable, which their `pyproject.toml`
handles via `pythonpath` when using `pytest`, and via `PYTHONPATH` when
running `uvicorn` (set it to the repo root).

## Migrations

See `database/README.md` and `scripts/migrate.sh`.

## Tests

```bash
cd services/auth && pip install -r requirements-dev.txt && pytest
cd services/core && pip install -r requirements-dev.txt && pytest
```

No test requires a real PostgreSQL or Firebase instance - dependencies are
mocked at the boundary (see each service's `tests/`).

## Linting / type-checking

Not yet configured - add per-service tooling (e.g. `ruff`, `mypy`) when the
project is ready to enforce it; keep configuration in each service's
`pyproject.toml` rather than a shared one, matching the service-boundary
principle in `docs/ARCHITECTURE.md`.
