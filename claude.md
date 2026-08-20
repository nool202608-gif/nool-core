nool-core — Backend Engineering Instructions

Mission

Build nool-core, the backend platform for noolAI.

This repository contains:

Authentication service

Core business API

NGINX reverse proxy

Database/migrations

Docker-based local development

Shared infrastructure/configuration

nool-app and admin web apps are separate repositories.

Current Goal

Establish the backend foundation only.

Implement:

Repository structure

Docker infrastructure

Auth service skeleton

Core API skeleton

NGINX

PostgreSQL development container

Database/migration foundation

Health/readiness endpoints

Configuration

Logging/error handling

Testing foundation

Do NOT implement business workflows yet:

Test

Homework

Retest

Improvement

Question Paper

AI Assessor

Question Generator

subscriptions

analytics

notifications

Repository Structure

nool-core/
├── CLAUDE.md
├── README.md
├── .env.example
├── .gitignore
├── compose.yml
├── nginx/
│ ├── nginx.conf
│ └── conf.d/
│ └── default.conf
├── services/
│ ├── auth/
│ │ ├── src/
│ │ │ ├── api/
│ │ │ ├── domain/
│ │ │ ├── services/
│ │ │ ├── repositories/
│ │ │ ├── config/
│ │ │ └── main.py
│ │ ├── tests/
│ │ ├── Dockerfile
│ │ └── README.md
│ └── core/
│ ├── src/
│ │ ├── api/
│ │ ├── domain/
│ │ ├── services/
│ │ ├── repositories/
│ │ ├── config/
│ │ └── main.py
│ ├── tests/
│ ├── Dockerfile
│ └── README.md
├── database/
│ ├── migrations/
│ └── README.md
├── shared/
│ ├── config/
│ ├── logging/
│ ├── errors/
│ └── types/
├── scripts/
└── docs/
├── ARCHITECTURE.md
├── DEVELOPMENT.md
└── DATABASE.md

Adapt the exact language/framework structure if the repository already has a selected stack. Do not add unnecessary abstractions.

Docker

The repository must support:

docker compose up
docker compose up --build
docker compose down
docker compose logs -f
docker compose ps

Initial local stack:

                    NGINX
                      │
              ┌───────┴───────┐
              ▼               ▼
        Auth Service      Core Service
              │               │
              └───────┬───────┘
                      ▼
                  PostgreSQL

PostgreSQL container — required

PostgreSQL MUST run as a real Docker Compose service for local development.

Use the official PostgreSQL image.

Requirements:

persistent named Docker volume

database name from environment configuration

database user from environment configuration

database password from environment configuration

health check using pg_isready

no credentials hardcoded in source code

Auth and Core connect through the Docker Compose network using the hostname postgres

do not use localhost for service-to-PostgreSQL connections inside containers

Expected connection shape:

postgresql://<user>:<password>@postgres:5432/<database>

The database must remain available across:

docker compose down
docker compose up

unless the volume is intentionally removed with:

docker compose down -v

docker compose down -v is destructive for local database data and must be documented clearly.

compose.yml initially contains:

nginx

auth

core

postgres

Do not add Redis, Kafka, RabbitMQ, Elasticsearch, Kubernetes or other infrastructure without an actual requirement.

Every application container must:

have a health check

use environment variables

avoid hardcoded secrets

expose only required ports

support graceful shutdown

produce useful logs

PostgreSQL uses a persistent Docker volume for local development.

Production Database

Docker PostgreSQL is for local development.

Production should use managed PostgreSQL unless explicitly decided otherwise.

The application must not depend on Docker-specific database behavior.

NGINX

NGINX is the external HTTP entry point.

Initial routing:

/auth/_ → Auth Service
/api/_ → Core Service

NGINX must:

forward request IDs

preserve required headers

support required CORS configuration

enforce reasonable request limits

return clean errors

contain no business logic

Authentication business logic belongs to Auth, not NGINX.

Auth Service

Firebase Authentication is the identity provider.

Architecture:

nool-app
↓
NGINX
↓
Auth Service
↓
Firebase

The backend verifies Firebase ID tokens.

Do NOT implement password authentication.
Do NOT store Firebase passwords.

Eventually:

Firebase UID
↓
nool User
↓
Role
↓
School/Tenant
↓
Teacher/Student profile

Initial Auth foundation only:

Firebase token verification foundation

authenticated-user extraction

health

readiness

configuration

errors

logging

tests

Do not implement complete user management yet.

Core Service

The Core service will eventually contain:

Schools

Teachers

Students

Classes

Curriculum

Tests

Test Results

Homework

Retests

Improvement

Question Papers

Datasets

Question Banks

Subscriptions

Analytics

For now implement only:

startup

configuration

health

readiness

request ID

error handling

logging

database connectivity

migration support

authentication middleware foundation

Database

Use PostgreSQL.

Create:

connection management

migration tooling

environment configuration

readiness check

transaction support

Do not create the complete product schema yet.

Identity

Firebase is the identity provider. PostgreSQL stores application-level identity.

Conceptually:

Firebase
│ firebase_uid
▼
nool User
├── role
├── school_id
└── profile

Never use email as the primary identity key. Use stable internal IDs. Store Firebase UID as an external identity reference.

Authorization

Authentication and authorization are different.

Authentication = who is the user?
Authorization = what can the user access?

Authorization must be enforced server-side. Frontend role checks are never a security boundary.

Initial roles:

SUPER_ADMIN

SCHOOL_ADMIN

TEACHER

STUDENT

Implement permissions only when required by a feature.

API

Use:

/api/v1/

Use clear resource-oriented endpoints.

Examples:

/api/v1/users
/api/v1/classes
/api/v1/tests
/api/v1/homework

Do not create endpoints merely for convenience.

Errors

Use:

{
"error": {
"code": "VALIDATION*ERROR",
"message": "Invalid request.",
"request_id": "req*..."
}
}

Never expose stack traces, database errors, internal paths or secrets.

Request IDs

Every incoming request must receive or propagate a request ID.

Use:

X-Request-ID

The ID must be available in logs and returned to clients when appropriate.

Configuration

Never hardcode:

Firebase credentials

database credentials

API keys

secrets

production URLs

Use environment variables.

Provide .env.example.
Never commit .env.

Logging

Use structured logging with:

timestamp

level

service

request_id

route

status

duration

Never log passwords, Firebase tokens, authorization headers or secrets.

Health

Every service exposes:

/health
/ready

/health checks process health.
/ready checks required dependencies such as PostgreSQL where appropriate.

Testing

Every service must have:

unit tests

API tests

integration tests where appropriate

At minimum test:

startup

health

readiness

configuration failures

database connectivity

authentication failures

authorization failures

valid authentication

Tests must not require production infrastructure.

Service Boundaries

Keep Auth and Core logically independent:

services/
├── auth/
└── core/

Do not import Core business modules into Auth.
Do not import Auth implementation details into Core.

Shared code should contain only genuinely generic infrastructure. Avoid a giant shared business-logic package.

Monorepo Decision

This repository intentionally contains Auth and Core for now.

Do not split them into separate repositories prematurely.

A service can be extracted later if it requires:

independent deployment

independent scaling

independent ownership

different runtime

strong isolation

First Claude Code Task

When first opened:

Read this CLAUDE.md completely.

Inspect the repository.

Do not implement business features.

Create the folder structure.

Create Docker Compose.

Create NGINX.

Create Auth service skeleton.

Create Core service skeleton.

Create PostgreSQL development container.

Create health/readiness endpoints.

Create configuration system.

Create logging foundation.

Create testing foundation.

Create documentation.

Run the complete local stack.

Verify NGINX reaches Auth and Core.

Verify Auth and Core reach PostgreSQL.

Run tests.

Run lint/typecheck.

Report exactly what was created.

Do not continue into business logic.

Definition of Done

Repository structure exists

Docker Compose works

NGINX starts

Auth starts

Core starts

PostgreSQL starts

Auth health works

Core health works

Readiness works

NGINX routes /auth/\*

NGINX routes /api/\*

Services connect to PostgreSQL

Environment variables work

No secrets committed

Logging works

Request IDs work

Error handling works

Tests pass

Lint/typecheck passes

docker compose up --build works from a clean checkout

Documentation is complete

Do not declare completion until these checks have actually been run.
