from __future__ import annotations

from uuid import UUID

from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import IntegrityError

from .catalog import CatalogCollection, CatalogError, CatalogItem
from .tenant_scope import TenantScopeError, require_tenant_scope


class PostgresCatalogStore:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @staticmethod
    def _require_member(connection: Connection, actor_id: UUID, tenant_id: UUID) -> UUID:
        try:
            return require_tenant_scope(connection, actor_id, tenant_id).account_id
        except TenantScopeError:
            raise CatalogError(
                "CATALOG_RESOURCE_UNAVAILABLE", "Catalog resource is unavailable."
            ) from None

    @staticmethod
    def _item(row: object, collection_ids: tuple[UUID, ...] = ()) -> CatalogItem:
        value = row._mapping  # type: ignore[attr-defined]
        return CatalogItem(
            item_id=value["item_id"],
            tenant_id=value["tenant_id"],
            account_id=value["account_id"],
            category_id=value["category_id"],
            item_code=value["item_code"],
            title=value["title"],
            attributes=value["attributes"],
            price_minor=value["price_minor"],
            currency=value["currency"],
            publish_state=value["publish_state"],
            collection_ids=collection_ids,
        )

    @staticmethod
    def _replace_collections(connection: Connection, item: CatalogItem) -> None:
        connection.execute(
            text(
                "DELETE FROM catalog_collection_items "
                "WHERE item_id = :item AND account_id = :account"
            ),
            {"item": item.item_id, "account": item.account_id},
        )
        for position, collection_id in enumerate(item.collection_ids):
            result = connection.execute(
                text(
                    """
                    INSERT INTO catalog_collection_items
                        (collection_id, item_id, account_id, tenant_id, position)
                    SELECT collection_id, :item, account_id, tenant_id, :position
                    FROM catalog_collections
                    WHERE collection_id = :collection AND tenant_id = :tenant
                      AND account_id = :account
                    """
                ),
                {
                    "collection": collection_id,
                    "item": item.item_id,
                    "account": item.account_id,
                    "tenant": item.tenant_id,
                    "position": position,
                },
            )
            if result.rowcount != 1:
                raise CatalogError("COLLECTION_NOT_FOUND", "Collection is unavailable.")

    def create_collection(self, actor_id: UUID, collection: CatalogCollection) -> CatalogCollection:
        try:
            with self.engine.begin() as connection:
                account_id = self._require_member(connection, actor_id, collection.tenant_id)
                if account_id != collection.account_id:
                    raise CatalogError(
                        "CATALOG_RESOURCE_UNAVAILABLE", "Catalog resource is unavailable."
                    )
                connection.execute(
                    text(
                        """
                        INSERT INTO catalog_collections
                            (collection_id, account_id, tenant_id, name, description, publish_state)
                        VALUES (:id, :account, :tenant, :name, :description, :state)
                        """
                    ),
                    {
                        "id": collection.collection_id,
                        "account": collection.account_id,
                        "tenant": collection.tenant_id,
                        "name": collection.name,
                        "description": collection.description,
                        "state": collection.publish_state,
                    },
                )
        except IntegrityError as error:
            raise CatalogError(
                "CATALOG_CONFLICT", "A collection with this name already exists."
            ) from error
        return collection

    def create_item(self, actor_id: UUID, item: CatalogItem) -> CatalogItem:
        try:
            with self.engine.begin() as connection:
                account_id = self._require_member(connection, actor_id, item.tenant_id)
                if account_id != item.account_id:
                    raise CatalogError(
                        "CATALOG_RESOURCE_UNAVAILABLE", "Catalog resource is unavailable."
                    )
                result = connection.execute(
                    text(
                        """
                        INSERT INTO catalog_items
                            (item_id, account_id, tenant_id, category_id, item_code, source_type,
                             title, attributes, price_minor, currency, publish_state, quality_state)
                        SELECT :id, :account, :tenant, c.category_id, :code, 'GENUINE', :title,
                               CAST(:attributes AS jsonb), :price, :currency, :state,
                               CASE WHEN :state = 'PUBLISHED' THEN 'APPROVED' ELSE 'PENDING' END
                        FROM offering_categories c
                        WHERE c.category_id = :category AND c.offering = 'BUSINESS'
                        """
                    ),
                    {
                        "id": item.item_id,
                        "account": item.account_id,
                        "tenant": item.tenant_id,
                        "category": item.category_id,
                        "code": item.item_code,
                        "title": item.title,
                        "attributes": __import__("json").dumps(item.attributes),
                        "price": item.price_minor,
                        "currency": item.currency,
                        "state": item.publish_state,
                    },
                )
                if result.rowcount != 1:
                    raise CatalogError("CATEGORY_NOT_FOUND", "Business category is unavailable.")
                self._replace_collections(connection, item)
        except IntegrityError as error:
            raise CatalogError(
                "CATALOG_CONFLICT", "Item code or catalogue data conflicts."
            ) from error
        return item

    def update_item(self, actor_id: UUID, item: CatalogItem) -> CatalogItem:
        try:
            with self.engine.begin() as connection:
                account_id = self._require_member(connection, actor_id, item.tenant_id)
                if account_id != item.account_id:
                    raise CatalogError(
                        "CATALOG_RESOURCE_UNAVAILABLE", "Catalog resource is unavailable."
                    )
                result = connection.execute(
                    text(
                        """
                        UPDATE catalog_items
                        SET category_id = :category, item_code = :code, title = :title,
                            attributes = CAST(:attributes AS jsonb), price_minor = :price,
                            currency = :currency, publish_state = :state,
                            quality_state = CASE
                                WHEN :state = 'PUBLISHED' THEN 'APPROVED'
                                ELSE quality_state
                            END,
                            updated_at = now()
                        WHERE item_id = :id AND tenant_id = :tenant AND account_id = :account
                        """
                    ),
                    {
                        "id": item.item_id,
                        "account": item.account_id,
                        "tenant": item.tenant_id,
                        "category": item.category_id,
                        "code": item.item_code,
                        "title": item.title,
                        "attributes": __import__("json").dumps(item.attributes),
                        "price": item.price_minor,
                        "currency": item.currency,
                        "state": item.publish_state,
                    },
                )
                if result.rowcount != 1:
                    raise CatalogError("CATALOG_ITEM_NOT_FOUND", "Catalog item is unavailable.")
                self._replace_collections(connection, item)
        except IntegrityError as error:
            raise CatalogError(
                "CATALOG_CONFLICT", "Item code or catalogue data conflicts."
            ) from error
        return item

    def get_item(self, actor_id: UUID, tenant_id: UUID, item_id: UUID) -> CatalogItem | None:
        with self.engine.connect() as connection:
            account_id = self._require_member(connection, actor_id, tenant_id)
            row = connection.execute(
                text(
                    """
                    SELECT item_id, tenant_id, account_id, category_id, item_code, title,
                           attributes, price_minor, currency, publish_state
                    FROM catalog_items
                    WHERE item_id = :item AND tenant_id = :tenant AND account_id = :account
                    """
                ),
                {"item": item_id, "tenant": tenant_id, "account": account_id},
            ).one_or_none()
            if row is None:
                return None
            collection_ids = tuple(
                value[0]
                for value in connection.execute(
                    text(
                        "SELECT collection_id FROM catalog_collection_items "
                        "WHERE item_id = :item ORDER BY position"
                    ),
                    {"item": item_id},
                )
            )
            return self._item(row, collection_ids)

    def list_items(self, actor_id: UUID, tenant_id: UUID) -> tuple[CatalogItem, ...]:
        with self.engine.connect() as connection:
            account_id = self._require_member(connection, actor_id, tenant_id)
            rows = connection.execute(
                text(
                    """
                    SELECT item_id, tenant_id, account_id, category_id, item_code, title,
                           attributes, price_minor, currency, publish_state
                    FROM catalog_items
                    WHERE tenant_id = :tenant AND account_id = :account
                    ORDER BY updated_at DESC, item_id
                    """
                ),
                {"tenant": tenant_id, "account": account_id},
            )
            return tuple(self._item(row) for row in rows)
