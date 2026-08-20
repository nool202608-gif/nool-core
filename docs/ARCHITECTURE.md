# Architecture

## Overview

nool-core is the backend platform for noolAI: an authentication service, a
core business API, an NGINX reverse proxy, and PostgreSQL, run together via
Docker Compose for local development. `nool-app` and the admin web app are
separate repositories that talk to this stack over HTTP.

```
                    NGINX
                      |
              +-------+-------+
              v               v
        Auth Service      Core Service
              |               |
              +-------+-------+
                      v
                  PostgreSQL
```

## Services

### NGINX

The external HTTP entry point. Routes `/auth/*` to the Auth service and
`/api/*` to the Core service, forwards/generates `X-Request-ID`, sets CORS
headers, and enforces request size limits. Contains no business or
authentication logic - see `nginx/`.

### Auth Service

Verifies Firebase ID tokens and extracts caller identity:

```
nool-app -> NGINX -> Auth Service -> Firebase
```

Firebase is the identity provider. This service never implements password
auth and never stores passwords. See `services/auth/README.md`.

### Core Service

Owns the product domain (Schools, Teachers, Students, Classes, Tests, ...).
Currently implements only the backend foundation: startup, configuration,
health/readiness, database connectivity, migration support, and an
authentication middleware foundation. No business workflows yet - see
`services/core/README.md`.

### PostgreSQL

Runs as a Compose service for local development with a persistent named
volume. Production uses managed PostgreSQL. See `database/README.md`.

## Identity & Authorization

Firebase issues ID tokens (`firebase_uid`). Both services can verify a token
independently - Firebase tokens are self-contained JWTs, so verification
doesn't require a network call to the Auth service per request. The shared
verification logic lives in `shared/auth/` since it's generic infrastructure,
not business logic.

Conceptually, once identity resolution exists in Core:

```
Firebase UID -> nool User -> Role -> School/Tenant -> Teacher/Student profile
```

Authorization (what a user can access) is enforced server-side and is
distinct from authentication (who the user is). Initial roles: `SUPER_ADMIN`,
`SCHOOL_ADMIN`, `TEACHER`, `STUDENT`. Permissions are implemented only as
features require them.

## Shared infrastructure

`shared/` contains only generic, cross-service infrastructure - never
business logic:

- `shared/config` - base environment-driven settings class.
- `shared/logging` - structured JSON logging, request ID context/middleware.
- `shared/errors` - the standard error envelope and FastAPI exception handlers.
- `shared/types` - common response models (health/readiness).
- `shared/auth` - Firebase ID token verification.

## Service boundaries

Auth and Core are logically independent within one repository (a deliberate
monorepo decision - see the root README). Auth does not import Core business
modules; Core does not import Auth implementation details. A service is
extracted into its own repository only if it later needs independent
deployment, scaling, ownership, runtime, or isolation.

## Error handling

Every error - expected (`AppError` subclasses) or unexpected - renders as:

```json
{ "error": { "code": "VALIDATION_ERROR", "message": "Invalid request.", "request_id": "req_..." } }
```

Stack traces, database errors, internal paths, and secrets are never
exposed to clients.
