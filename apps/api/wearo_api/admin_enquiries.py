from __future__ import annotations

from sqlalchemy import Engine, text

ENQUIRY_STATUSES = frozenset({"SUBMITTED", "IN_REVIEW", "CLOSED"})
ENQUIRY_PURPOSES = frozenset(
    {
        "BRAND_TRY_ON",
        "RETAIL_PARTNERSHIP",
        "ENTERPRISE_DEMO",
        "TECHNOLOGY_PARTNERSHIP",
        "PRESS",
        "OTHER",
    }
)


class AdminEnquiryError(ValueError):
    pass


class PostgresAdminEnquiries:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def list(
        self,
        *,
        search: str = "",
        purpose: str | None = None,
        status: str | None = None,
    ) -> dict[str, object]:
        query = search.strip()
        normalized_purpose = purpose.strip().upper() if purpose else None
        normalized_status = status.strip().upper() if status else None
        if normalized_purpose and normalized_purpose not in ENQUIRY_PURPOSES:
            raise AdminEnquiryError("Unsupported enquiry purpose filter.")
        if normalized_status and normalized_status not in ENQUIRY_STATUSES:
            raise AdminEnquiryError("Unsupported enquiry status filter.")

        with self.engine.connect() as connection:
            summary = dict(
                connection.execute(
                    text(
                        """SELECT COUNT(*)::int AS total,
                                  COUNT(*) FILTER (WHERE status='SUBMITTED')::int AS submitted,
                                  COUNT(*) FILTER (WHERE status='IN_REVIEW')::int AS in_review,
                                  COUNT(*) FILTER (WHERE status='CLOSED')::int AS closed
                           FROM contact_enquiries"""
                    )
                )
                .mappings()
                .one()
            )
            rows = connection.execute(
                text(
                    """SELECT contact_enquiry_id, name, email, mobile, website_url,
                              purpose, status, created_at, updated_at
                       FROM contact_enquiries
                       WHERE (CAST(:purpose AS varchar) IS NULL OR purpose=:purpose)
                         AND (CAST(:status AS varchar) IS NULL OR status=:status)
                         AND (NOT :has_search
                              OR name ILIKE :search
                              OR email ILIKE :search
                              OR mobile ILIKE :search
                              OR COALESCE(website_url, '') ILIKE :search)
                       ORDER BY created_at DESC, contact_enquiry_id DESC
                       LIMIT 500"""
                ),
                {
                    "purpose": normalized_purpose,
                    "status": normalized_status,
                    "has_search": bool(query),
                    "search": f"%{query}%",
                },
            ).mappings()
            enquiries = [dict(row) for row in rows]
        return {"summary": summary, "enquiries": enquiries}
