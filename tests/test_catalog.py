from __future__ import annotations

from uuid import uuid4

import pytest

from apps.api.wearo_api.catalog import CatalogError, CatalogItem, CatalogService


class Store:
    def __init__(self, item: CatalogItem | None = None) -> None:
        self.item = item

    def create_item(self, actor_id: object, item: CatalogItem) -> CatalogItem:
        self.item = item
        return item

    def update_item(self, actor_id: object, item: CatalogItem) -> CatalogItem:
        self.item = item
        return item

    def get_item(self, actor_id: object, tenant_id: object, item_id: object) -> CatalogItem | None:
        return self.item

    def list_items(self, actor_id: object, tenant_id: object) -> tuple[CatalogItem, ...]:
        return (self.item,) if self.item else ()

    def create_collection(self, actor_id: object, collection: object) -> object:
        return collection


def item(
    *,
    title: str = " Jacket ",
    price_minor: int | None = 129900,
    currency: str | None = "inr",
    publish_state: str = "DRAFT",
) -> CatalogItem:
    return CatalogItem(
        item_id=uuid4(),
        tenant_id=uuid4(),
        account_id=uuid4(),
        category_id=uuid4(),
        item_code=" SKU-1 ",
        title=title,
        attributes={},
        price_minor=price_minor,
        currency=currency,
        publish_state=publish_state,  # type: ignore[arg-type]
    )


def test_create_normalizes_catalog_fields() -> None:
    store = Store()
    created = CatalogService(store).create_item(uuid4(), item())  # type: ignore[arg-type]
    assert (created.item_code, created.title, created.currency) == ("SKU-1", "Jacket", "INR")


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"price_minor": -1}, "INVALID_PRICE"),
        ({"price_minor": None}, "INVALID_PRICE"),
        ({"currency": "RUPEE"}, "INVALID_CURRENCY"),
        ({"title": "  "}, "INVALID_TITLE"),
    ],
)
def test_invalid_item_is_rejected(changes: dict[str, object], code: str) -> None:
    with pytest.raises(CatalogError) as error:
        CatalogService(Store()).create_item(uuid4(), item(**changes))  # type: ignore[arg-type]
    assert error.value.code == code


def test_unpublish_preserves_item_and_changes_visibility() -> None:
    existing = item(publish_state="PUBLISHED")
    store = Store(existing)
    result = CatalogService(store).unpublish(uuid4(), existing.tenant_id, existing.item_id)  # type: ignore[arg-type]
    assert result.publish_state == "UNPUBLISHED"
