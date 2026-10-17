#!/bin/sh
set -eu

if [ -z "${WEARO_DATABASE_URL:-}" ]; then
  echo "WEARO_DATABASE_URL is required" >&2
  exit 2
fi

uv run python scripts/validate_migrations.py
uv run alembic -c apps/api/alembic.ini upgrade head
uv run alembic -c apps/api/alembic.ini downgrade base
uv run alembic -c apps/api/alembic.ini upgrade head
uv run alembic -c apps/api/alembic.ini current
