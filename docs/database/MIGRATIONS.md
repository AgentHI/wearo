# Database migration conventions

Wearo uses PostgreSQL and Alembic. `WEARO_DATABASE_URL` is supplied by the runtime or CI secret store; no database credential or environment URL is committed.

## Ownership and classification

Every created table must have exactly one `TABLE_POLICIES` entry in its migration revision.

- `public`: non-private reference/configuration data. No account ownership is implied.
- `private`: customer or tenant data. Declare at least one of `consumer_id`, `tenant_id`, or `account_id` and include `created_at` and `updated_at`.
- `financial`: wallet/payment/invoice data. Declare `account_id`, use immutable or append-only domain rules, and include `created_at` and `updated_at`.
- `audit`: protected audit evidence. Declare applicable ownership/scope and timestamps; mutations require an explicit append-only design review.
- `system`: migration/queue/operational metadata containing no customer business data.

Owner columns are authorization attributes, not permission by themselves. APIs must resolve the authenticated principal and effective paying account server-side; client-provided tenant, owner, wallet, or account IDs never grant access.

## Identifier and time rules

- Application identifiers are UUIDs generated server-side. Do not use sequential IDs in public contracts.
- Use timezone-aware PostgreSQL timestamps and store UTC.
- Foreign keys and uniqueness constraints are explicit and named.
- Private object keys, OTPs, secrets, or unrestricted URLs are never stored in migration literals.
- Financial idempotency/provider identifiers require database uniqueness, not best-effort application checks.

## Compatibility and rollback

1. Prefer expand/migrate/contract changes across releases.
2. An application deploy must tolerate both the pre- and post-migration schema during rollout.
3. Destructive column/table changes require a separately approved cleanup migration after readers have moved.
4. Every revision implements `downgrade`; if a data transformation cannot be reversed, document the restore/forward-fix procedure and obtain review before merge.
5. Migrations must not silently seed unresolved prices, retention periods, providers, tax rules, categories, or quality thresholds.

## Required verification

Run:

```sh
uv run python scripts/validate_migrations.py
WEARO_DATABASE_URL='postgresql+psycopg://...' scripts/rehearse_migrations.sh
```

The rehearsal performs `upgrade head → downgrade base → upgrade head` on an empty disposable PostgreSQL database and prints the current revision. Production databases are never valid rehearsal targets.
