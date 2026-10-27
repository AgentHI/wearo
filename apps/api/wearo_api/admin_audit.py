from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import Engine, text

from .plan_usage import BUSINESS_REPORTING_TIMEZONE


class AdminAuditError(ValueError):
    pass


class PostgresAdminAudit:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def list(
        self, *, search: str = "", date_from: date | None = None, date_to: date | None = None
    ) -> dict[str, object]:
        if date_from and date_to and date_from > date_to:
            raise AdminAuditError("Start date must not be after end date.")
        if date_from and date_to and (date_to - date_from).days > 366:
            raise AdminAuditError("Audit date range cannot exceed 367 days.")
        start = (
            datetime.combine(date_from, time.min, BUSINESS_REPORTING_TIMEZONE).astimezone(UTC)
            if date_from
            else None
        )
        end = (
            datetime.combine(
                date_to + timedelta(days=1), time.min, BUSINESS_REPORTING_TIMEZONE
            ).astimezone(UTC)
            if date_to
            else None
        )
        query = search.strip()
        with self.engine.connect() as connection:
            rows = connection.execute(
                text(
                    """SELECT event.audit_event_id, event.actor_type, event.actor_id,
                              event.action, event.target_type, event.target_id, event.reason,
                              event.before_summary, event.after_summary, event.occurred_at,
                              event.tenant_id, profile.display_name AS organization_name,
                              CASE WHEN event.actor_type='ADMIN' THEN 'Wearo Super Admin'
                                   WHEN event.actor_type='SYSTEM' THEN 'Wearo Platform'
                                   ELSE event.actor_type END AS actor_name
                       FROM audit_events event
                       LEFT JOIN business_profiles profile
                         ON profile.tenant_id=event.tenant_id
                        AND profile.account_id=event.account_id
                       WHERE event.actor_type IN ('ADMIN', 'SYSTEM')
                         AND (CAST(:start AS timestamptz) IS NULL
                              OR event.occurred_at >= CAST(:start AS timestamptz))
                         AND (CAST(:end AS timestamptz) IS NULL
                              OR event.occurred_at < CAST(:end AS timestamptz))
                         AND (NOT :has_search
                           OR event.action ILIKE :search
                           OR event.target_type ILIKE :search
                           OR COALESCE(event.reason, '') ILIKE :search
                           OR COALESCE(profile.display_name, '') ILIKE :search)
                       ORDER BY event.occurred_at DESC, event.audit_event_id DESC
                       LIMIT 500"""
                ),
                {"start": start, "end": end, "has_search": bool(query), "search": f"%{query}%"},
            ).mappings()
            items = [dict(row) for row in rows]
        return {"events": items, "count": len(items), "editable": False}
