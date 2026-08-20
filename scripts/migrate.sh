#!/usr/bin/env bash
# Runs Alembic migrations for the core service's PostgreSQL database, inside
# the running `core` container. Defaults to "upgrade head" with no arguments.
#
# Usage:
#   ./scripts/migrate.sh                              # upgrade head
#   ./scripts/migrate.sh downgrade -1
#   ./scripts/migrate.sh revision --autogenerate -m "add schools table"
set -euo pipefail

cd "$(dirname "$0")/.."

if [ "$#" -eq 0 ]; then
    set -- upgrade head
fi

docker compose exec --workdir /app/database core alembic "$@"
