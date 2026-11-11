from __future__ import annotations

import argparse
import os

from sqlalchemy import create_engine

from .account_lifecycle import PostgresAccountLifecycle
from .database import normalize_database_url
from .media_runtime import private_blob_store_from_env
from .postgres_retention import PostgresLifecycleStore
from .render_runtime import PostgresRenderRuntime
from .retention import RetentionService


def main() -> None:
    parser = argparse.ArgumentParser(description="Wearo scheduled beta operations")
    parser.add_argument("operation", choices=("purge", "purge-accounts", "recover-leases"))
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    database_url = os.environ.get("WEARO_DATABASE_URL", "")
    if not database_url:
        raise SystemExit("WEARO_DATABASE_URL is required")
    engine = create_engine(normalize_database_url(database_url), pool_pre_ping=True)
    if args.operation == "purge":
        blobs = private_blob_store_from_env()
        deleted_assets = RetentionService(PostgresLifecycleStore(engine), blobs).purge_due(
            limit=args.limit
        )
        deleted_accounts = PostgresAccountLifecycle(engine, blobs).purge_due(limit=args.limit)
        print(f"purged={len(deleted_assets)} purged_accounts={len(deleted_accounts)}")
        return
    if args.operation == "purge-accounts":
        deleted = PostgresAccountLifecycle(engine, private_blob_store_from_env()).purge_due(
            limit=args.limit
        )
        print(f"purged_accounts={len(deleted)}")
        return
    summary = PostgresRenderRuntime(engine).recover_expired()
    print(f"requeued={summary.requeued} failed={summary.failed}")


if __name__ == "__main__":
    main()
