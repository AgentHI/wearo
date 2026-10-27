from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy import Engine, text

from .admin_organizations import ADMIN_ACTOR_ID, BUSINESS_TYPES

ControlScope = Literal["PLATFORM", "BUSINESS_TYPE", "ORGANIZATION"]
ControlAction = Literal["PAUSE", "RESUME"]


class AdminPlatformControlError(ValueError):
    pass


class PostgresAdminPlatformControls:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def status(self) -> dict[str, object]:
        with self.engine.connect() as connection:
            platform = (
                connection.execute(
                    text(
                        "SELECT paused, reason, updated_at FROM platform_tryon_controls "
                        "WHERE scope='PLATFORM' AND scope_key='ALL'"
                    )
                )
                .mappings()
                .one()
            )
            types = connection.execute(
                text(
                    "SELECT scope_key AS business_type, paused, reason, updated_at "
                    "FROM platform_tryon_controls WHERE scope='BUSINESS_TYPE' "
                    "ORDER BY scope_key"
                )
            ).mappings()
        return {
            "platform": {**dict(platform), "operational": not platform["paused"]},
            "business_types": [dict(item) for item in types],
        }

    def change(
        self,
        *,
        scope: ControlScope,
        scope_key: str | None,
        action: ControlAction,
        reason: str,
        confirmed: bool,
    ) -> dict[str, object]:
        explanation = reason.strip()
        if not confirmed or not explanation:
            raise AdminPlatformControlError("Confirmation and a reason are required.")
        key = (scope_key or "").strip().upper()
        if scope == "PLATFORM":
            key = "ALL"
        elif scope == "BUSINESS_TYPE" and key not in BUSINESS_TYPES:
            raise AdminPlatformControlError("A valid business type is required.")
        elif scope == "ORGANIZATION":
            try:
                UUID(key)
            except ValueError:
                raise AdminPlatformControlError("A valid organization is required.") from None
        paused = action == "PAUSE"
        now = datetime.now(UTC)
        tenant_id = UUID(key) if scope == "ORGANIZATION" else None
        target_id = tenant_id or uuid5(
            NAMESPACE_URL, f"https://wearo.ai/admin/tryon-controls/{scope}/{key}"
        )
        with self.engine.begin() as connection:
            if scope == "ORGANIZATION":
                existing = (
                    connection.execute(
                        text(
                            "SELECT account_id, try_on_status FROM business_tenants "
                            "WHERE tenant_id=:tenant AND status='ACTIVE' FOR UPDATE"
                        ),
                        {"tenant": tenant_id},
                    )
                    .mappings()
                    .one_or_none()
                )
                if existing is None:
                    raise AdminPlatformControlError("Organization is unavailable.")
                before_paused = existing["try_on_status"] == "PAUSED"
                account_id: UUID | None = existing["account_id"]
                connection.execute(
                    text(
                        "UPDATE business_tenants SET try_on_status=:status, updated_at=:now "
                        "WHERE tenant_id=:tenant"
                    ),
                    {"status": "PAUSED" if paused else "ACTIVE", "now": now, "tenant": tenant_id},
                )
            else:
                before_paused = bool(
                    connection.execute(
                        text(
                            "SELECT paused FROM platform_tryon_controls "
                            "WHERE scope=:scope AND scope_key=:key FOR UPDATE"
                        ),
                        {"scope": scope, "key": key},
                    ).scalar_one_or_none()
                )
                connection.execute(
                    text("""INSERT INTO platform_tryon_controls
                    (scope, scope_key, paused, reason, updated_at)
                    VALUES (:scope, :key, :paused, :reason, :now)
                    ON CONFLICT (scope, scope_key) DO UPDATE SET paused=EXCLUDED.paused,
                      reason=EXCLUDED.reason, updated_at=EXCLUDED.updated_at"""),
                    {
                        "scope": scope,
                        "key": key,
                        "paused": paused,
                        "reason": explanation,
                        "now": now,
                    },
                )
                account_id = None
            connection.execute(
                text("""INSERT INTO audit_events
                (audit_event_id, account_id, tenant_id, actor_type, actor_id, action,
                 target_type, target_id, reason, before_summary, after_summary, occurred_at)
                VALUES (:event, :account, :tenant, 'ADMIN', :actor, :action,
                        'TRY_ON_CONTROL', :target, :reason, CAST(:before AS jsonb),
                        CAST(:after AS jsonb), :now)"""),
                {
                    "event": uuid4(),
                    "account": account_id,
                    "tenant": tenant_id,
                    "actor": ADMIN_ACTOR_ID,
                    "action": f"ADMIN_TRYONS_{action}",
                    "target": target_id,
                    "reason": explanation,
                    "before": json.dumps(
                        {"scope": scope, "scope_key": key, "paused": before_paused}
                    ),
                    "after": json.dumps({"scope": scope, "scope_key": key, "paused": paused}),
                    "now": now,
                },
            )
        return {"scope": scope, "scope_key": key, "operational": not paused}
