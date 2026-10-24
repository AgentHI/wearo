"""Seed pilot try-on pricing and business promotional credits.

Revision ID: 20261024_0033
Revises: 20261024_0032
Created: 2026-10-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261024_0033"
down_revision: str | None = "20261024_0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_POLICIES: dict[str, dict[str, object]] = {}


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO price_versions
            (price_version_id, action_code, token_cost, effective_from)
        SELECT gen_random_uuid(), 'TRY_ON', 20, '2026-10-24 00:00:00+00'
        WHERE NOT EXISTS (
            SELECT 1 FROM price_versions WHERE action_code='TRY_ON'
        )
        """
    )
    op.execute(
        """
        WITH eligible AS (
            SELECT w.account_id, w.wallet_id, t.tenant_id,
                   m.principal_id, gen_random_uuid() AS bucket_id
            FROM wallets w
            JOIN business_tenants t ON t.account_id=w.account_id
            JOIN tenant_memberships m
              ON m.account_id=t.account_id AND m.tenant_id=t.tenant_id
             AND m.role='OWNER' AND m.revoked_at IS NULL
            WHERE NOT EXISTS (
                SELECT 1 FROM ledger_entries e
                WHERE e.account_id=w.account_id
                  AND e.operation_key='pilot-business-starter-2026-10'
            )
        ), buckets AS (
            INSERT INTO wallet_buckets
                (bucket_id, account_id, wallet_id, bucket_type, expires_at)
            SELECT bucket_id, account_id, wallet_id, 'PROMO',
                   '2027-01-31 23:59:59+00'
            FROM eligible
            RETURNING bucket_id, account_id, wallet_id
        )
        INSERT INTO ledger_entries
            (entry_id, account_id, tenant_id, wallet_id, bucket_id, entry_type,
             amount, operation_key, performed_by_principal_id)
        SELECT gen_random_uuid(), e.account_id, e.tenant_id, e.wallet_id, e.bucket_id,
               'CREDIT', 1000, 'pilot-business-starter-2026-10', e.principal_id
        FROM eligible e
        JOIN buckets b ON b.bucket_id=e.bucket_id
        """
    )


def downgrade() -> None:
    # Ledger entries are append-only. Financial seed history is intentionally retained.
    pass
