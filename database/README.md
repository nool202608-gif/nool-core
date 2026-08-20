# Database

PostgreSQL is the system of record. Locally it runs as a Docker Compose
service (`postgres`) with a persistent named volume; production uses a
managed PostgreSQL instance (see the root README).

## Migrations

Migration tooling is [Alembic](https://alembic.sqlalchemy.org/), configured
in this directory:

```
database/
├── alembic.ini
├── migrations/
│   ├── env.py          # reads POSTGRES_*/DATABASE_URL from the environment
│   ├── script.py.mako
│   └── versions/        # empty - no product schema yet
└── README.md
```

No product schema exists yet (see `CLAUDE.md`'s "Current Goal" - foundation
only, no business tables). `target_metadata` in `env.py` is `None` until
Core's domain models exist, at which point `--autogenerate` can be enabled.

### Running migrations

Migrations run inside the `core` container, which has both Alembic and this
`database/` directory available:

```bash
./scripts/migrate.sh                 # alembic upgrade head
./scripts/migrate.sh downgrade -1    # any alembic subcommand
./scripts/migrate.sh revision --autogenerate -m "add schools table"
```

Or directly:

```bash
docker compose exec --workdir /app/database core alembic upgrade head
```

Credentials come from the same `POSTGRES_*` environment variables the core
service uses - nothing is hardcoded in `env.py`.
