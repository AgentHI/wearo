from __future__ import annotations

import argparse
import os
from pathlib import Path

from sqlalchemy import create_engine

from .database import normalize_database_url
from .media_runtime import FilesystemPrivateBlobStore
from .postgres_retention import PostgresLifecycleStore
from .render_runtime import PostgresRenderRuntime
from .retention import RetentionService


def main() -> None:
    parser = argparse.ArgumentParser(description="Wearo scheduled beta operations")
    parser.add_argument("operation", choices=("purge", "recover-leases"))
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    database_url = os.environ.get("WEARO_DATABASE_URL", "")
    if not database_url:
        raise SystemExit("WEARO_DATABASE_URL is required")
    engine = create_engine(normalize_database_url(database_url), pool_pre_ping=True)
    if args.operation == "purge":
        root = Path(os.environ.get("WEARO_PRIVATE_STORAGE_ROOT", ".wearo-storage"))
        deleted = RetentionService(
            PostgresLifecycleStore(engine), FilesystemPrivateBlobStore(root)
        ).purge_due(limit=args.limit)
        print(f"purged={len(deleted)}")
        return
    summary = PostgresRenderRuntime(engine).recover_expired()
    print(f"requeued={summary.requeued} failed={summary.failed}")


if __name__ == "__main__":
    main()
