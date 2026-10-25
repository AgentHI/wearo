from __future__ import annotations

import argparse
import os
from pathlib import Path

from sqlalchemy import create_engine

from .account_lifecycle import PostgresAccountLifecycle
from .database import normalize_database_url
from .media_runtime import FilesystemPrivateBlobStore
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
    root = Path(os.environ.get("WEARO_PRIVATE_STORAGE_ROOT", ".wearo-storage"))
    if args.operation == "purge":
        blobs = FilesystemPrivateBlobStore(root)
        deleted_assets = RetentionService(PostgresLifecycleStore(engine), blobs).purge_due(
            limit=args.limit
        )
        deleted_accounts = PostgresAccountLifecycle(engine, blobs).purge_due(limit=args.limit)
        print(f"purged={len(deleted_assets)} purged_accounts={len(deleted_accounts)}")
        return
    if args.operation == "purge-accounts":
        deleted = PostgresAccountLifecycle(engine, FilesystemPrivateBlobStore(root)).purge_due(
            limit=args.limit
        )
        print(f"purged_accounts={len(deleted)}")
        return
    summary = PostgresRenderRuntime(engine).recover_expired()
    print(f"requeued={summary.requeued} failed={summary.failed}")


if __name__ == "__main__":
    main()
