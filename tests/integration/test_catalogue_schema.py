from __future__ import annotations

import os
from collections.abc import Iterator
from uuid import uuid4

import pytest
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from apps.api.wearo_api.database import normalize_database_url

pytestmark = pytest.mark.integration


@pytest.fixture
def connection() -> Iterator[Connection]:
    raw_url = os.environ.get("WEARO_DATABASE_URL")
    if raw_url is None:
        pytest.skip("WEARO_DATABASE_URL is required for PostgreSQL integration tests")
    engine = create_engine(normalize_database_url(raw_url))
    with engine.connect() as database_connection:
        transaction = database_connection.begin()
        yield database_connection
        transaction.rollback()
    engine.dispose()


def create_tenant(connection: Connection, slug: str) -> tuple[str, str]:
    account_id = str(uuid4())
    tenant_id = str(uuid4())
    connection.execute(
        text("INSERT INTO accounts (account_id, kind) VALUES (:id, 'TENANT')"),
        {"id": account_id},
    )
    connection.execute(
        text(
            "INSERT INTO business_tenants (tenant_id, account_id, slug) "
            "VALUES (:tenant, :account, :slug)"
        ),
        {"tenant": tenant_id, "account": account_id, "slug": slug},
    )
    return account_id, tenant_id


def create_category(connection: Connection, *, enabled: bool) -> str:
    category_id = str(uuid4())
    category_code = f"category-{uuid4().hex[:12]}"
    connection.execute(
        text(
            "INSERT INTO offering_categories (category_id, code, offering, enabled) "
            "VALUES (:id, :code, 'SHOP', :enabled)"
        ),
        {"id": category_id, "code": category_code, "enabled": enabled},
    )
    return category_id


def test_disabled_category_rejects_published_item(connection: Connection) -> None:
    account_id, tenant_id = create_tenant(connection, "disabled-category")
    category_id = create_category(connection, enabled=False)

    with pytest.raises(DBAPIError, match="disabled category"), connection.begin_nested():
        connection.execute(
            text(
                "INSERT INTO catalog_items "
                "(account_id, tenant_id, category_id, item_code, source_type, title, "
                "publish_state, quality_state) VALUES (:account, :tenant, :category, 'SKU-1', "
                "'GENUINE', 'Item', 'PUBLISHED', 'APPROVED')"
            ),
            {"account": account_id, "tenant": tenant_id, "category": category_id},
        )


def test_item_requires_exactly_one_owner_kind(connection: Connection) -> None:
    category_id = create_category(connection, enabled=True)

    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(
            text(
                "INSERT INTO catalog_items "
                "(category_id, item_code, source_type, title) "
                "VALUES (:category, 'OWNERLESS', 'GENUINE', 'Ownerless')"
            ),
            {"category": category_id},
        )


def test_verified_seller_url_requires_a_url(connection: Connection) -> None:
    account_id, tenant_id = create_tenant(connection, "verified-url")
    category_id = create_category(connection, enabled=True)

    with pytest.raises(IntegrityError), connection.begin_nested():
        connection.execute(
            text(
                "INSERT INTO catalog_items "
                "(account_id, tenant_id, category_id, item_code, source_type, title, "
                "seller_url_verified) VALUES (:account, :tenant, :category, 'SKU-2', "
                "'GENUINE', 'Item', true)"
            ),
            {"account": account_id, "tenant": tenant_id, "category": category_id},
        )
