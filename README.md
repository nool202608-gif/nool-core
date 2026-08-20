# nool-core

Backend platform for noolAI: authentication service, core business API,
NGINX reverse proxy, PostgreSQL, and Docker-based local development.

`nool-app` and the admin web app are separate repositories.

## Current status

This repository currently implements the **backend foundation only** -
repository structure, Docker infrastructure, service skeletons, health
checks, configuration, logging, error handling, and a testing foundation.
No business workflows (Tests, Homework, Retests, Question Papers, AI
Assessor, subscriptions, analytics, notifications, ...) are implemented yet.
See `CLAUDE.md` for the full scope and `docs/ARCHITECTURE.md` for how the
pieces fit together.

## Repository structure

```
nool-core/
├── CLAUDE.md
├── compose.yml
├── nginx/                 # reverse proxy: routes /auth/* and /api/*
├── services/
│   ├── auth/               # Firebase token verification service
│   └── core/                # core business API (foundation only)
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
`docs/ARCHITECTURE.md` for system design, and `docs/DATABASE.md` for the
database setup and migration workflow.

## Services

| Service | Description | README |
| ------- | ----------- | ------ |
| Auth    | Firebase ID token verification | [`services/auth/README.md`](services/auth/README.md) |
| Core    | Core business API foundation   | [`services/core/README.md`](services/core/README.md) |
