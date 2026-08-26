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

Verifies the caller's token and extracts identity, via whatever identity
provider is configured behind `shared/auth`'s `IdentityProvider` interface
(see "Identity & Authorization" below):

```
nool-app -> NGINX -> Auth Service -> Firebase
```

Firebase is the identity provider today. This service never implements
password auth and never stores passwords. See `services/auth/README.md`.

### Core Service

Owns the product domain: Schools, Teachers, Students, Classes, Curriculum,
Voice Tests, Test Results, Homework, Retests, Improvement, Question Papers,
Dashboards, Assistant, AI Assessor sessions, Leaderboard, and the Super
Admin / School Admin surfaces - the full contract nool-app's
`spec/docs/api-reference.html` defines. See `services/core/README.md` for
the schema/route/authorization architecture.

### PostgreSQL

Runs as a Compose service for local development with a persistent named
volume. Production uses managed PostgreSQL. See `database/README.md`.

## Identity & Authorization

Both services verify tokens independently - self-contained JWTs, so
verification doesn't require a network call to the Auth service per
request. The shared verification logic lives in `shared/auth/` since it's
generic infrastructure, not business logic - and it's provider-agnostic on
purpose:

- `shared/auth/provider.py` defines `AuthenticatedUser` (the
  provider-agnostic identity shape every provider must produce) and the
  `IdentityProvider` interface every provider implements.
- `shared/auth/providers/firebase.py` is the only concrete implementation
  today, and the only file that imports `firebase_admin`.
- Each service's `deps.py` (`services/auth/src/services/token_service.py`
  and `services/core/src/api/deps.py`) has exactly one line naming
  `FirebaseIdentityProvider` concretely - mirroring how nool-apps'
  `AuthProvider.tsx` has exactly one line naming its concrete identity
  service. Everything else (routes, business logic, tests using a fake
  provider) depends only on `AuthenticatedUser`/`IdentityProvider`.

Swapping identity providers means: add a class under `shared/auth/providers/`
implementing `IdentityProvider`, and change those two construction call
sites. Provider-specific configuration (env vars, `compose.yml`,
`requirements.txt`) still has to change too - that part can't be abstracted
away by any code design - but no route handler, business logic, or test
using a fake provider needs to.

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
- `shared/logging` - structured JSON logging, request ID + trace/span
  context/middleware.
- `shared/errors` - the standard error envelope and FastAPI exception handlers.
- `shared/types` - common response models (health/readiness).
- `shared/auth` - provider-agnostic token verification (`IdentityProvider`
  interface + `AuthenticatedUser`); Firebase is the one implementation,
  under `shared/auth/providers/`.
- `shared/tracing` - OpenTelemetry wiring (exported to Jaeger locally) -
  see `docs/OBSERVABILITY.md`.

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
