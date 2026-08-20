# Auth Service

Verifies Firebase ID tokens and extracts the authenticated caller's identity.
Firebase is the sole identity provider - this service never handles
passwords and never stores them.

```
nool-app -> NGINX -> Auth Service -> Firebase
```

## Endpoints

| Method | Path          | Description                                   |
| ------ | ------------- | ---------------------------------------------- |
| GET    | `/health`     | Process health.                                |
| GET    | `/ready`      | Ready when Firebase is configured.             |
| GET    | `/api/v1/me`  | Returns the caller's identity from their token. |

## Configuration

Read from the environment (see `.env.example` at the repo root):

| Variable                     | Required | Description                                  |
| ----------------------------- | -------- | --------------------------------------------- |
| `SERVICE_NAME`                | no       | Defaults to `auth`.                           |
| `ENVIRONMENT`                 | no       | Defaults to `development`.                    |
| `LOG_LEVEL`                   | no       | Defaults to `INFO`.                           |
| `FIREBASE_PROJECT_ID`         | for `/ready` and `/api/v1/me` | Firebase project ID. |
| `FIREBASE_CREDENTIALS_PATH`   | no       | Path to a service account JSON key. Falls back to Application Default Credentials when unset. |

Firebase is initialized lazily on first token verification, not at startup,
so the service boots cleanly even without credentials configured.

## Local development

```bash
cd services/auth
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn src.main:app --reload
```

## Tests

```bash
cd services/auth
pytest
```
