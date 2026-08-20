# Core Service

The Core service will eventually own the product domain: Schools, Teachers,
Students, Classes, Curriculum, Tests, and more. For now it only implements
the backend foundation: startup, configuration, health/readiness, request
IDs, error handling, logging, database connectivity, migration support, and
an authentication middleware foundation.

## Endpoints

| Method | Path      | Description                                   |
| ------ | --------- | ---------------------------------------------- |
| GET    | `/health` | Process health.                                |
| GET    | `/ready`  | Ready when PostgreSQL is reachable.            |

## Configuration

Read from the environment (see `.env.example` at the repo root):

| Variable                   | Required | Description                                   |
| ---------------------------- | -------- | ---------------------------------------------- |
| `SERVICE_NAME`                | no       | Defaults to `core`.                            |
| `ENVIRONMENT`                 | no       | Defaults to `development`.                     |
| `LOG_LEVEL`                   | no       | Defaults to `INFO`.                            |
| `POSTGRES_USER`               | yes      | Database user.                                 |
| `POSTGRES_PASSWORD`           | yes      | Database password.                             |
| `POSTGRES_DB`                 | yes      | Database name.                                 |
| `POSTGRES_HOST`               | no       | Defaults to `postgres` (the Compose service).  |
| `POSTGRES_PORT`               | no       | Defaults to `5432`.                            |
| `FIREBASE_PROJECT_ID`         | no       | Needed for the auth middleware to verify tokens. |
| `FIREBASE_CREDENTIALS_PATH`   | no       | Path to a service account JSON key.            |

## Database & migrations

Connection management lives in `src/repositories/database.py`. Migration
tooling (Alembic) lives in `database/` at the repo root - see
[`database/README.md`](../../database/README.md).

## Local development

```bash
cd services/core
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
POSTGRES_USER=nool POSTGRES_PASSWORD=nool POSTGRES_DB=nool_core POSTGRES_HOST=localhost \
  uvicorn src.main:app --reload
```

## Tests

```bash
cd services/core
pytest
```

Tests never require a real PostgreSQL instance - database connectivity is
exercised through mocks (see `tests/test_ready.py`).
