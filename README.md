# nool-core

Backend platform for noolAI: authentication service, core business API,
NGINX reverse proxy, PostgreSQL, and Docker-based local development.

`nool-app` and the admin web app are separate repositories.

## Current status

Backend foundation (Phase 1) is done - repository structure, Docker
infrastructure, service skeletons, health checks, configuration, logging,
error handling, testing foundation. Phase 2 is in progress: the full
product API in Core - Schools, Teachers, Students, Classes, Curriculum,
Voice Tests, Test Results, Homework, Retests, Improvement, Question Papers,
Dashboards, Assistant, AI Assessor sessions, Leaderboard, Super Admin, and
School Admin. See `CLAUDE.md` for the full scope and `docs/ARCHITECTURE.md`
for how the pieces fit together.

## Repository structure

```
nool-core/
├── CLAUDE.md
├── compose.yml
├── nginx/                 # reverse proxy: routes /auth/* and /api/*
├── services/
│   ├── auth/               # Firebase token verification service
│   └── core/                # core business API
├── database/               # Alembic migration tooling
├── shared/                 # generic cross-service infrastructure
├── scripts/
└── docs/
```

## Quick start

```bash
cp .env.example .env
docker compose up --build
curl http://localhost:8080/health
```

See `docs/DEVELOPMENT.md` for the full local development workflow,
`docs/ARCHITECTURE.md` for system design, `docs/DATABASE.md` for the
database setup and migration workflow, and `docs/OBSERVABILITY.md` for
distributed tracing (Jaeger) and the authentication audit trail.

## Services

| Service | Description | README |
| ------- | ----------- | ------ |
| Auth    | Firebase ID token verification | [`services/auth/README.md`](services/auth/README.md) |
| Core    | Core business API foundation   | [`services/core/README.md`](services/core/README.md) |
