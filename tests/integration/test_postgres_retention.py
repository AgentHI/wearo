from __future__ import annotations

import io
import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image
from sqlalchemy import Engine, create_engine, text

from apps.api.wearo_api.database import normalize_database_url
from apps.api.wearo_api.media_runtime import (
    FilesystemPrivateBlobStore,
    MediaRuntimeError,
    PostgresMediaRuntime,
)
from apps.api.wearo_api.postgres_retention import PostgresLifecycleStore
from apps.api.wearo_api.retention import RetentionService

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 17, 12, tzinfo=UTC)


@pytest.fixture
def engine() -> Iterator[Engine]:
    raw_url = os.environ.get("WEARO_DATABASE_URL")
    if raw_url is None:
        pytest.skip("WEARO_DATABASE_URL is required for PostgreSQL integration tests")
    database_engine = create_engine(normalize_database_url(raw_url))
    try:
        yield database_engine
    finally:
        database_engine.dispose()


def _image() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (256, 256), (50, 70, 90)).save(output, format="PNG")
    return output.getvalue()


def test_owner_deletion_revokes_immediately_and_purges_with_tombstone(
    engine: Engine, tmp_path: Path
) -> None:
    account_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO accounts (account_id, kind) VALUES (:account, 'CONSUMER')"),
            {"account": account_id},
        )
    blobs = FilesystemPrivateBlobStore(tmp_path / "private")
    media = PostgresMediaRuntime(engine, blobs)
    retention = RetentionService(PostgresLifecycleStore(engine), blobs)

    try:
        stored = media.store(account_id, kind="PRODUCT", content=_image(), content_type="image/png")
        delete_after = retention.request_delete(stored.asset_id, account_id, now=NOW)
        assert delete_after == NOW + timedelta(hours=24)
        with pytest.raises(MediaRuntimeError, match="unavailable"):
            media.read_owned(stored.asset_id, account_id)

        assert retention.purge_due(now=delete_after, limit=10) == (stored.asset_id,)
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT deletion_state, deleted_at
                    FROM media_assets
                    WHERE asset_id = :asset
                    """
                ),
                {"asset": stored.asset_id},
            ).one()
            assert row.deletion_state == "DELETED" and row.deleted_at == delete_after
    finally:
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM media_assets WHERE account_id = :account"),
                {"account": account_id},
            )
            connection.execute(
                text("DELETE FROM accounts WHERE account_id = :account"),
                {"account": account_id},
            )


def test_only_render_results_receive_automatic_expiry(engine: Engine, tmp_path: Path) -> None:
    account_id = uuid4()
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO accounts (account_id, kind) VALUES (:account, 'CONSUMER')"),
            {"account": account_id},
        )
    media = PostgresMediaRuntime(engine, FilesystemPrivateBlobStore(tmp_path / "private"))

    try:
        retained = {
            media.store(
                account_id, kind="PERSON", content=_image(), content_type="image/png"
            ).asset_id,
            media.store(
                account_id, kind="PRODUCT", content=_image(), content_type="image/png"
            ).asset_id,
            media.store_business_logo(account_id, _image(), "image/png").asset_id,
            media.store_advertisement(account_id, _image(), "image/png").asset_id,
            media.store_smart_ad(account_id, _image(), "image/png").asset_id,
        }
        render_result = media.store_result(account_id, _image(), "image/png")

        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT asset_id, purpose, retention_state, delete_after
                    FROM media_assets
                    WHERE account_id = :account
                    """
                ),
                {"account": account_id},
            ).mappings()
            assets = {row["asset_id"]: row for row in rows}

        assert all(
            assets[asset_id]["retention_state"] == "ACTIVE"
            and assets[asset_id]["delete_after"] is None
            for asset_id in retained
        )
        assert assets[render_result]["purpose"] == "RENDER_RESULT"
        assert assets[render_result]["retention_state"] == "EXPIRING"
        assert timedelta(days=29) < assets[render_result]["delete_after"] - datetime.now(UTC)
    finally:
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM media_assets WHERE account_id = :account"),
                {"account": account_id},
            )
            connection.execute(
                text("DELETE FROM accounts WHERE account_id = :account"),
                {"account": account_id},
            )
