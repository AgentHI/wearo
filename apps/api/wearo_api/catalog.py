from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

PublishState = Literal["DRAFT", "PUBLISHED", "UNPUBLISHED"]


class CatalogError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class CatalogCollection:
    collection_id: UUID
    tenant_id: UUID
    account_id: UUID
    name: str
    description: str | None
    publish_state: PublishState


@dataclass(frozen=True)
class CatalogItem:
    item_id: UUID
    tenant_id: UUID
    account_id: UUID
    category_id: UUID
    item_code: str
    title: str
    attributes: dict[str, object]
    price_minor: int | None
    currency: str | None
    publish_state: PublishState
    collection_ids: tuple[UUID, ...] = ()


class CatalogStore(Protocol):
    def create_collection(
        self, actor_id: UUID, collection: CatalogCollection
    ) -> CatalogCollection: ...
    def create_item(self, actor_id: UUID, item: CatalogItem) -> CatalogItem: ...
    def update_item(self, actor_id: UUID, item: CatalogItem) -> CatalogItem: ...
    def get_item(self, actor_id: UUID, tenant_id: UUID, item_id: UUID) -> CatalogItem | None: ...
    def list_items(self, actor_id: UUID, tenant_id: UUID) -> tuple[CatalogItem, ...]: ...


class CatalogService:
    def __init__(self, store: CatalogStore) -> None:
        self.store = store

    @staticmethod
    def validate_item(item: CatalogItem) -> CatalogItem:
        if not item.item_code.strip() or len(item.item_code.strip()) > 80:
            raise CatalogError("INVALID_ITEM_CODE", "Item code must contain 1 to 80 characters.")
        if not item.title.strip() or len(item.title.strip()) > 200:
            raise CatalogError("INVALID_TITLE", "Title must contain 1 to 200 characters.")
        if (item.price_minor is None) != (item.currency is None):
            raise CatalogError("INVALID_PRICE", "Price and currency must be supplied together.")
        if item.price_minor is not None and item.price_minor < 0:
            raise CatalogError("INVALID_PRICE", "Price cannot be negative.")
        if item.currency is not None and (len(item.currency) != 3 or not item.currency.isalpha()):
            raise CatalogError("INVALID_CURRENCY", "Currency must be a three-letter code.")
        return CatalogItem(
            **{
                **item.__dict__,
                "item_code": item.item_code.strip(),
                "title": item.title.strip(),
                "currency": item.currency.upper() if item.currency else None,
            }
        )

    def create_collection(self, actor_id: UUID, collection: CatalogCollection) -> CatalogCollection:
        name = collection.name.strip()
        if not name or len(name) > 120:
            raise CatalogError(
                "INVALID_COLLECTION_NAME", "Collection name must contain 1 to 120 characters."
            )
        return self.store.create_collection(
            actor_id, CatalogCollection(**{**collection.__dict__, "name": name})
        )

    def create_item(self, actor_id: UUID, item: CatalogItem) -> CatalogItem:
        return self.store.create_item(actor_id, self.validate_item(item))

    def revise_item(self, actor_id: UUID, item: CatalogItem) -> CatalogItem:
        return self.store.update_item(actor_id, self.validate_item(item))

    def unpublish(self, actor_id: UUID, tenant_id: UUID, item_id: UUID) -> CatalogItem:
        existing = self.store.get_item(actor_id, tenant_id, item_id)
        if existing is None:
            raise CatalogError("CATALOG_ITEM_NOT_FOUND", "Catalog item is unavailable.")
        return self.store.update_item(
            actor_id, CatalogItem(**{**existing.__dict__, "publish_state": "UNPUBLISHED"})
        )
