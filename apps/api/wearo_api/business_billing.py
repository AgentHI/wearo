from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine, text

from .business_onboarding import InvoiceDetails, validate_invoice_details
from .tenant_scope import TenantScopeError, require_tenant_scope


class BusinessBillingError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class BillingProfileUpdate:
    billing_email: str
    billing_phone: str | None
    legal_name: str
    tax_identifier: str | None
    billing_address: dict[str, str]
    tax_invoice_requested: bool
    reason: str


class PostgresBusinessBilling:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @staticmethod
    def _require_owner(connection: Connection, principal_id: UUID, tenant_id: UUID) -> UUID:
        try:
            return require_tenant_scope(
                connection, principal_id, tenant_id, roles=frozenset({"OWNER"})
            ).account_id
        except TenantScopeError:
            raise BusinessBillingError(
                "BILLING_PROFILE_UNAVAILABLE", "Resource unavailable."
            ) from None

    def get(self, principal_id: UUID, tenant_id: UUID) -> dict[str, object]:
        with self.engine.connect() as connection:
            account_id = self._require_owner(connection, principal_id, tenant_id)
            profile = (
                connection.execute(
                    text(
                        """
                    SELECT legal_name, billing_email, billing_phone, billing_address,
                           tax_identifier, tax_invoice_requested, jurisdiction, updated_at
                    FROM business_profiles
                    WHERE tenant_id = :tenant AND account_id = :account
                    """
                    ),
                    {"tenant": tenant_id, "account": account_id},
                )
                .mappings()
                .one_or_none()
            )
            if profile is None:
                raise BusinessBillingError("BILLING_PROFILE_UNAVAILABLE", "Resource unavailable.")
            invoices = tuple(
                dict(row)
                for row in connection.execute(
                    text(
                        """
                        SELECT invoice_id, invoice_number, issued_at, amount_minor, currency,
                               business_snapshot, tax_snapshot, document_url
                        FROM invoices WHERE account_id = :account
                        ORDER BY issued_at DESC, invoice_id DESC
                        """
                    ),
                    {"account": account_id},
                ).mappings()
            )
        return {"current": dict(profile), "issued_invoices": invoices}

    def update(
        self, principal_id: UUID, tenant_id: UUID, change: BillingProfileUpdate
    ) -> dict[str, object]:
        reason = change.reason.strip()
        if not reason or len(reason) > 500:
            raise BusinessBillingError("CHANGE_REASON_REQUIRED", "A change reason is required.")
        email = change.billing_email.strip().casefold()
        if email.count("@") != 1 or len(email) > 320:
            raise BusinessBillingError("INVALID_BILLING_EMAIL", "Enter a valid billing email.")
        phone = change.billing_phone.strip() if change.billing_phone else None
        if not change.legal_name.strip():
            raise BusinessBillingError("INVALID_LEGAL_NAME", "Legal business name is required.")
        with self.engine.begin() as connection:
            account_id = self._require_owner(connection, principal_id, tenant_id)
            before = (
                connection.execute(
                    text(
                        """
                    SELECT legal_name, billing_email, billing_phone, billing_address,
                           tax_identifier, tax_invoice_requested, jurisdiction
                    FROM business_profiles
                    WHERE tenant_id = :tenant AND account_id = :account FOR UPDATE
                    """
                    ),
                    {"tenant": tenant_id, "account": account_id},
                )
                .mappings()
                .one_or_none()
            )
            if before is None:
                raise BusinessBillingError("BILLING_PROFILE_UNAVAILABLE", "Resource unavailable.")
            invoice = validate_invoice_details(
                before["jurisdiction"],
                InvoiceDetails(
                    requested=change.tax_invoice_requested,
                    legal_name=change.legal_name,
                    tax_identifier=change.tax_identifier,
                    billing_address=change.billing_address,
                ),
            )
            legal_name = invoice.legal_name or change.legal_name.strip()
            address = invoice.billing_address or {}
            connection.execute(
                text(
                    """
                    UPDATE business_profiles
                    SET legal_name = :legal_name, billing_email = :email,
                        billing_phone = :phone, billing_address = CAST(:address AS jsonb),
                        tax_identifier = :tax_identifier,
                        tax_invoice_requested = :invoice_requested, updated_at = :now
                    WHERE tenant_id = :tenant AND account_id = :account
                    """
                ),
                {
                    "legal_name": legal_name,
                    "email": email,
                    "phone": phone,
                    "address": json.dumps(address),
                    "tax_identifier": invoice.tax_identifier,
                    "invoice_requested": invoice.requested,
                    "now": datetime.now(UTC),
                    "tenant": tenant_id,
                    "account": account_id,
                },
            )
            after = {
                "legal_name": legal_name,
                "billing_email": email,
                "billing_phone": phone,
                "billing_address": address,
                "tax_identifier": invoice.tax_identifier,
                "tax_invoice_requested": invoice.requested,
                "jurisdiction": before["jurisdiction"],
            }
            connection.execute(
                text(
                    """
                    INSERT INTO audit_events
                        (audit_event_id, account_id, tenant_id, actor_type, actor_id,
                         action, target_type, target_id, reason, before_summary,
                         after_summary, occurred_at)
                    VALUES
                        (:event, :account, :tenant, 'PRINCIPAL', :actor,
                         'BUSINESS_BILLING_PROFILE_UPDATED', 'BUSINESS_PROFILE', :tenant,
                         :reason, CAST(:before AS jsonb), CAST(:after AS jsonb), :now)
                    """
                ),
                {
                    "event": uuid4(),
                    "account": account_id,
                    "tenant": tenant_id,
                    "actor": principal_id,
                    "reason": reason,
                    "before": json.dumps(dict(before), default=str),
                    "after": json.dumps(after),
                    "now": datetime.now(UTC),
                },
            )
        return after
