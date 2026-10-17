# Continuous integration

The required GitHub Actions workflow is `.github/workflows/ci.yml`. Every pull request and push to
`main` must pass these independent blocking jobs:

- `contracts`: backlog integrity, OpenAPI linting, and generated-client drift.
- `python-quality`: formatting, linting, strict typing, unit tests, and CI policy validation.
- `migrations`: policy validation plus upgrade, downgrade, re-upgrade, and current-revision checks
  against a fresh PostgreSQL 16 service database.
- `dependency-security`: Python and Node dependency vulnerability audits.

The workflow has read-only repository permissions and no required step may use
`continue-on-error`. `scripts/validate_ci.py` enforces both properties and the required command set.
Its negative tests demonstrate that removing a gate or making checks non-blocking fails the suite.

## Local checks

Install exact dependencies first:

```sh
pnpm install --frozen-lockfile
UV_CACHE_DIR=.uv-cache uv sync --frozen --extra dev
```

Run the non-database gates:

```sh
pnpm validate:backlog
pnpm lint:openapi
pnpm check:contracts
pnpm check:ci
pnpm check:python
pnpm check:security
```

Run the migration gate with a disposable PostgreSQL database only:

```sh
WEARO_DATABASE_URL='postgresql+psycopg://...' sh scripts/rehearse_migrations.sh
```

## Secrets

The PostgreSQL credential in CI belongs only to the disposable per-job service container. It is not
a deployable secret. Future provider, staging, and production credentials must be stored in GitHub
encrypted secrets or an approved environment secret store and referenced as
`${{ secrets.SECRET_NAME }}`. They must never be committed to the repository, workflow, fixtures,
logs, generated artifacts, or documentation.
