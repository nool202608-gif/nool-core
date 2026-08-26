# Auth Service

Verifies the caller's token and extracts their identity. Firebase is the
identity provider today - this service never handles passwords and never
stores them.

```
nool-app -> NGINX -> Auth Service -> Firebase
```

## Provider abstraction

Token verification goes through `shared.auth`'s `IdentityProvider`
interface, not Firebase directly - see `docs/ARCHITECTURE.md`'s "Identity &
Authorization" section for the full design. In this service, the only file
that names Firebase concretely is `src/services/token_service.py`
(one constructor call); everything else - `src/api/deps.py`, all routes -
only ever sees `shared.auth.AuthenticatedUser`. Swapping identity
providers means adding a class under `shared/auth/providers/` and changing
that one call.

## Endpoints

| Method | Path          | Description                                   |
| ------ | ------------- | ---------------------------------------------- |
| GET    | `/health`     | Process health.                                |
| GET    | `/ready`      | Ready when Firebase is configured.             |
| GET    | `/api/v1/me`  | Returns `{uid, email, role}` from the caller's token. `role` is `null` if the account has no role assigned yet. |

## Roles

Firebase has no first-class "role" concept - roles are a `role` **custom
claim** on the user, set via `scripts/set_role.py` (an Admin SDK tool, not
an API endpoint - there is no user-management feature yet). A signed-in
user must sign in again (or force-refresh their ID token) after their role
changes to see it reflected.

```bash
python services/auth/scripts/set_role.py --email teacher@example.com --role TEACHER
python services/auth/scripts/set_role.py --uid abc123 --role STUDENT --display-name "Aarav Kumar"
```

Requires `FIREBASE_PROJECT_ID`/`FIREBASE_CREDENTIALS_PATH` in the environment
(a real service account - see Configuration below).

## Configuration

Read from the environment (see `.env.example` at the repo root):

| Variable                     | Required | Description                                  |
| ----------------------------- | -------- | --------------------------------------------- |
| `SERVICE_NAME`                | no       | Defaults to `auth`.                           |
| `ENVIRONMENT`                 | no       | Defaults to `development`.                    |
| `LOG_LEVEL`                   | no       | Defaults to `INFO`.                           |
| `FIREBASE_PROJECT_ID`         | for `/ready` and `/api/v1/me` | Firebase project ID. |
| `FIREBASE_CREDENTIALS_HOST_PATH` (compose.yml) | no | Host path to an Admin SDK service account JSON, bind-mounted read-only into the container. Required for `scripts/set_role.py`; without it, token verification falls back to Application Default Credentials, which typically isn't available locally. Put the file under `secrets/` (gitignored) - see the root `.env.example`. |

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
