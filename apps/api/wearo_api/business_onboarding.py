from __future__ import annotations

import json
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from .business_platform import OperatingProfile
from .email_otp import normalize_destination, normalize_email


class BusinessOnboardingError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class BusinessRegistration:
    registration_id: UUID
    account_id: UUID
    tenant_id: UUID
    principal_id: UUID
    identity_id: UUID
    slug: str
    email: str


@dataclass(frozen=True)
class InvoiceDetails:
    requested: bool = False
    legal_name: str | None = None
    tax_identifier: str | None = None
    billing_address: dict[str, str] | None = None


def validate_invoice_details(jurisdiction: str, details: InvoiceDetails) -> InvoiceDetails:
    if not details.requested:
        return InvoiceDetails()
    legal_name = (details.legal_name or "").strip()
    address = {key: value.strip() for key, value in (details.billing_address or {}).items()}
    if len(address) > 10 or any(
        len(key) > 40 or len(value) > 200 for key, value in address.items()
    ):
        raise BusinessOnboardingError("INVALID_BILLING_ADDRESS", "Billing address is too large.")
    required_address = ("line1", "city", "postal_code")
    if not legal_name or any(not address.get(key) for key in required_address):
        raise BusinessOnboardingError(
            "INVOICE_DETAILS_REQUIRED",
            "Legal name and billing address are required for tax invoices.",
        )
    tax_identifier = (details.tax_identifier or "").strip().upper() or None
    if jurisdiction == "IN" and tax_identifier is None:
        raise BusinessOnboardingError(
            "TAX_IDENTIFIER_REQUIRED", "GSTIN is required for an Indian tax invoice."
        )
    if jurisdiction == "IN" and not re.fullmatch(
        r"[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][A-Z0-9]Z[A-Z0-9]", tax_identifier or ""
    ):
        raise BusinessOnboardingError("INVALID_TAX_IDENTIFIER", "Enter a valid GSTIN.")
    return InvoiceDetails(True, legal_name, tax_identifier, address)


def normalized_slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().casefold()).strip("-")
    if not 3 <= len(slug) <= 60:
        raise BusinessOnboardingError(
            "INVALID_BUSINESS_NAME", "Business name must produce a 3 to 60 character identifier."
        )
    return slug


class PostgresBusinessOnboarding:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def register(
        self,
        *,
        idempotency_key: str,
        business_name: str,
        email: str,
        primary_mobile: str | None,
        operating_profile: OperatingProfile,
        jurisdiction: str,
        website_url: str | None,
        invoice_details: InvoiceDetails | None = None,
    ) -> BusinessRegistration:
        if not 8 <= len(idempotency_key) <= 100:
            raise BusinessOnboardingError("INVALID_IDEMPOTENCY_KEY", "Invalid registration key.")
        normalized = normalize_email(email)
        if not normalized:
            raise BusinessOnboardingError("INVALID_EMAIL", "Enter a valid work email address.")
        mobile = normalize_destination(primary_mobile or "") if primary_mobile else None
        if primary_mobile and (mobile is None or "@" in mobile):
            raise BusinessOnboardingError(
                "INVALID_MOBILE", "Enter a mobile number with its international country code."
            )
        country = jurisdiction.strip().upper()
        if len(country) != 2 or not country.isalpha():
            raise BusinessOnboardingError("INVALID_JURISDICTION", "Use a two-letter country code.")
        name = business_name.strip()
        if not name or len(name) > 200:
            raise BusinessOnboardingError("INVALID_BUSINESS_NAME", "Enter a valid business name.")
        base_slug = normalized_slug(name)
        invoice = validate_invoice_details(country, invoice_details or InvoiceDetails())
        with self.engine.begin() as connection:
            existing = (
                connection.execute(
                    text(
                        """
                    SELECT r.registration_id, r.account_id, r.tenant_id, r.principal_id,
                           r.identity_id, t.slug, i.normalized_value
                    FROM business_registrations r
                    JOIN business_tenants t ON t.tenant_id = r.tenant_id
                    JOIN principal_identities i ON i.identity_id = r.identity_id
                    WHERE r.idempotency_key = :key
                    """
                    ),
                    {"key": idempotency_key},
                )
                .mappings()
                .one_or_none()
            )
            if existing:
                return BusinessRegistration(
                    registration_id=existing["registration_id"],
                    account_id=existing["account_id"],
                    tenant_id=existing["tenant_id"],
                    principal_id=existing["principal_id"],
                    identity_id=existing["identity_id"],
                    slug=existing["slug"],
                    email=existing["normalized_value"],
                )
            registration_id, account_id, tenant_id = uuid4(), uuid4(), uuid4()
            principal_id, identity_id = uuid4(), uuid4()
            wallet_id, bucket_id, promo_bucket_id = uuid4(), uuid4(), uuid4()
            slug_exists: bool = bool(
                connection.execute(
                    text("SELECT EXISTS (SELECT 1 FROM business_tenants WHERE slug=:slug)"),
                    {"slug": base_slug},
                ).scalar_one()
            )
            slug = base_slug
            if slug_exists:
                suffix = 1000 + tenant_id.int % 9000
                for offset in range(9000):
                    candidate = f"{base_slug[:55]}-{1000 + (suffix - 1000 + offset) % 9000}"
                    candidate_exists = bool(
                        connection.execute(
                            text("SELECT EXISTS (SELECT 1 FROM business_tenants WHERE slug=:slug)"),
                            {"slug": candidate},
                        ).scalar_one()
                    )
                    if not candidate_exists:
                        slug = candidate
                        break
                else:
                    raise BusinessOnboardingError(
                        "BUSINESS_SLUG_UNAVAILABLE", "A unique business URL could not be created."
                    )
            public_code = ""
            for _ in range(100):
                candidate_code = f"{secrets.randbelow(100_000_000):08d}"
                code_exists = bool(
                    connection.execute(
                        text(
                            "SELECT EXISTS (SELECT 1 FROM business_shop_links "
                            "WHERE public_code=:code)"
                        ),
                        {"code": candidate_code},
                    ).scalar_one()
                )
                if not code_exists:
                    public_code = candidate_code
                    break
            if not public_code:
                raise BusinessOnboardingError(
                    "PUBLIC_CODE_UNAVAILABLE", "A unique business link could not be created."
                )
            try:
                connection.execute(
                    text("INSERT INTO accounts (account_id, kind) VALUES (:id, 'TENANT')"),
                    {"id": account_id},
                )
                connection.execute(
                    text(
                        """INSERT INTO principals
                        (principal_id, account_id, account_kind, principal_type)
                        VALUES (:principal, :account, 'TENANT', 'BUSINESS')"""
                    ),
                    {"principal": principal_id, "account": account_id},
                )
                connection.execute(
                    text(
                        """INSERT INTO principal_identities
                        (identity_id, account_id, principal_id, channel, normalized_value)
                        VALUES (:identity, :account, :principal, 'EMAIL', :email)"""
                    ),
                    {
                        "identity": identity_id,
                        "account": account_id,
                        "principal": principal_id,
                        "email": normalized,
                    },
                )
                if mobile:
                    connection.execute(
                        text(
                            """INSERT INTO principal_identities
                            (identity_id, account_id, principal_id, channel, normalized_value)
                            VALUES (:identity, :account, :principal, 'PHONE', :mobile)"""
                        ),
                        {
                            "identity": uuid4(),
                            "account": account_id,
                            "principal": principal_id,
                            "mobile": mobile,
                        },
                    )
                connection.execute(
                    text(
                        """INSERT INTO business_tenants (tenant_id, account_id, slug)
                        VALUES (:tenant, :account, :slug)"""
                    ),
                    {"tenant": tenant_id, "account": account_id, "slug": slug},
                )
                connection.execute(
                    text(
                        """INSERT INTO tenant_memberships
                        (tenant_id, account_id, principal_id, role)
                        VALUES (:tenant, :account, :principal, 'OWNER')"""
                    ),
                    {"tenant": tenant_id, "account": account_id, "principal": principal_id},
                )
                connection.execute(
                    text(
                        """INSERT INTO business_profiles
                        (tenant_id, account_id, legal_name, display_name, operating_profile,
                         jurisdiction, billing_email, website_url, tax_invoice_requested,
                         tax_identifier, billing_address)
                        VALUES
                        (:tenant, :account, :legal_name, :name, :profile, :country, :email,
                         :website, :invoice_requested, :tax_identifier,
                         CAST(:billing_address AS jsonb))"""
                    ),
                    {
                        "tenant": tenant_id,
                        "account": account_id,
                        "name": name,
                        "legal_name": invoice.legal_name or name,
                        "profile": operating_profile,
                        "country": country,
                        "email": normalized,
                        "website": website_url,
                        "invoice_requested": invoice.requested,
                        "tax_identifier": invoice.tax_identifier,
                        "billing_address": json.dumps(invoice.billing_address or {}),
                    },
                )
                connection.execute(
                    text("INSERT INTO wallets (wallet_id, account_id) VALUES (:wallet, :account)"),
                    {"wallet": wallet_id, "account": account_id},
                )
                connection.execute(
                    text(
                        """INSERT INTO wallet_buckets
                        (bucket_id, account_id, wallet_id, bucket_type)
                        VALUES (:bucket, :account, :wallet, 'PURCHASED')"""
                    ),
                    {"bucket": bucket_id, "account": account_id, "wallet": wallet_id},
                )
                connection.execute(
                    text(
                        """INSERT INTO wallet_buckets
                        (bucket_id, account_id, wallet_id, bucket_type, expires_at)
                        VALUES (:bucket, :account, :wallet, 'PROMO',
                                '2027-01-31 23:59:59+00')"""
                    ),
                    {"bucket": promo_bucket_id, "account": account_id, "wallet": wallet_id},
                )
                connection.execute(
                    text(
                        """INSERT INTO ledger_entries
                        (entry_id, account_id, tenant_id, wallet_id, bucket_id, entry_type,
                         amount, operation_key, performed_by_principal_id)
                        VALUES (:entry, :account, :tenant, :wallet, :bucket, 'CREDIT',
                                1000, 'pilot-business-starter-2026-10', :principal)"""
                    ),
                    {
                        "entry": uuid4(),
                        "account": account_id,
                        "tenant": tenant_id,
                        "wallet": wallet_id,
                        "bucket": promo_bucket_id,
                        "principal": principal_id,
                    },
                )
                connection.execute(
                    text(
                        """INSERT INTO offering_entitlements
                        (account_id, tenant_id, offering, enabled, effective_from)
                        VALUES (:account, :tenant, 'BUSINESS', true, :now)"""
                    ),
                    {"account": account_id, "tenant": tenant_id, "now": datetime.now(UTC)},
                )
                connection.execute(
                    text(
                        """INSERT INTO business_shop_links (tenant_id, account_id, public_code)
                        VALUES (:tenant, :account, :public_code)"""
                    ),
                    {"tenant": tenant_id, "account": account_id, "public_code": public_code},
                )
                connection.execute(
                    text(
                        """INSERT INTO business_allowance_policies
                        (tenant_id, account_id, default_try_on_limit, period,
                         updated_by_principal_id)
                        VALUES (:tenant, :account, 3, 'DAY', :principal)"""
                    ),
                    {"tenant": tenant_id, "account": account_id, "principal": principal_id},
                )
                connection.execute(
                    text(
                        """INSERT INTO business_registrations
                        (registration_id, idempotency_key, account_id, tenant_id,
                         principal_id, identity_id)
                        VALUES
                        (:registration, :key, :account, :tenant, :principal, :identity)"""
                    ),
                    {
                        "registration": registration_id,
                        "key": idempotency_key,
                        "account": account_id,
                        "tenant": tenant_id,
                        "principal": principal_id,
                        "identity": identity_id,
                    },
                )
            except IntegrityError as error:
                raise BusinessOnboardingError(
                    "REGISTRATION_CONFLICT", "This business identity is already registered."
                ) from error
        return BusinessRegistration(
            registration_id, account_id, tenant_id, principal_id, identity_id, slug, normalized
        )
