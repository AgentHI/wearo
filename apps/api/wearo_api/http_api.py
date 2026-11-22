from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import logging
import os
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any, Literal, cast
from urllib.parse import urlencode
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import FastAPI, File, Form, Header, Query, Request, Response, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine, text

from .account_lifecycle import AccountLifecycleError, PostgresAccountLifecycle
from .admin_ai_costs import AdminAiCostError, PostgresAdminAiCosts, PostgresTryOnRouteRegistry
from .admin_audit import AdminAuditError, PostgresAdminAudit
from .admin_billing import AdminBillingError, PostgresAdminBilling
from .admin_customers import AdminCustomerError, PostgresAdminCustomers
from .admin_dashboard import AdminDashboardError, PostgresAdminDashboard
from .admin_enquiries import AdminEnquiryError, PostgresAdminEnquiries
from .admin_operations import AdminOperationsError, PostgresAdminOperations
from .admin_organizations import (
    AdminOrganizationError,
    OrganizationAction,
    PostgresAdminOrganizations,
)
from .admin_platform_controls import (
    AdminPlatformControlError,
    ControlAction,
    ControlScope,
    PostgresAdminPlatformControls,
)
from .admin_pricing import AdminPricingError, PostgresAdminPricing
from .admin_realtime import AdminRealtimeError, PostgresAdminRealtime
from .admin_revenue import AdminRevenueError, PostgresAdminRevenue
from .admin_service_health import current_service_health
from .admin_subscriptions import (
    AdminSubscriptionError,
    PostgresAdminSubscriptions,
    SubscriptionAction,
)
from .admin_support import AdminSupportError, PostgresAdminSupport
from .admin_usage_analytics import AdminUsageAnalyticsError, PostgresAdminUsageAnalytics
from .beta_profile import (
    FreeTryOnQuotaService,
    PersonProfile,
    PersonProfileService,
    ProfileError,
    ProfileImage,
)
from .billing_history_pdf import billing_history_pdf
from .browser_sessions import (
    BrowserSession,
    BrowserSessionService,
    SessionAuthenticationError,
    SessionPolicy,
)
from .business_agents import BusinessAgentError, PostgresBusinessAgents
from .business_allowances import (
    AllowanceAction,
    BusinessAllowanceError,
    PostgresBusinessAllowances,
)
from .business_billing import (
    BillingProfileUpdate,
    BusinessBillingError,
    PostgresBusinessBilling,
)
from .business_membership import (
    BusinessMembershipError,
    MembershipRole,
    PostgresBusinessMembership,
)
from .business_onboarding import (
    BusinessOnboardingError,
    InvoiceDetails,
    PostgresBusinessOnboarding,
)
from .business_platform import (
    BusinessPlatformError,
    OperatingProfile,
    PostgresBusinessPlatform,
    recommendation_for,
)
from .business_reports import BusinessReportError, PostgresBusinessReports, reconciliation_csv
from .business_shop import BusinessShopError, PostgresBusinessShop, qr_poster
from .business_smart_ads import (
    DeliveryChannel,
    OpenAISmartAdGenerator,
    PostgresBusinessSmartAds,
    SmartAdError,
    TargetGender,
)
from .business_stores import BusinessStoreError, PostgresBusinessStores
from .business_tryon_status import (
    BusinessTryOnStatusError,
    PostgresBusinessTryOnStatus,
)
from .catalog import CatalogCollection, CatalogError, CatalogItem, CatalogService, PublishState
from .communications_governance import (
    CommunicationChannel,
    CommunicationsError,
    CommunicationTopic,
    PostgresCommunicationsGovernance,
)
from .consent import ConsentAttestation, ConsentError, ConsentService
from .contact_enquiries import (
    ContactEnquiryError,
    ContactPurpose,
    PostgresContactEnquiries,
)
from .database import create_database_engine
from .durable_worker import DurableRenderWorker
from .email_otp import (
    AuthRealm,
    EmailDeliveryProvider,
    EmailOtpPolicy,
    EmailOtpService,
    OtpAuthenticationError,
)
from .environment import load_wearo_environment
from .external_runtime import (
    AnalysisServiceError,
    HttpAnalysisClient,
    OpenAIAnalysisClient,
)
from .google_drive import (
    DriveIntegrationError,
    DriveSyncWorker,
    GoogleDriveConfig,
    GoogleDriveService,
)
from .home_captions import HomeCaptionService
from .image_preflight import ImagePreflightService, VisionAnalyzer
from .media_runtime import MediaRuntimeError, PostgresMediaRuntime, private_blob_store_from_env
from .notification_delivery import (
    TEMPLATE_DEFINITIONS,
    NotificationError,
    OpenAITemplateGenerator,
    PostgresNotificationService,
    template_variable_names,
)
from .plan_usage import BUSINESS_REPORTING_TIMEZONE, PostgresPlanUsage
from .platform_admin_auth import PlatformAdminAuth
from .platform_identity import PlatformIdentityError, PostgresPlatformIdentity
from .postgres_auth import (
    DevelopmentPostgresOtpStore,
    PostgresBrowserSessionStore,
    PostgresEmailOtpStore,
)
from .postgres_beta import (
    PostgresConsentStore,
    PostgresProfileStore,
    PostgresQuotaStore,
    PostgresQuoteStore,
    decimal_or_none,
)
from .postgres_catalog import PostgresCatalogStore
from .postgres_retention import PostgresLifecycleStore
from .render_preflight import BetaRenderPreflightService, RenderPreflightError
from .render_runtime import DurableRenderError, DurableRenderJob, PostgresRenderRuntime
from .retail_tryon_pricing import PostgresRetailTryOnPricing, RetailTryOnPricingError
from .retention import LifecycleError, RetentionService
from .sensitive_audit import PostgresSensitiveAudit, SensitiveAuditError
from .sms_delivery import AwsSmsDeliveryProvider, AwsSmsSettings, HttpSmsDeliveryProvider
from .smtp_email import SmtpEmailDeliveryProvider, SmtpSettings
from .sponsored_tryons import PostgresSponsoredTryOns, SponsoredTryOnError
from .store_advertisements import (
    OpenAIAdvertisementGenerator,
    PostgresStoreAdvertisements,
    StoreAdvertisementError,
)
from .support_access import PostgresSupportAccess, SupportAccessError
from .support_cases import CaseType, PostgresSupportCases, SupportCaseError
from .topups import (
    HttpPaymentGateway,
    PostgresTopUps,
    RazorpayPaymentGateway,
    TopUpError,
    UnavailablePaymentGateway,
)
from .tryon_authorization import BusinessTryOnStatus, TryOnAuthorizationError
from .wallet_billing import PostgresWalletBilling
from .wallet_transactions import (
    PostgresWalletTransactions,
    TransactionCategory,
    WalletTransactionError,
    transactions_csv,
)

IST = ZoneInfo("Asia/Kolkata")
logger = logging.getLogger(__name__)


class ApiProblem(ValueError):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code


class UnavailableEmailProvider:
    def send_sign_in_code(self, **_: object) -> None:
        raise ApiProblem(503, "EMAIL_DELIVERY_UNAVAILABLE", "Email delivery is not configured.")


@dataclass(frozen=True)
class ApiContainer:
    engine: Engine
    otp: EmailOtpService
    sessions: BrowserSessionService
    media: PostgresMediaRuntime
    consents: ConsentService
    profiles: PersonProfileService
    quota: FreeTryOnQuotaService
    renders: PostgresRenderRuntime
    retention: RetentionService | None = None
    catalog: CatalogService | None = None
    business_platform: PostgresBusinessPlatform | None = None
    plan_usage: PostgresPlanUsage | None = None
    platform_identity: PostgresPlatformIdentity | None = None
    business_onboarding: PostgresBusinessOnboarding | None = None
    business_billing: PostgresBusinessBilling | None = None
    business_membership: PostgresBusinessMembership | None = None
    wallet_billing: PostgresWalletBilling | None = None
    wallet_transactions: PostgresWalletTransactions | None = None
    topups: PostgresTopUps | None = None
    sensitive_audit: PostgresSensitiveAudit | None = None
    business_agents: PostgresBusinessAgents | None = None
    business_stores: PostgresBusinessStores | None = None
    store_advertisements: PostgresStoreAdvertisements | None = None
    business_smart_ads: PostgresBusinessSmartAds | None = None
    business_shop: PostgresBusinessShop | None = None
    business_tryon_status: PostgresBusinessTryOnStatus | None = None
    business_allowances: PostgresBusinessAllowances | None = None
    communications: PostgresCommunicationsGovernance | None = None
    business_reports: PostgresBusinessReports | None = None
    support_cases: PostgresSupportCases | None = None
    support_access: PostgresSupportAccess | None = None
    sponsored_tryons: PostgresSponsoredTryOns | None = None
    account_lifecycle: PostgresAccountLifecycle | None = None
    preflight: BetaRenderPreflightService | None = None
    secure_cookie: bool = True
    registration_test_otp: str | None = None
    platform_admin_auth: PlatformAdminAuth | None = None
    admin_organizations: PostgresAdminOrganizations | None = None
    admin_dashboard: PostgresAdminDashboard | None = None
    admin_enquiries: PostgresAdminEnquiries | None = None
    admin_usage_analytics: PostgresAdminUsageAnalytics | None = None
    admin_realtime: PostgresAdminRealtime | None = None
    admin_customers: PostgresAdminCustomers | None = None
    admin_subscriptions: PostgresAdminSubscriptions | None = None
    admin_pricing: PostgresAdminPricing | None = None
    admin_billing: PostgresAdminBilling | None = None
    admin_revenue: PostgresAdminRevenue | None = None
    admin_operations: PostgresAdminOperations | None = None
    admin_platform_controls: PostgresAdminPlatformControls | None = None
    admin_audit: PostgresAdminAudit | None = None
    admin_ai_costs: PostgresAdminAiCosts | None = None
    contact_enquiries: PostgresContactEnquiries | None = None
    home_captions: HomeCaptionService | None = None
    contact_form_token: bytes = b""
    google_drive: GoogleDriveService | None = None


class OtpRequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    destination: str
    purpose: str = "SIGN_IN"


class ContactEnquiryBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=320)
    mobile: str = Field(min_length=7, max_length=32, pattern=r"^[0-9+() .-]+$")
    website_url: str | None = Field(default=None, max_length=2048)
    purpose: ContactPurpose


class TopUpOrderBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pack_id: UUID
    idempotency_key: str = Field(min_length=8, max_length=100)


class ConsumerTopUpOrderBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retail_package_id: UUID
    idempotency_key: str = Field(min_length=8, max_length=100)


class GoogleDriveSettingsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    auto_sync_enabled: bool


class RazorpayVerificationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    razorpay_payment_id: str | None = Field(default=None, max_length=100)
    razorpay_order_id: str | None = Field(default=None, max_length=100)
    razorpay_signature: str | None = Field(default=None, max_length=256)


class OperatingProfileUpdateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operating_profile: OperatingProfile
    reason: str = Field(min_length=1, max_length=500)


class CustomerExperienceSettingsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image_retention_days: int = Field(ge=1, le=30)
    profile_deletion_hours: int = Field(ge=1, le=24)
    reason: str = Field(min_length=1, max_length=500)


class BusinessAgentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    mobile: str = Field(min_length=7, max_length=32)
    store_id: UUID


class BusinessStoreBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    code: str = Field(min_length=1, max_length=40)
    admin_email: str = Field(min_length=3, max_length=320)
    admin_mobile: str = Field(min_length=7, max_length=32)


class AdvertisementGenerateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=120)
    prompt: str = Field(min_length=1, max_length=1000)
    starts_on: date
    ends_on: date
    advertisement_id: UUID | None = None


class AdvertisementUpdateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=120)
    prompt: str | None = Field(default=None, max_length=1000)
    starts_on: date
    ends_on: date


class AdvertisementActivationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    active_date: date


class SmartAdUpdateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=120)
    prompt: str = Field(min_length=1, max_length=2000)


class SmartAdScheduleBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    smart_ad_id: UUID
    occasion: str = Field(min_length=1, max_length=160)
    scheduled_for: datetime
    channel: DeliveryChannel = "EMAIL"
    target_gender: TargetGender = "female"
    target_age_min: int | None = Field(default=None, ge=1, le=120)
    target_age_max: int | None = Field(default=None, ge=1, le=120)


class AgentMoveBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    store_id: UUID


class AllowancePolicyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    default_try_on_limit: int = Field(ge=0, le=100000)


class BusinessTryOnStatusBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: BusinessTryOnStatus


class UserAllowanceBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mobile: str = Field(min_length=7, max_length=32)
    action: AllowanceAction
    amount: int = Field(default=0, ge=0, le=100000)


class SponsoredSessionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(min_length=8, max_length=36)


class SponsoredTryOnBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_key: str = Field(min_length=8, max_length=80)


class CommunicationPreferenceBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    channel: CommunicationChannel
    topic: CommunicationTopic
    enabled: bool


class SupportCaseBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_type: CaseType
    reason: str = Field(min_length=1, max_length=2000)


class OtpVerifyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    challenge_id: UUID
    code: str = Field(min_length=4, max_length=8)


class ConsentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_asset_id: UUID
    adult_confirmed: bool
    depicted_person_permission: bool
    transformation_approved: bool
    retention_notice_acknowledged: bool
    no_training_notice_acknowledged: bool


class ProfileImageBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    person_asset_id: UUID
    consent_id: UUID
    photo_type: Literal["FULL_BODY", "CLOSE_UP", "OTHER"]
    label: str = Field(min_length=1, max_length=60)
    is_primary: bool = False


class ProfileBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    person_asset_id: UUID | None = None
    consent_id: UUID | None = None
    images: list[ProfileImageBody] = Field(default_factory=list, max_length=10)
    height_cm: float | None = Field(default=None, ge=80, le=260)
    weight_kg: float | None = Field(default=None, ge=20, le=350)


class QuoteBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_asset_id: UUID
    person_asset_id: UUID
    sponsored_session_id: UUID | None = None


class RenderBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quote_id: UUID


class CollectionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    publish_state: PublishState = "DRAFT"


class CatalogItemBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category_id: UUID
    item_code: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=200)
    attributes: dict[str, object] = Field(default_factory=dict)
    price_minor: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    publish_state: PublishState = "DRAFT"
    collection_ids: list[UUID] = Field(default_factory=list, max_length=50)


class BusinessRegistrationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    business_name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=320)
    primary_mobile: str = Field(min_length=7, max_length=32)
    email_otp: str = Field(min_length=4, max_length=8)
    mobile_otp: str = Field(min_length=4, max_length=8)
    operating_profile: Literal[
        "BOUTIQUE", "CLOTHING_RETAILER", "JEWELLERY_RETAILER", "ENTERPRISE_CHAIN", "OTHER"
    ]
    jurisdiction: str = Field(min_length=2, max_length=2)
    website_url: str | None = Field(default=None, max_length=2048)
    tax_invoice_requested: bool = False
    legal_name: str | None = Field(default=None, max_length=200)
    tax_identifier: str | None = Field(default=None, max_length=80)
    billing_address: dict[str, str] | None = None
    company_logo_data_url: str | None = Field(default=None, max_length=2_800_000)


class BillingProfileBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    billing_email: str = Field(min_length=3, max_length=320)
    billing_phone: str | None = Field(default=None, max_length=32)
    legal_name: str = Field(min_length=1, max_length=200)
    tax_identifier: str | None = Field(default=None, max_length=80)
    billing_address: dict[str, str] = Field(default_factory=dict)
    tax_invoice_requested: bool
    reason: str = Field(min_length=1, max_length=500)


class MembershipChangeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: MembershipRole | None = None
    reason: str = Field(min_length=1, max_length=500)


class OwnerContactUpdateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel: Literal["email", "mobile"]
    value: str = Field(min_length=3, max_length=320)
    otp: str = Field(min_length=4, max_length=8)
    reason: str = Field(min_length=1, max_length=500)


def _problem(status: int, code: str, message: str, request_id: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"code": code, "message": message, "request_id": request_id},
    )


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", uuid4().hex)


CONSUMER_SESSION_COOKIE = "wearo_consumer_session"
BUSINESS_SESSION_COOKIE = "wearo_business_session"
AGENT_SESSION_COOKIE = "wearo_agent_session"
STORE_SESSION_COOKIE = "wearo_store_session"
LEGACY_SESSION_COOKIE = "wearo_session"
ADMIN_SESSION_COOKIE = "wearo_admin_session"


class AdminLoginBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class AdminOrganizationStatusBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: OrganizationAction
    reason: str = Field(min_length=1, max_length=500)


class AdminTokenAdjustmentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: int = Field(ge=-1_000_000, le=1_000_000)
    reason: str = Field(min_length=1, max_length=500)


class AdminCustomerTryOnLimitBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(ge=0, le=100_000)
    reason: str = Field(min_length=1, max_length=500)


class AdminSupportTokenCreditBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: int = Field(ge=1, le=1_000_000)
    reason: str = Field(min_length=1, max_length=500)


class AdminPlatformControlBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: ControlScope
    scope_key: str | None = Field(default=None, max_length=120)
    action: ControlAction
    reason: str = Field(min_length=1, max_length=500)
    confirmed: bool


class AdminSubscriptionTransitionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: SubscriptionAction
    reason: str = Field(min_length=1, max_length=500)


class AdminPlanAssignmentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_code: str = Field(min_length=1, max_length=40)
    next_billing_at: datetime | None = None
    reason: str = Field(min_length=1, max_length=500)


class AdminTrialExtensionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    days: int = Field(ge=1, le=365)
    reason: str = Field(min_length=1, max_length=500)


class AdminPricingSettingsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_code: str = Field(min_length=1, max_length=40)
    business_type: OperatingProfile | None = None
    monthly_fee_minor: int = Field(ge=0, le=1_000_000_000)
    try_on_token_cost: int = Field(ge=1, le=1_000_000)
    free_trial_tokens: int = Field(ge=0, le=10_000_000)
    trial_duration_days: int = Field(ge=1, le=365)
    payment_grace_days: int = Field(ge=0, le=90)
    gst_basis_points: int = Field(ge=0, le=10_000)
    reason: str = Field(min_length=1, max_length=500)


class AdminTokenPackageBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=40)
    business_type: OperatingProfile | None = None
    purchased_tokens: int = Field(ge=1, le=100_000_000)
    promo_tokens: int = Field(ge=0, le=100_000_000)
    amount_minor: int = Field(ge=1, le=1_000_000_000)
    discount_basis_points: int = Field(ge=0, le=10_000)
    gst_basis_points: int = Field(ge=0, le=10_000)
    reason: str = Field(min_length=1, max_length=500)


class AdminRetailTryOnPriceBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    price_minor: int = Field(ge=20, le=10_000_000, multiple_of=20)
    reason: str = Field(min_length=1, max_length=500)


class AdminRetailTryOnPackageBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    minimum_amount_minor: int = Field(ge=20, le=1_000_000_000, multiple_of=20)
    gst_basis_points: int = Field(ge=0, le=10_000)
    reason: str = Field(min_length=1, max_length=500)


class AdminRetailTryOnPackageDeleteBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=500)


class AdminAiProviderBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1, max_length=40)
    display_name: str = Field(min_length=1, max_length=120)
    adapter_type: str = Field(min_length=1, max_length=40)
    credential_env_name: str = Field(min_length=7, max_length=120)


class AdminAiModelBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider_id: UUID
    api_model_id: str = Field(min_length=1, max_length=160)
    display_name: str = Field(min_length=1, max_length=160)
    capability: str = Field(default="TRY_ON", min_length=1, max_length=40)
    region: str = Field(default="global", min_length=1, max_length=80)
    billing_method: Literal["TOKEN", "REQUEST", "IMAGE", "CREDIT"]
    input_unit_price_usd_micros: int = Field(default=0, ge=0)
    output_unit_price_usd_micros: int = Field(default=0, ge=0)
    request_price_usd_micros: int = Field(default=0, ge=0)
    fallback_cost_usd_micros: int = Field(default=0, ge=0)


class AdminProviderPurchaseBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider_id: UUID
    amount_minor: int = Field(gt=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    units_purchased: Decimal | None = Field(default=None, gt=0)
    unit_type: Literal["USD", "TOKEN", "IMAGE", "CREDIT"]
    reference: str | None = Field(default=None, max_length=160)
    purchased_at: datetime | None = None


class AdminAiStatusBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ACTIVE", "DISABLED", "ARCHIVED"]


class AdminCommunicationTemplateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    channel: Literal["EMAIL", "SMS", "WHATSAPP"]
    template_key: str = Field(min_length=1, max_length=80)
    category: Literal["NOTIFICATION", "SUPPORT", "BILLING"]
    display_name: str = Field(min_length=1, max_length=160)
    subject: str | None = Field(default=None, max_length=998)
    body: str = Field(min_length=1, max_length=20_000)
    signature: str | None = Field(default=None, max_length=2_000)
    generation_prompt: str | None = Field(default=None, max_length=4_000)
    status: Literal["DRAFT", "ACTIVE"] = "DRAFT"


class AdminTemplateGenerationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    channel: Literal["EMAIL", "SMS", "WHATSAPP"]
    template_key: str = Field(min_length=1, max_length=80)
    prompt: str = Field(min_length=3, max_length=4_000)
    reference_image: str | None = Field(default=None, max_length=7_000_000)


class NotificationEnqueueBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    channel: Literal["EMAIL", "SMS", "WHATSAPP"]
    template_key: str = Field(min_length=1, max_length=80)
    recipient: str = Field(min_length=3, max_length=320)
    variables: dict[str, object] = Field(default_factory=dict)
    metadata: dict[str, object] = Field(default_factory=dict)
    deduplication_key: str | None = Field(default=None, max_length=300)
    scheduled_at: datetime | None = None


class InboundSupportBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider_message_id: str = Field(min_length=1, max_length=500)
    sender_email: str = Field(min_length=3, max_length=320)
    recipient_email: str = Field(min_length=3, max_length=320)
    subject: str = Field(default="Support request", max_length=998)
    body_text: str = Field(default="", max_length=100_000)
    received_at: datetime


def _authenticate(
    request: Request,
    container: ApiContainer,
    *,
    mutation: bool = False,
    csrf_token: str | None = None,
    allow_deletion_pending: bool = False,
) -> BrowserSession:
    token = request.cookies.get(CONSUMER_SESSION_COOKIE) or request.cookies.get(
        LEGACY_SESSION_COOKIE, ""
    )
    try:
        return container.sessions.authenticate(
            token,
            expected_realm="SHOP",
            csrf_token=csrf_token,
            mutation=mutation,
            allowed_account_statuses=(
                frozenset({"ACTIVE", "DELETION_PENDING"})
                if allow_deletion_pending
                else frozenset({"ACTIVE"})
            ),
        )
    except SessionAuthenticationError:
        status = 403 if token and mutation else 401
        raise ApiProblem(status, "AUTHENTICATION_REQUIRED", "Authentication required.") from None


def _authenticate_business(
    request: Request,
    container: ApiContainer,
    *,
    mutation: bool = False,
    csrf_token: str | None = None,
) -> BrowserSession:
    token = request.cookies.get(BUSINESS_SESSION_COOKIE) or request.cookies.get(
        LEGACY_SESSION_COOKIE, ""
    )
    try:
        return container.sessions.authenticate(
            token,
            expected_realm="BUSINESS",
            csrf_token=csrf_token,
            mutation=mutation,
        )
    except SessionAuthenticationError:
        status = 403 if token and mutation else 401
        raise ApiProblem(status, "AUTHENTICATION_REQUIRED", "Authentication required.") from None


def _authenticate_agent(
    request: Request,
    container: ApiContainer,
    *,
    mutation: bool = False,
    csrf_token: str | None = None,
) -> BrowserSession:
    token = request.cookies.get(AGENT_SESSION_COOKIE, "")
    try:
        return container.sessions.authenticate(
            token,
            expected_realm="BUSINESS",
            csrf_token=csrf_token,
            mutation=mutation,
        )
    except SessionAuthenticationError:
        status = 403 if token and mutation else 401
        raise ApiProblem(status, "AUTHENTICATION_REQUIRED", "Authentication required.") from None


def _authenticate_store(
    request: Request,
    container: ApiContainer,
    *,
    mutation: bool = False,
    csrf_token: str | None = None,
) -> BrowserSession:
    token = request.cookies.get(STORE_SESSION_COOKIE, "")
    try:
        return container.sessions.authenticate(
            token, expected_realm="BUSINESS", csrf_token=csrf_token, mutation=mutation
        )
    except SessionAuthenticationError:
        status = 403 if token and mutation else 401
        raise ApiProblem(status, "AUTHENTICATION_REQUIRED", "Authentication required.") from None


def _authenticated_cookie(
    request: Request, container: ApiContainer, csrf_token: str | None
) -> tuple[str, str]:
    candidates: tuple[tuple[str, Literal["SHOP", "BUSINESS"]], ...] = (
        (CONSUMER_SESSION_COOKIE, "SHOP"),
        (BUSINESS_SESSION_COOKIE, "BUSINESS"),
        (LEGACY_SESSION_COOKIE, "SHOP"),
        (LEGACY_SESSION_COOKIE, "BUSINESS"),
    )
    for cookie_name, realm in candidates:
        token = request.cookies.get(cookie_name, "")
        if not token:
            continue
        try:
            container.sessions.authenticate(
                token,
                expected_realm=realm,
                csrf_token=csrf_token,
                mutation=True,
                allowed_account_statuses=frozenset({"ACTIVE", "DELETION_PENDING"}),
            )
            return cookie_name, token
        except SessionAuthenticationError:
            continue
    raise ApiProblem(403, "AUTHENTICATION_REQUIRED", "Authentication required.")


def _catalog_item_json(item: CatalogItem) -> dict[str, Any]:
    return {
        "item_id": item.item_id,
        "tenant_id": item.tenant_id,
        "category_id": item.category_id,
        "item_code": item.item_code,
        "title": item.title,
        "attributes": item.attributes,
        "price_minor": item.price_minor,
        "currency": item.currency,
        "publish_state": item.publish_state,
        "collection_ids": item.collection_ids,
    }


def _profile_json(profile: PersonProfile) -> dict[str, Any]:
    images = profile.images or (
        ProfileImage(
            profile_image_id=profile.profile_id,
            asset_id=profile.person_asset_id,
            consent_id=profile.consent_id,
            photo_type="FULL_BODY",
            label="Full body",
            is_primary=True,
        ),
    )
    return {
        "id": profile.profile_id,
        "person_asset_id": profile.person_asset_id,
        "consent_id": profile.consent_id,
        "height_cm": profile.height_cm,
        "weight_kg": profile.weight_kg,
        "status": profile.status,
        "last_used_at": profile.last_used_at,
        "images": [
            {
                "id": image.profile_image_id,
                "person_asset_id": image.asset_id,
                "consent_id": image.consent_id,
                "photo_type": image.photo_type,
                "label": image.label,
                "is_primary": image.is_primary,
            }
            for image in images
        ],
    }


def _job_json(job: DurableRenderJob) -> dict[str, Any]:
    states = {"PENDING": "QUEUED", "DELIVERED": "SUCCEEDED"}
    charge_states = {
        "PENDING": "RESERVED",
        "PROCESSING": "RESERVED",
        "DELIVERED": "SETTLED",
        "FAILED": "RELEASED",
        "CANCELLED": "RELEASED",
    }
    return {
        "render_id": job.job_id,
        "quote_id": job.quote_id,
        "status": states.get(job.status, job.status),
        "charge_status": charge_states[job.status],
        "cost_wearo_tokens": 0,
        "error_code": job.error_code,
        "result_asset_id": job.result_asset_id,
        "status_url": f"/api/v1/renders/{job.job_id}",
    }


def _public_origin(request: Request) -> str:
    """Return the configured browser origin, falling back to the request host."""
    return os.environ.get("WEARO_CONSUMER_ORIGIN", str(request.base_url)).rstrip("/")


def create_app(
    container: ApiContainer,
    *,
    embedded_worker: DurableRenderWorker | None = None,
    embedded_drive_worker: DriveSyncWorker | None = None,
) -> FastAPI:
    platform_admin_auth = container.platform_admin_auth
    admin_organizations = container.admin_organizations or PostgresAdminOrganizations(
        container.engine
    )
    platform_dashboard = container.admin_dashboard or PostgresAdminDashboard(container.engine)
    admin_enquiries = container.admin_enquiries or PostgresAdminEnquiries(container.engine)
    admin_usage_analytics = container.admin_usage_analytics or PostgresAdminUsageAnalytics(
        container.engine
    )
    admin_realtime = container.admin_realtime or PostgresAdminRealtime(
        container.engine, int(os.environ.get("WEARO_ESTIMATED_AI_COST_MINOR", "0"))
    )
    admin_ai_costs = container.admin_ai_costs or PostgresAdminAiCosts(container.engine)
    admin_customers = container.admin_customers or PostgresAdminCustomers(container.engine)
    admin_support = PostgresAdminSupport(container.engine)
    admin_subscriptions = container.admin_subscriptions or PostgresAdminSubscriptions(
        container.engine
    )
    admin_pricing = container.admin_pricing or PostgresAdminPricing(container.engine)
    retail_tryon_pricing = PostgresRetailTryOnPricing(container.engine)
    admin_billing = container.admin_billing or PostgresAdminBilling(container.engine)
    admin_revenue = container.admin_revenue or PostgresAdminRevenue(
        container.engine, int(os.environ.get("WEARO_ESTIMATED_AI_COST_MINOR", "0"))
    )
    admin_operations = container.admin_operations or PostgresAdminOperations(container.engine)
    admin_platform_controls = container.admin_platform_controls or PostgresAdminPlatformControls(
        container.engine
    )
    admin_audit = container.admin_audit or PostgresAdminAudit(container.engine)
    notifications = PostgresNotificationService(container.engine)
    template_generator = OpenAITemplateGenerator(
        os.environ.get("WEARO_OPENAI_API_KEY", ""),
        os.environ.get("WEARO_NOTIFICATION_AI_MODEL", "gpt-5-mini"),
    )
    home_captions = container.home_captions or HomeCaptionService(
        os.environ.get("WEARO_OPENAI_API_KEY", ""),
        os.environ.get("WEARO_HOME_CAPTION_MODEL", "gpt-5-mini"),
    )
    admin_email = os.environ.get("WEARO_ADMIN_EMAIL", "")
    admin_password = os.environ.get("WEARO_ADMIN_PASSWORD", "")
    if platform_admin_auth is None and admin_email and admin_password:
        platform_admin_auth = PlatformAdminAuth(admin_email, admin_password)
    stop_worker = threading.Event()
    worker_threads: list[threading.Thread] = []

    def run_embedded_worker() -> None:
        worker = embedded_worker
        if worker is None:
            return
        while not stop_worker.is_set():
            try:
                worker.recover_stale()
                outcome = worker.run_once()
                drive_claimed = False
                if embedded_drive_worker is not None:
                    embedded_drive_worker.recover_expired()
                    drive_claimed = embedded_drive_worker.run_once()
            except Exception:
                logger.exception("Local embedded render worker iteration failed")
                stop_worker.wait(2)
                continue
            if not outcome.claimed and not drive_claimed:
                stop_worker.wait(1)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if embedded_worker is not None:
            try:
                concurrency = int(os.environ.get("WEARO_WORKER_CONCURRENCY", "4"))
            except ValueError as error:
                raise RuntimeError(
                    "WEARO_WORKER_CONCURRENCY must be an integer from 1 to 32"
                ) from error
            if not 1 <= concurrency <= 32:
                raise RuntimeError("WEARO_WORKER_CONCURRENCY must be between 1 and 32")
            for slot in range(1, concurrency + 1):
                thread = threading.Thread(
                    target=run_embedded_worker,
                    name=f"wearo-local-render-worker-{slot}",
                    daemon=True,
                )
                worker_threads.append(thread)
                thread.start()
        try:
            yield
        finally:
            stop_worker.set()
            for thread in worker_threads:
                thread.join(timeout=1)

    app = FastAPI(title="Wearo beta API", version="1.0.0-beta", lifespan=lifespan)

    @app.middleware("http")
    async def request_context(request: Request, call_next: Any) -> Response:
        request.state.request_id = request.headers.get("X-Request-Id", uuid4().hex)[:100]
        response: Response = await call_next(request)
        response.headers["X-Request-Id"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ApiProblem)
    async def api_problem(request: Request, error: ApiProblem) -> JSONResponse:
        return _problem(error.status, error.code, str(error), _request_id(request))

    @app.exception_handler(DriveIntegrationError)
    async def drive_problem(request: Request, error: DriveIntegrationError) -> JSONResponse:
        status = 503 if error.retryable else 400
        return _problem(status, error.code, str(error), _request_id(request))

    @app.exception_handler(ProfileError)
    @app.exception_handler(CatalogError)
    @app.exception_handler(BusinessPlatformError)
    @app.exception_handler(PlatformIdentityError)
    @app.exception_handler(BusinessOnboardingError)
    @app.exception_handler(BusinessBillingError)
    @app.exception_handler(BusinessMembershipError)
    @app.exception_handler(WalletTransactionError)
    @app.exception_handler(TopUpError)
    @app.exception_handler(SensitiveAuditError)
    @app.exception_handler(BusinessAgentError)
    @app.exception_handler(BusinessStoreError)
    @app.exception_handler(StoreAdvertisementError)
    @app.exception_handler(SmartAdError)
    @app.exception_handler(BusinessShopError)
    @app.exception_handler(BusinessTryOnStatusError)
    @app.exception_handler(BusinessAllowanceError)
    @app.exception_handler(CommunicationsError)
    @app.exception_handler(BusinessReportError)
    @app.exception_handler(SupportCaseError)
    @app.exception_handler(SupportAccessError)
    @app.exception_handler(SponsoredTryOnError)
    @app.exception_handler(AccountLifecycleError)
    @app.exception_handler(ContactEnquiryError)
    @app.exception_handler(ConsentError)
    @app.exception_handler(MediaRuntimeError)
    @app.exception_handler(RenderPreflightError)
    @app.exception_handler(DurableRenderError)
    @app.exception_handler(TryOnAuthorizationError)
    async def domain_problem(request: Request, error: ValueError) -> JSONResponse:
        code = getattr(error, "code", "VALIDATION_FAILED")
        if code in {
            "JOB_UNAVAILABLE",
            "CATALOG_ITEM_NOT_FOUND",
            "CATALOG_RESOURCE_UNAVAILABLE",
            "COLLECTION_NOT_FOUND",
            "CATEGORY_NOT_FOUND",
            "BUSINESS_RESOURCE_UNAVAILABLE",
            "PLATFORM_CONTEXT_UNAVAILABLE",
            "OFFERING_UNAVAILABLE",
            "BILLING_PROFILE_UNAVAILABLE",
            "MEMBERSHIP_UNAVAILABLE",
            "TRANSACTION_HISTORY_UNAVAILABLE",
            "TOPUP_UNAVAILABLE",
            "TOKEN_PACK_UNAVAILABLE",
            "PAYMENT_ORDER_UNAVAILABLE",
            "RECEIPT_UNAVAILABLE",
            "INVOICE_UNAVAILABLE",
            "RECONCILIATION_UNAVAILABLE",
            "AUDIT_UNAVAILABLE",
            "AGENT_UNAVAILABLE",
            "SHOP_LINK_UNAVAILABLE",
            "ALLOWANCE_UNAVAILABLE",
            "COMMUNICATIONS_UNAVAILABLE",
            "NOTICE_UNAVAILABLE",
            "REPORT_UNAVAILABLE",
            "CASE_UNAVAILABLE",
            "SUPPORT_GRANT_UNAVAILABLE",
            "TRY_ON_STATUS_UNAVAILABLE",
            "SMART_AD_UNAVAILABLE",
            "SMART_AD_IMAGE_UNAVAILABLE",
        }:
            status = 404
        elif code in {
            "JOB_STATE_CONFLICT",
            "QUOTA_STATE_CONFLICT",
            "QUEUE_CANCELLATION_TOO_EARLY",
            "CATALOG_CONFLICT",
            "REGISTRATION_CONFLICT",
            "LAST_OWNER_REQUIRED",
            "ACCOUNT_CANCELLATION_UNAVAILABLE",
            "TRY_ON_STATUS_CONFLICT",
            "SMART_AD_ALREADY_ACTIVE",
            "SMART_AD_DAILY_LIMIT_REACHED",
            "SMART_AD_GENERATION_IN_PROGRESS",
            "SMART_AD_SCHEDULE_LOCKED",
        }:
            status = 409
        elif code == "INVALID_PAYMENT_SIGNATURE":
            status = 400
        elif code == "PAYMENT_GATEWAY_AUTH_FAILED":
            status = 401
        elif code == "PAYMENT_GATEWAY_UNAVAILABLE":
            status = 500
        else:
            status = 422
        return _problem(status, code, str(error), _request_id(request))

    @app.post("/api/v1/public/contact-enquiries", status_code=201)
    def create_contact_enquiry(
        body: ContactEnquiryBody,
        request: Request,
        x_wearo_contact_token: Annotated[str | None, Header(alias="X-Wearo-Contact-Token")] = None,
    ) -> dict[str, object]:
        configured_origin = os.environ.get("WEARO_CONSUMER_ORIGIN", "").rstrip("/")
        request_origin = request.headers.get("origin", "").rstrip("/")
        if configured_origin and request_origin != configured_origin:
            raise ApiProblem(403, "CONTACT_ORIGIN_REJECTED", "Contact request rejected.")
        supplied_token = (x_wearo_contact_token or "").encode()
        if not container.contact_form_token or not hmac.compare_digest(
            supplied_token, container.contact_form_token
        ):
            raise ApiProblem(401, "INVALID_CONTACT_TOKEN", "Contact request rejected.")
        if container.contact_enquiries is None:
            raise ApiProblem(503, "CONTACT_ENQUIRIES_UNAVAILABLE", "Contact is unavailable.")
        return container.contact_enquiries.create(
            name=body.name,
            email=body.email,
            mobile=body.mobile,
            website_url=body.website_url,
            purpose=body.purpose,
            request_id=_request_id(request),
        )

    @app.get("/api/v1/public/smart-ads/{public_token}/image")
    def public_smart_ad_image(public_token: UUID) -> Response:
        if container.business_smart_ads is None:
            raise ApiProblem(404, "SMART_AD_IMAGE_UNAVAILABLE", "SmartAds image unavailable.")
        content, content_type = container.business_smart_ads.public_image(public_token)
        return Response(content, media_type=content_type)

    @app.get("/api/v1/public/smart-ads/{public_token}/try-on-item")
    def public_smart_ad_try_on_item(public_token: UUID) -> Response:
        if container.business_smart_ads is None:
            raise ApiProblem(404, "SMART_AD_IMAGE_UNAVAILABLE", "SmartAds item unavailable.")
        content, content_type = container.business_smart_ads.public_try_on_item(public_token)
        return Response(
            content,
            media_type=content_type,
            headers={"Cache-Control": "private, no-store"},
        )

    @app.exception_handler(AnalysisServiceError)
    async def analysis_problem(request: Request, error: AnalysisServiceError) -> JSONResponse:
        return _problem(
            503,
            "VISION_PROVIDER_UNAVAILABLE",
            "Image understanding is temporarily unavailable.",
            _request_id(request),
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        with container.engine.connect() as connection:
            connection.execute(text("SELECT 1")).scalar_one()
        return {"status": "ok"}

    @app.get("/health/ready")
    def readiness() -> dict[str, str]:
        with container.engine.connect() as connection:
            connection.execute(text("SELECT 1")).scalar_one()
        if container.preflight is None:
            raise ApiProblem(
                503,
                "VISION_PROVIDER_UNAVAILABLE",
                "Image understanding is not configured for this environment.",
            )
        return {"status": "ready", "image_understanding": "configured"}

    @app.post("/api/v1/admin/login")
    def admin_login(body: AdminLoginBody, request: Request, response: Response) -> dict[str, str]:
        if platform_admin_auth is None:
            raise ApiProblem(503, "ADMIN_AUTH_UNAVAILABLE", "Admin sign-in is unavailable.")
        client_key = request.client.host if request.client is not None else "unknown"
        session = platform_admin_auth.login(body.email, body.password, client_key)
        if session is None:
            raise ApiProblem(401, "INVALID_ADMIN_CREDENTIALS", "Invalid email or password.")
        max_age = max(0, int((session.expires_at - datetime.now(UTC)).total_seconds()))
        response.set_cookie(
            ADMIN_SESSION_COOKIE,
            session.token,
            max_age=max_age,
            httponly=True,
            secure=container.secure_cookie,
            samesite="strict",
            path="/",
        )
        return {"redirect_to": "/admin/dashboard"}

    @app.get("/api/v1/admin/session")
    def admin_session(request: Request) -> dict[str, bool]:
        token = request.cookies.get(ADMIN_SESSION_COOKIE, "")
        if platform_admin_auth is None or not platform_admin_auth.authenticate(token):
            raise ApiProblem(401, "ADMIN_AUTHENTICATION_REQUIRED", "Admin sign-in required.")
        return {"authenticated": True}

    def require_platform_admin(request: Request) -> None:
        token = request.cookies.get(ADMIN_SESSION_COOKIE, "")
        if platform_admin_auth is None or not platform_admin_auth.authenticate(token):
            raise ApiProblem(401, "ADMIN_AUTHENTICATION_REQUIRED", "Admin sign-in required.")

    def require_notification_webhook(secret: str | None) -> None:
        configured = os.environ.get("WEARO_NOTIFICATION_WEBHOOK_SECRET", "")
        if not configured or not secret or not hmac.compare_digest(secret, configured):
            raise ApiProblem(401, "INVALID_WEBHOOK_SECRET", "Webhook authentication failed.")

    @app.get("/api/v1/admin/notifications/templates")
    def admin_notification_templates(
        request: Request,
        channel: Literal["EMAIL", "SMS", "WHATSAPP"] | None = None,
    ) -> dict[str, object]:
        require_platform_admin(request)
        return {"templates": notifications.list_templates(channel)}

    @app.post("/api/v1/admin/notifications/templates", status_code=201)
    def admin_save_notification_template(
        body: AdminCommunicationTemplateBody, request: Request
    ) -> dict[str, object]:
        require_platform_admin(request)
        try:
            return notifications.save_template(
                channel=body.channel,
                template_key=body.template_key,
                category=body.category,
                display_name=body.display_name,
                subject=body.subject,
                body=body.body,
                signature=body.signature,
                prompt=body.generation_prompt,
                status=body.status,
            )
        except NotificationError as error:
            raise ApiProblem(422, error.code, str(error)) from None

    @app.post("/api/v1/admin/notifications/templates/generate")
    def admin_generate_notification_template(
        body: AdminTemplateGenerationBody, request: Request
    ) -> dict[str, object]:
        require_platform_admin(request)
        try:
            if body.channel == "SMS":
                raise NotificationError(
                    "SMS_AI_DISABLED", "Enter and save the SMS OTP message manually."
                )
            if body.template_key not in TEMPLATE_DEFINITIONS:
                raise NotificationError(
                    "INVALID_TEMPLATE_KEY", "Select a supported template purpose."
                )
            generated = template_generator.generate(
                channel=body.channel,
                template_key=body.template_key,
                prompt=body.prompt,
                reference_image=body.reference_image,
            )
            category, display_name = TEMPLATE_DEFINITIONS[body.template_key]
            return notifications.save_template(
                channel=body.channel,
                template_key=body.template_key,
                category=category,
                display_name=display_name,
                subject=generated["subject"] if body.channel == "EMAIL" else None,
                body=generated["body"],
                signature=generated["signature"],
                prompt=body.prompt,
                status="DRAFT",
            )
        except NotificationError as error:
            status = 422 if error.code == "INVALID_REFERENCE_IMAGE" else 503
            raise ApiProblem(status, error.code, str(error)) from None

    @app.post("/api/v1/admin/notifications/templates/generate-all", status_code=201)
    def admin_generate_all_notification_templates(
        body: AdminTemplateGenerationBody, request: Request
    ) -> dict[str, object]:
        require_platform_admin(request)
        try:
            if body.channel == "SMS":
                raise NotificationError(
                    "SMS_AI_DISABLED", "Enter and save the SMS OTP message manually."
                )
            generated = template_generator.generate_all(
                channel=body.channel,
                prompt=body.prompt,
                reference_image=body.reference_image,
            )
            templates = tuple(
                notifications.save_template(
                    channel=body.channel,
                    template_key=item["template_key"],
                    category=TEMPLATE_DEFINITIONS[item["template_key"]][0],
                    display_name=TEMPLATE_DEFINITIONS[item["template_key"]][1],
                    subject=item["subject"] if body.channel == "EMAIL" else None,
                    body=item["body"],
                    signature=item["signature"],
                    prompt=body.prompt,
                    status="DRAFT",
                )
                for item in generated
            )
            return {"templates": templates, "count": len(templates)}
        except NotificationError as error:
            status = 422 if error.code == "INVALID_REFERENCE_IMAGE" else 503
            raise ApiProblem(status, error.code, str(error)) from None

    @app.post("/api/v1/admin/notifications/templates/{template_id}/activate")
    def admin_activate_notification_template(
        template_id: UUID, request: Request
    ) -> dict[str, object]:
        require_platform_admin(request)
        try:
            return notifications.activate_template(template_id)
        except NotificationError as error:
            status = 404 if error.code == "TEMPLATE_NOT_FOUND" else 409
            raise ApiProblem(status, error.code, str(error)) from None

    @app.delete("/api/v1/admin/notifications/templates/{template_id}", status_code=204)
    def admin_delete_notification_template(template_id: UUID, request: Request) -> Response:
        require_platform_admin(request)
        try:
            notifications.delete_template(template_id)
        except NotificationError as error:
            status = 409 if error.code == "TEMPLATE_IN_USE" else 404
            raise ApiProblem(status, error.code, str(error)) from None
        return Response(status_code=204)

    @app.delete("/api/v1/admin/notifications/templates", status_code=200)
    def admin_delete_all_notification_templates(
        request: Request,
        channel: Literal["EMAIL", "SMS", "WHATSAPP"],
    ) -> dict[str, object]:
        require_platform_admin(request)
        try:
            deleted = notifications.delete_all_templates(channel)
        except NotificationError as error:
            raise ApiProblem(409, error.code, str(error)) from None
        return {"channel": channel, "deleted": deleted}

    @app.post("/api/v1/admin/notifications/templates/{template_id}/send-test", status_code=202)
    def admin_send_test_notification_template(
        template_id: UUID, request: Request
    ) -> dict[str, object]:
        require_platform_admin(request)
        recipient_email = os.environ.get("WEARO_ADMIN_EMAIL", "").strip()
        recipient_name = os.environ.get("WEARO_ADMIN_NAME", "").strip() or "Wearo Super Admin"
        if not recipient_email:
            raise ApiProblem(
                503, "ADMIN_EMAIL_UNAVAILABLE", "Configure WEARO_ADMIN_EMAIL to send test emails."
            )
        try:
            template = notifications.template_version(template_id)
            if template["channel"] != "EMAIL":
                raise NotificationError(
                    "INVALID_TEST_CHANNEL", "Test delivery is currently available for email only."
                )
            sample_values: dict[str, object] = {
                "first_name": recipient_name.split()[0],
                "name": recipient_name,
                "full_name": recipient_name,
                "customer_name": recipient_name,
                "account_email": recipient_email,
                "email": recipient_email,
                "original_subject": "Your support request",
                "support_reference": "TEST-1001",
                "billing_month": datetime.now(UTC).strftime("%B %Y"),
                "amount_due": "INR 1,999.00",
                "due_date": (datetime.now(UTC) + timedelta(days=7)).date().isoformat(),
            }
            origin = _public_origin(request)
            sample_values.update(
                {
                    "customer_login_url": f"{origin}/business/sign-in",
                    "dashboard_url": f"{origin}/business/sign-in",
                    "help_center_url": f"{origin}/business/support",
                    "support_email": os.environ.get("SES_SUPPORT_EMAIL", "support@wearo.ai"),
                    "lady_image_url": f"{origin}/wearo-hero-campaign.webp",
                    "wearo_logo_url": f"{origin}/wearo-brand_white_bg.png?v=20261114-email-2",
                }
            )
            for variable in template_variable_names(
                str(template.get("subject") or ""),
                str(template["body"]),
                str(template.get("signature") or ""),
            ):
                sample_values.setdefault(variable, "Sample value")
            job_id = notifications.enqueue(
                channel="EMAIL",
                template_key=str(template["template_key"]),
                recipient=f"{recipient_name} <{recipient_email}>",
                variables=sample_values,
                metadata={"template_id": str(template_id), "test_email": True},
            )
            return {"job_id": job_id, "status": "QUEUED", "recipient": recipient_email}
        except NotificationError as error:
            status = 404 if error.code == "TEMPLATE_NOT_FOUND" else 422
            raise ApiProblem(status, error.code, str(error)) from None

    @app.post("/api/v1/webhooks/notifications/enqueue", status_code=202)
    def enqueue_notification(
        body: NotificationEnqueueBody,
        x_wearo_webhook_secret: Annotated[
            str | None, Header(alias="X-Wearo-Webhook-Secret")
        ] = None,
    ) -> dict[str, object]:
        require_notification_webhook(x_wearo_webhook_secret)
        try:
            job_id = notifications.enqueue(
                channel=body.channel,
                template_key=body.template_key,
                recipient=body.recipient,
                variables=body.variables,
                metadata=body.metadata,
                deduplication_key=body.deduplication_key,
                scheduled_at=body.scheduled_at,
            )
            return {"job_id": job_id, "status": "QUEUED"}
        except NotificationError as error:
            raise ApiProblem(422, error.code, str(error)) from None

    @app.post("/api/v1/webhooks/ses/support", status_code=202)
    def inbound_support_email(
        body: InboundSupportBody,
        x_wearo_webhook_secret: Annotated[
            str | None, Header(alias="X-Wearo-Webhook-Secret")
        ] = None,
    ) -> dict[str, object]:
        require_notification_webhook(x_wearo_webhook_secret)
        support_address = os.environ.get("SES_SUPPORT_EMAIL", "").casefold()
        if support_address and body.recipient_email.casefold() != support_address:
            raise ApiProblem(422, "INVALID_SUPPORT_RECIPIENT", "Support recipient is invalid.")
        try:
            return notifications.ingest_support(
                provider_message_id=body.provider_message_id,
                sender=body.sender_email,
                recipient=body.recipient_email,
                subject=body.subject,
                body_text=body.body_text,
                received_at=body.received_at,
            )
        except NotificationError as error:
            raise ApiProblem(422, error.code, str(error)) from None

    @app.post("/api/v1/webhooks/notifications/schedule-billing", status_code=202)
    def schedule_billing_notifications(
        x_wearo_webhook_secret: Annotated[
            str | None, Header(alias="X-Wearo-Webhook-Secret")
        ] = None,
    ) -> dict[str, int]:
        require_notification_webhook(x_wearo_webhook_secret)
        return {"queued": notifications.schedule_billing(datetime.now(UTC).date())}

    @app.get("/api/v1/admin/organizations")
    def admin_organization_list(
        request: Request,
        search: str = "",
        business_type: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        require_platform_admin(request)
        try:
            return admin_organizations.list(
                search=search, business_type=business_type, status=status
            )
        except AdminOrganizationError as error:
            raise ApiProblem(422, "INVALID_ORGANIZATION_FILTER", str(error)) from None

    @app.get("/api/v1/admin/support/customers")
    def admin_support_customer_search(request: Request, identity: str) -> dict[str, object]:
        require_platform_admin(request)
        try:
            return admin_support.search(identity)
        except AdminSupportError as error:
            raise ApiProblem(422, error.code, str(error)) from None

    @app.post("/api/v1/admin/support/customers/{account_id}/token-credits")
    def admin_support_token_credit(
        account_id: UUID, body: AdminSupportTokenCreditBody, request: Request
    ) -> dict[str, object]:
        require_platform_admin(request)
        try:
            return admin_support.add_tokens(account_id, body.amount, body.reason)
        except AdminSupportError as error:
            status = 404 if error.code == "SUPPORT_ACCOUNT_NOT_FOUND" else 422
            raise ApiProblem(status, error.code, str(error)) from None

    @app.get("/api/v1/admin/dashboard")
    def admin_dashboard_metrics(
        request: Request,
        date_from: date,
        date_to: date,
        tenant_id: UUID | None = None,
        business_type: str | None = None,
    ) -> dict[str, int | float]:
        require_platform_admin(request)
        try:
            return platform_dashboard.metrics(
                date_from=date_from,
                date_to=date_to,
                tenant_id=tenant_id,
                business_type=business_type,
            )
        except AdminDashboardError as error:
            raise ApiProblem(422, "INVALID_DASHBOARD_FILTER", str(error)) from None

    @app.get("/api/v1/admin/usage/organizations")
    def admin_usage_by_organization(
        request: Request,
        date_from: date,
        date_to: date,
        tenant_id: UUID | None = None,
        business_type: str | None = None,
    ) -> dict[str, object]:
        require_platform_admin(request)
        try:
            return admin_usage_analytics.organizations(
                date_from=date_from,
                date_to=date_to,
                tenant_id=tenant_id,
                business_type=business_type,
            )
        except AdminUsageAnalyticsError as error:
            raise ApiProblem(422, "INVALID_USAGE_FILTER", str(error)) from None

    @app.get("/api/v1/admin/usage/organizations/{tenant_id}")
    def admin_organization_usage_history(
        request: Request, tenant_id: UUID, date_from: date, date_to: date
    ) -> dict[str, object]:
        require_platform_admin(request)
        try:
            return admin_usage_analytics.history(tenant_id, date_from=date_from, date_to=date_to)
        except AdminUsageAnalyticsError as error:
            raise ApiProblem(404, "ORGANIZATION_USAGE_NOT_FOUND", str(error)) from None

    @app.get("/api/v1/admin/realtime")
    def admin_realtime_snapshot(request: Request, window_minutes: int = 60) -> dict[str, object]:
        require_platform_admin(request)
        try:
            return admin_realtime.snapshot(window_minutes=window_minutes)
        except AdminRealtimeError as error:
            raise ApiProblem(422, "INVALID_REALTIME_WINDOW", str(error)) from None

    @app.get("/api/v1/admin/ai-costs")
    def admin_ai_cost_dashboard(request: Request) -> dict[str, object]:
        require_platform_admin(request)
        return admin_ai_costs.dashboard()

    @app.post("/api/v1/admin/ai-costs/providers", status_code=201)
    def admin_add_ai_provider(request: Request, body: AdminAiProviderBody) -> dict[str, object]:
        require_platform_admin(request)
        try:
            return admin_ai_costs.add_provider(body.model_dump())
        except AdminAiCostError as error:
            raise ApiProblem(422, "INVALID_AI_PROVIDER", str(error)) from None

    @app.put("/api/v1/admin/ai-costs/providers/{provider_id}")
    def admin_update_ai_provider(
        request: Request, provider_id: UUID, body: AdminAiProviderBody
    ) -> dict[str, object]:
        require_platform_admin(request)
        try:
            return admin_ai_costs.update_provider(provider_id, body.model_dump())
        except AdminAiCostError as error:
            raise ApiProblem(422, "INVALID_AI_PROVIDER", str(error)) from None

    @app.post("/api/v1/admin/ai-costs/models", status_code=201)
    def admin_add_ai_model(request: Request, body: AdminAiModelBody) -> dict[str, object]:
        require_platform_admin(request)
        try:
            return admin_ai_costs.add_model(body.model_dump())
        except AdminAiCostError as error:
            raise ApiProblem(422, "INVALID_AI_MODEL", str(error)) from None

    @app.put("/api/v1/admin/ai-costs/models/{model_id}")
    def admin_update_ai_model(
        request: Request, model_id: UUID, body: AdminAiModelBody
    ) -> dict[str, object]:
        require_platform_admin(request)
        try:
            return admin_ai_costs.update_model(model_id, body.model_dump())
        except AdminAiCostError as error:
            raise ApiProblem(422, "INVALID_AI_MODEL", str(error)) from None

    @app.put("/api/v1/admin/ai-costs/models/{model_id}/select")
    def admin_select_tryon_model(request: Request, model_id: UUID) -> dict[str, object]:
        require_platform_admin(request)
        try:
            return admin_ai_costs.select_tryon_model(model_id)
        except AdminAiCostError as error:
            raise ApiProblem(422, "INVALID_TRYON_MODEL", str(error)) from None

    @app.post("/api/v1/admin/ai-costs/purchases", status_code=201)
    def admin_add_provider_purchase(
        request: Request, body: AdminProviderPurchaseBody
    ) -> dict[str, object]:
        require_platform_admin(request)
        try:
            return admin_ai_costs.add_purchase(body.model_dump())
        except AdminAiCostError as error:
            raise ApiProblem(422, "INVALID_PROVIDER_PURCHASE", str(error)) from None

    @app.put("/api/v1/admin/ai-costs/{entity}/{entity_id}/status")
    def admin_set_ai_status(
        request: Request,
        entity: Literal["providers", "models"],
        entity_id: UUID,
        body: AdminAiStatusBody,
    ) -> dict[str, object]:
        require_platform_admin(request)
        try:
            return admin_ai_costs.set_status(entity, entity_id, body.status)
        except AdminAiCostError as error:
            raise ApiProblem(422, "INVALID_AI_LIFECYCLE", str(error)) from None

    @app.delete("/api/v1/admin/ai-costs/models/{model_id}", status_code=204)
    def admin_delete_unused_model(request: Request, model_id: UUID) -> Response:
        require_platform_admin(request)
        try:
            admin_ai_costs.delete_model(model_id)
        except AdminAiCostError as error:
            raise ApiProblem(409, "AI_MODEL_HAS_HISTORY", str(error)) from None
        return Response(status_code=204)

    @app.delete("/api/v1/admin/ai-costs/providers/{provider_id}", status_code=204)
    def admin_delete_unused_provider(request: Request, provider_id: UUID) -> Response:
        require_platform_admin(request)
        try:
            admin_ai_costs.delete_provider(provider_id)
        except AdminAiCostError as error:
            raise ApiProblem(409, "AI_PROVIDER_HAS_HISTORY", str(error)) from None
        return Response(status_code=204)

    @app.get("/api/v1/admin/customers")
    def admin_customer_list(request: Request, status: str | None = None) -> dict[str, object]:
        require_platform_admin(request)
        try:
            return admin_customers.list(status=status)
        except AdminCustomerError as error:
            raise ApiProblem(422, "INVALID_CUSTOMER_FILTER", str(error)) from None

    @app.get("/api/v1/admin/enquiries")
    def admin_enquiry_list(
        request: Request,
        search: str = "",
        purpose: str | None = None,
        status: str | None = None,
    ) -> dict[str, object]:
        require_platform_admin(request)
        try:
            return admin_enquiries.list(search=search, purpose=purpose, status=status)
        except AdminEnquiryError as error:
            raise ApiProblem(422, "INVALID_ENQUIRY_FILTER", str(error)) from None

    @app.get("/api/v1/admin/subscriptions/{tenant_id}")
    def admin_subscription_detail(request: Request, tenant_id: UUID) -> dict[str, object]:
        require_platform_admin(request)
        try:
            return admin_subscriptions.get(tenant_id)
        except AdminSubscriptionError as error:
            raise ApiProblem(404, "SUBSCRIPTION_NOT_FOUND", str(error)) from None

    @app.post("/api/v1/admin/subscriptions/{tenant_id}/transitions")
    def admin_subscription_transition(
        request: Request, tenant_id: UUID, body: AdminSubscriptionTransitionBody
    ) -> dict[str, object]:
        require_platform_admin(request)
        try:
            return admin_subscriptions.transition(tenant_id, body.action, body.reason)
        except AdminSubscriptionError as error:
            raise ApiProblem(409, "SUBSCRIPTION_TRANSITION_CONFLICT", str(error)) from None

    @app.post("/api/v1/admin/subscriptions/{tenant_id}/plan")
    def admin_subscription_plan(
        request: Request, tenant_id: UUID, body: AdminPlanAssignmentBody
    ) -> dict[str, object]:
        require_platform_admin(request)
        try:
            return admin_subscriptions.assign_plan(
                tenant_id, body.plan_code, body.next_billing_at, body.reason
            )
        except AdminSubscriptionError as error:
            raise ApiProblem(422, "PLAN_ASSIGNMENT_REJECTED", str(error)) from None

    @app.post("/api/v1/admin/subscriptions/{tenant_id}/trial-extension")
    def admin_subscription_trial_extension(
        request: Request, tenant_id: UUID, body: AdminTrialExtensionBody
    ) -> dict[str, object]:
        require_platform_admin(request)
        try:
            return admin_subscriptions.extend_trial(tenant_id, body.days, body.reason)
        except AdminSubscriptionError as error:
            raise ApiProblem(422, "TRIAL_EXTENSION_REJECTED", str(error)) from None

    @app.get("/api/v1/admin/pricing")
    def admin_pricing_detail(request: Request) -> dict[str, object]:
        require_platform_admin(request)
        return admin_pricing.current()

    @app.post("/api/v1/admin/pricing/settings", status_code=201)
    def admin_publish_pricing(
        request: Request, body: AdminPricingSettingsBody
    ) -> dict[str, object]:
        require_platform_admin(request)
        values = body.model_dump(exclude={"reason"})
        try:
            return admin_pricing.publish_settings(values, body.reason)
        except AdminPricingError as error:
            raise ApiProblem(422, "PRICING_REJECTED", str(error)) from None

    @app.post("/api/v1/admin/pricing/token-packages", status_code=201)
    def admin_publish_token_package(
        request: Request, body: AdminTokenPackageBody
    ) -> dict[str, object]:
        require_platform_admin(request)
        values = body.model_dump(exclude={"reason"})
        try:
            return admin_pricing.publish_package(values, body.reason)
        except AdminPricingError as error:
            raise ApiProblem(422, "TOKEN_PACKAGE_REJECTED", str(error)) from None

    @app.get("/api/v1/admin/pricing/retail-tryon")
    def admin_retail_tryon_price(request: Request) -> dict[str, object]:
        require_platform_admin(request)
        return retail_tryon_pricing.history()

    @app.post("/api/v1/admin/pricing/retail-tryon", status_code=201)
    def admin_publish_retail_tryon_price(
        request: Request, body: AdminRetailTryOnPriceBody
    ) -> dict[str, object]:
        require_platform_admin(request)
        try:
            return retail_tryon_pricing.publish(body.price_minor, body.reason)
        except RetailTryOnPricingError as error:
            raise ApiProblem(422, "RETAIL_TRYON_PRICE_REJECTED", str(error)) from None

    @app.post("/api/v1/admin/pricing/retail-tryon/packages", status_code=201)
    def admin_create_retail_tryon_package(
        request: Request, body: AdminRetailTryOnPackageBody
    ) -> dict[str, object]:
        require_platform_admin(request)
        try:
            return retail_tryon_pricing.create_package(
                body.name, body.minimum_amount_minor, body.gst_basis_points, body.reason
            )
        except RetailTryOnPricingError as error:
            raise ApiProblem(422, "RETAIL_TRYON_PACKAGE_REJECTED", str(error)) from None

    @app.put("/api/v1/admin/pricing/retail-tryon/packages/{package_id}")
    def admin_update_retail_tryon_package(
        request: Request, package_id: UUID, body: AdminRetailTryOnPackageBody
    ) -> dict[str, object]:
        require_platform_admin(request)
        try:
            return retail_tryon_pricing.update_package(
                package_id, body.name, body.minimum_amount_minor,
                body.gst_basis_points, body.reason
            )
        except RetailTryOnPricingError as error:
            raise ApiProblem(422, "RETAIL_TRYON_PACKAGE_REJECTED", str(error)) from None

    @app.delete("/api/v1/admin/pricing/retail-tryon/packages/{package_id}")
    def admin_delete_retail_tryon_package(
        request: Request, package_id: UUID, body: AdminRetailTryOnPackageDeleteBody
    ) -> dict[str, object]:
        require_platform_admin(request)
        try:
            return retail_tryon_pricing.delete_package(package_id, body.reason)
        except RetailTryOnPricingError as error:
            raise ApiProblem(422, "RETAIL_TRYON_PACKAGE_REJECTED", str(error)) from None

    @app.get("/api/v1/admin/billing")
    def admin_billing_list(request: Request, status: str | None = None) -> dict[str, object]:
        require_platform_admin(request)
        try:
            return admin_billing.list(status)
        except AdminBillingError as error:
            raise ApiProblem(422, "INVALID_PAYMENT_FILTER", str(error)) from None

    @app.get("/api/v1/admin/revenue")
    def admin_revenue_metrics(
        request: Request, date_from: date, date_to: date, tenant_id: UUID | None = None
    ) -> dict[str, object]:
        require_platform_admin(request)
        try:
            return admin_revenue.metrics(date_from=date_from, date_to=date_to, tenant_id=tenant_id)
        except AdminRevenueError as error:
            raise ApiProblem(422, "INVALID_REVENUE_FILTER", str(error)) from None

    @app.get("/api/v1/admin/operations/try-ons")
    def admin_tryon_operations(
        request: Request,
        date_from: date,
        date_to: date,
        tenant_id: UUID | None = None,
        business_type: str | None = None,
    ) -> dict[str, object]:
        require_platform_admin(request)
        try:
            return admin_operations.list(
                date_from=date_from,
                date_to=date_to,
                tenant_id=tenant_id,
                business_type=business_type,
            )
        except AdminOperationsError as error:
            raise ApiProblem(422, "INVALID_OPERATIONS_FILTER", str(error)) from None

    @app.get("/api/v1/admin/service-health")
    def admin_service_health(request: Request) -> dict[str, object]:
        require_platform_admin(request)
        return current_service_health()

    @app.get("/api/v1/admin/operations/controls")
    def admin_platform_control_status(request: Request) -> dict[str, object]:
        require_platform_admin(request)
        return admin_platform_controls.status()

    @app.get("/api/v1/admin/audit-history")
    def admin_audit_history(
        request: Request,
        search: str = "",
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict[str, object]:
        require_platform_admin(request)
        try:
            return admin_audit.list(search=search, date_from=date_from, date_to=date_to)
        except AdminAuditError as error:
            raise ApiProblem(422, "INVALID_AUDIT_FILTER", str(error)) from None

    @app.post("/api/v1/admin/operations/controls")
    def admin_platform_control_change(
        request: Request, body: AdminPlatformControlBody
    ) -> dict[str, object]:
        require_platform_admin(request)
        try:
            return admin_platform_controls.change(**body.model_dump())
        except AdminPlatformControlError as error:
            raise ApiProblem(409, "TRY_ON_CONTROL_REJECTED", str(error)) from None

    @app.get("/api/v1/admin/operations/try-ons/{job_id}")
    def admin_tryon_operation_detail(request: Request, job_id: UUID) -> dict[str, object]:
        require_platform_admin(request)
        try:
            return admin_operations.detail(job_id)
        except AdminOperationsError as error:
            raise ApiProblem(404, "TRY_ON_REQUEST_NOT_FOUND", str(error)) from None

    @app.get("/api/v1/admin/billing/invoices/{invoice_id}/detail")
    def admin_invoice_detail(request: Request, invoice_id: UUID) -> dict[str, object]:
        require_platform_admin(request)
        try:
            return admin_billing.invoice(invoice_id)
        except AdminBillingError as error:
            raise ApiProblem(404, "INVOICE_NOT_FOUND", str(error)) from None

    @app.get("/api/v1/admin/billing/invoices/{invoice_id}.txt")
    def admin_invoice_download(request: Request, invoice_id: UUID) -> PlainTextResponse:
        require_platform_admin(request)
        try:
            invoice = admin_billing.invoice(invoice_id)
        except AdminBillingError as error:
            raise ApiProblem(404, "INVOICE_NOT_FOUND", str(error)) from None
        business = invoice["business_snapshot"]
        tax = invoice["tax_snapshot"]
        if not isinstance(business, dict) or not isinstance(tax, dict):
            raise ApiProblem(500, "INVALID_INVOICE", "Invoice snapshot is invalid.")
        subtotal = invoice["subtotal_minor"]
        tax_minor = invoice["tax_minor"]
        total = invoice["amount_minor"]
        rate = tax.get("rate_basis_points", 0)
        if (
            not isinstance(subtotal, int)
            or not isinstance(tax_minor, int)
            or not isinstance(total, int)
            or not isinstance(rate, int)
        ):
            raise ApiProblem(500, "INVALID_INVOICE", "Invoice amounts are invalid.")
        body = (
            "WEARO TAX INVOICE\n"
            f"Invoice number: {invoice['invoice_number']}\n"
            f"Issued: {invoice['issued_at']}\n"
            f"Bill to: {business.get('legal_name', '')}\n"
            f"Billing email: {business.get('billing_email', '')}\n"
            f"GSTIN: {business.get('tax_identifier') or 'Not provided'}\n"
            f"Billing address: {json.dumps(business.get('billing_address', {}), sort_keys=True)}\n"
            f"Subtotal: {invoice['currency']} {subtotal / 100:.2f}\n"
            f"Tax ({rate / 100:.2f}%): {invoice['currency']} {tax_minor / 100:.2f}\n"
            f"Total payable: {invoice['currency']} {total / 100:.2f}\n"
            f"Payment date: {invoice.get('payment_date') or 'Pending'}\n"
        )
        return PlainTextResponse(
            body,
            headers={
                "Content-Disposition": f'attachment; filename="{invoice["invoice_number"]}.txt"'
            },
        )

    @app.get("/api/v1/admin/organizations/{tenant_id}")
    def admin_organization_detail(request: Request, tenant_id: UUID) -> dict[str, object]:
        require_platform_admin(request)
        try:
            return admin_organizations.get(tenant_id)
        except AdminOrganizationError:
            raise ApiProblem(404, "ORGANIZATION_NOT_FOUND", "Organization not found.") from None

    @app.post("/api/v1/admin/organizations/{tenant_id}/status")
    def admin_organization_status(
        request: Request, tenant_id: UUID, body: AdminOrganizationStatusBody
    ) -> dict[str, str]:
        require_platform_admin(request)
        try:
            return admin_organizations.change_status(tenant_id, body.action, body.reason)
        except AdminOrganizationError as error:
            raise ApiProblem(409, "ORGANIZATION_STATUS_CONFLICT", str(error)) from None

    @app.post("/api/v1/admin/organizations/{tenant_id}/token-adjustments")
    def admin_organization_token_adjustment(
        request: Request, tenant_id: UUID, body: AdminTokenAdjustmentBody
    ) -> dict[str, int]:
        require_platform_admin(request)
        try:
            return admin_organizations.adjust_tokens(tenant_id, body.amount, body.reason)
        except AdminOrganizationError as error:
            raise ApiProblem(422, "TOKEN_ADJUSTMENT_REJECTED", str(error)) from None

    @app.put("/api/v1/admin/organizations/{tenant_id}/customer-try-on-limit")
    def admin_customer_try_on_limit(
        request: Request, tenant_id: UUID, body: AdminCustomerTryOnLimitBody
    ) -> dict[str, int]:
        require_platform_admin(request)
        try:
            return admin_organizations.update_customer_try_on_limit(
                tenant_id, body.limit, body.reason
            )
        except AdminOrganizationError as error:
            raise ApiProblem(422, "TRY_ON_LIMIT_UPDATE_REJECTED", str(error)) from None

    @app.post("/api/v1/admin/logout", status_code=204)
    def admin_logout(request: Request, response: Response) -> None:
        token = request.cookies.get(ADMIN_SESSION_COOKIE, "")
        if platform_admin_auth is None or not platform_admin_auth.invalidate(token):
            raise ApiProblem(403, "ADMIN_AUTHENTICATION_REQUIRED", "Admin sign-in required.")
        response.delete_cookie(
            ADMIN_SESSION_COOKIE,
            httponly=True,
            secure=container.secure_cookie,
            samesite="strict",
            path="/",
        )

    @app.get("/api/v1/platform/pricing")
    def platform_pricing() -> dict[str, Any]:
        if container.business_platform is None:
            raise ApiProblem(503, "PRICING_UNAVAILABLE", "Pricing is unavailable.")
        return {
            "unit": "WEARO_TOKEN",
            "rates": container.business_platform.pricing(),
            "explanation": (
                "Wearo Tokens are consumed by product actions; they are not model text tokens. "
                "Costs vary by action and the effective published rate."
            ),
        }

    @app.get("/api/v1/public/try-on-pricing")
    def public_tryon_pricing() -> dict[str, object]:
        current = retail_tryon_pricing.current()
        if current is None:
            return {"status": "UNPUBLISHED", "action_code": "TRY_ON"}
        return {
            "status": "PUBLISHED",
            "action_code": "TRY_ON",
            "price_minor": current["price_minor"],
            "currency": current["currency"],
            "tokens_per_tryon": current["tokens_per_tryon"],
            "effective_from": current["effective_from"],
            "formula": "(try-on price in INR × 10) ÷ 2",
            "packages": retail_tryon_pricing.packages(),
        }

    @app.get("/api/v1/platform/recredit-policy")
    def recredit_policy() -> dict[str, Any]:
        return {
            "automatic_recredit": [
                {
                    "reason_code": "FAILED",
                    "description": "The billable action failed before delivering a result.",
                },
                {
                    "reason_code": "CANCELLED_BEFORE_PROCESSING",
                    "description": "The request was cancelled before processing started.",
                },
                {
                    "reason_code": "NON_DELIVERED",
                    "description": "Processing completed without a deliverable result.",
                },
            ],
            "not_automatic": (
                "Delivered actions and cancellations after processing starts require review."
            ),
            "ledger_entry_type": "RECREDIT",
        }

    @app.get("/api/v1/me/usage")
    def consumer_usage(request: Request, action_code: str = "TRY_ON") -> dict[str, Any]:
        session = _authenticate(request, container)
        if container.plan_usage is None:
            raise ApiProblem(503, "USAGE_UNAVAILABLE", "Usage is unavailable.")
        return asdict(container.plan_usage.for_account(session.account_id, action_code=action_code))

    @app.get("/api/integrations/google-drive/connect")
    def connect_google_drive(request: Request) -> RedirectResponse:
        session = _authenticate(request, container)
        if container.google_drive is None:
            raise ApiProblem(503, "GOOGLE_DRIVE_UNAVAILABLE", "Google Drive is not configured.")
        session_token = request.cookies.get(CONSUMER_SESSION_COOKIE) or request.cookies.get(
            LEGACY_SESSION_COOKIE, ""
        )
        authorization_url = container.google_drive.begin_connection(
            session.account_id, session_token
        )
        return RedirectResponse(authorization_url, status_code=302)

    @app.get("/api/integrations/google-drive/callback")
    def google_drive_callback(
        state: str = Query(min_length=20, max_length=500),
        code: str | None = Query(default=None, min_length=1, max_length=4096),
        error: str | None = Query(default=None, max_length=200),
    ) -> RedirectResponse:
        if container.google_drive is None:
            raise ApiProblem(503, "GOOGLE_DRIVE_UNAVAILABLE", "Google Drive is not configured.")
        if error or not code:
            container.google_drive.cancel_connection_callback(state)
            return RedirectResponse(
                f"{container.google_drive.config.settings_redirect_uri}?drive=cancelled",
                status_code=302,
            )
        try:
            container.google_drive.complete_connection_callback(state, code)
        except DriveIntegrationError as connection_error:
            query = urlencode({"drive": "error", "drive_error": connection_error.code})
            return RedirectResponse(
                f"{container.google_drive.config.settings_redirect_uri}?{query}",
                status_code=302,
            )
        return RedirectResponse(
            f"{container.google_drive.config.settings_redirect_uri}?drive=connected",
            status_code=302,
        )

    @app.get("/api/integrations/google-drive/status")
    def google_drive_status(request: Request) -> dict[str, object]:
        session = _authenticate(request, container)
        if container.google_drive is None:
            return {
                "status": "UNAVAILABLE",
                "connected": False,
                "account_email": None,
                "auto_sync_enabled": False,
                "destination_folder": None,
                "last_successful_sync_at": None,
                "failed_sync_count": 0,
                "reconnect_required": False,
                "last_error_code": None,
            }
        return container.google_drive.status(session.account_id)

    @app.patch("/api/integrations/google-drive/settings")
    def update_google_drive_settings(
        body: GoogleDriveSettingsBody,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        session = _authenticate(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.google_drive is None:
            raise ApiProblem(503, "GOOGLE_DRIVE_UNAVAILABLE", "Google Drive is not configured.")
        return container.google_drive.set_enabled(session.account_id, body.auto_sync_enabled)

    @app.post("/api/integrations/google-drive/disconnect", status_code=204)
    def disconnect_google_drive(
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> Response:
        session = _authenticate(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.google_drive is not None:
            container.google_drive.disconnect(session.account_id)
        return Response(status_code=204)

    @app.post("/api/integrations/google-drive/retry")
    def retry_google_drive_sync(
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, int]:
        session = _authenticate(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.google_drive is None:
            raise ApiProblem(503, "GOOGLE_DRIVE_UNAVAILABLE", "Google Drive is not configured.")
        return {"retried": container.google_drive.retry_failed(session.account_id)}

    @app.get("/api/v1/me/platform")
    def consumer_platform(request: Request) -> dict[str, Any]:
        session = _authenticate(request, container)
        if container.platform_identity is None:
            raise ApiProblem(503, "PLATFORM_UNAVAILABLE", "Platform context is unavailable.")
        return asdict(
            container.platform_identity.context(
                session.principal_id, session.account_id, "CONSUMER"
            )
        )

    @app.get("/api/v1/me/account")
    def consumer_account_lifecycle(request: Request) -> dict[str, Any]:
        session = _authenticate(request, container, allow_deletion_pending=True)
        if container.account_lifecycle is None:
            raise ApiProblem(
                503, "ACCOUNT_LIFECYCLE_UNAVAILABLE", "Account lifecycle is unavailable."
            )
        return asdict(container.account_lifecycle.get(session.account_id, session.principal_id))

    @app.delete("/api/v1/me/account", status_code=202)
    async def cancel_consumer_account(
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, Any]:
        session = _authenticate(
            request,
            container,
            mutation=True,
            csrf_token=x_csrf_token,
            allow_deletion_pending=True,
        )
        if request.query_params or (await request.body()).strip():
            raise ApiProblem(
                422,
                "ACCOUNT_LIFECYCLE_FIELDS_SERVER_MANAGED",
                "Account identity and deletion timing are derived by the server.",
            )
        if container.account_lifecycle is None:
            raise ApiProblem(
                503, "ACCOUNT_CANCELLATION_UNAVAILABLE", "Account cancellation is unavailable."
            )
        lifecycle = container.account_lifecycle.cancel(session.account_id, session.principal_id)
        return asdict(lifecycle)

    @app.post("/api/v1/me/topup-orders")
    def create_consumer_topup(
        body: ConsumerTopUpOrderBody,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        session = _authenticate(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.topups is None:
            raise ApiProblem(503, "PAYMENT_GATEWAY_UNAVAILABLE", "Payments are unavailable.")
        return container.topups.create_consumer_order(
            session.account_id, body.retail_package_id, body.idempotency_key
        )

    @app.post("/api/v1/me/verify-payment")
    def verify_consumer_payment(
        body: RazorpayVerificationBody,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        session = _authenticate(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.topups is None:
            raise ApiProblem(503, "PAYMENT_GATEWAY_UNAVAILABLE", "Payments are unavailable.")
        if (
            not body.razorpay_order_id
            or not body.razorpay_payment_id
            or not body.razorpay_signature
        ):
            raise ApiProblem(400, "INVALID_PAYMENT_SIGNATURE", "Payment fields are required.")
        return container.topups.verify_consumer_checkout_payment(
            session.account_id,
            body.razorpay_order_id,
            body.razorpay_payment_id,
            body.razorpay_signature,
        )

    @app.get("/api/v1/me/billing-history")
    def consumer_billing_history(
        request: Request, page: int = 1, page_size: int = 10
    ) -> dict[str, object]:
        session = _authenticate(request, container)
        if container.topups is None:
            raise ApiProblem(503, "PAYMENT_HISTORY_UNAVAILABLE", "Billing history is unavailable.")
        return container.topups.consumer_billing_history(
            session.account_id, page=page, page_size=page_size
        )

    @app.get("/api/v1/me/billing-history.pdf")
    def download_consumer_billing_history(request: Request) -> Response:
        session = _authenticate(request, container)
        if container.topups is None:
            raise ApiProblem(503, "PAYMENT_HISTORY_UNAVAILABLE", "Billing history is unavailable.")
        rows = container.topups.consumer_billing_report(session.account_id)
        return Response(
            billing_history_pdf(rows),
            media_type="application/pdf",
            headers={
                "Content-Disposition": 'attachment; filename="wearo-billing-history.pdf"'
            },
        )

    @app.get("/api/v1/me/topup-orders/{payment_order_id}")
    def consumer_topup_status(payment_order_id: UUID, request: Request) -> dict[str, object]:
        session = _authenticate(request, container)
        if container.topups is None:
            raise ApiProblem(503, "PAYMENT_STATUS_UNAVAILABLE", "Payment status is unavailable.")
        return container.topups.consumer_order_status(session.account_id, payment_order_id)

    @app.get("/api/v1/business/tenants/{tenant_id}/overview")
    def business_overview(tenant_id: UUID, request: Request) -> dict[str, object]:
        session = _authenticate_business(request, container)
        if container.business_platform is None:
            raise ApiProblem(503, "BUSINESS_PLATFORM_UNAVAILABLE", "Workspace is unavailable.")
        return container.business_platform.overview(session.principal_id, tenant_id)

    @app.get("/api/v1/business/tenants/{tenant_id}/customer-experience-settings")
    def customer_experience_settings(tenant_id: UUID, request: Request) -> dict[str, int]:
        session = _authenticate_business(request, container)
        if container.business_platform is None:
            raise ApiProblem(503, "BUSINESS_PLATFORM_UNAVAILABLE", "Workspace is unavailable.")
        return container.business_platform.customer_experience_settings(
            session.principal_id, tenant_id
        )

    @app.put("/api/v1/business/tenants/{tenant_id}/customer-experience-settings")
    def update_customer_experience_settings(
        tenant_id: UUID,
        body: CustomerExperienceSettingsBody,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, int]:
        session = _authenticate_business(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.business_platform is None:
            raise ApiProblem(503, "BUSINESS_PLATFORM_UNAVAILABLE", "Workspace is unavailable.")
        return container.business_platform.update_customer_experience_settings(
            session.principal_id,
            tenant_id,
            image_retention_days=body.image_retention_days,
            profile_deletion_hours=body.profile_deletion_hours,
            reason=body.reason,
        )

    @app.put("/api/v1/business/tenants/{tenant_id}/operating-profile")
    def update_operating_profile(
        tenant_id: UUID,
        body: OperatingProfileUpdateBody,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        session = _authenticate_business(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.business_platform is None:
            raise ApiProblem(503, "BUSINESS_PLATFORM_UNAVAILABLE", "Workspace is unavailable.")
        return container.business_platform.update_operating_profile(
            session.principal_id, tenant_id, body.operating_profile, body.reason
        )

    @app.get("/api/v1/business/tenants/{tenant_id}/audit-events")
    def business_audit_events(
        tenant_id: UUID, request: Request, limit: int = 100
    ) -> dict[str, object]:
        session = _authenticate_business(request, container)
        if container.sensitive_audit is None:
            raise ApiProblem(503, "AUDIT_UNAVAILABLE", "Audit history is unavailable.")
        return container.sensitive_audit.list_for_tenant(
            session.principal_id, tenant_id, limit=limit
        )

    @app.get("/api/v1/business/tenants/{tenant_id}/agents")
    def list_business_agents(
        tenant_id: UUID, request: Request, store_id: UUID | None = None
    ) -> dict[str, object]:
        session = _authenticate_business(request, container)
        if container.business_agents is None:
            raise ApiProblem(503, "AGENTS_UNAVAILABLE", "Agents are unavailable.")
        return {"items": container.business_agents.list(session.principal_id, tenant_id, store_id)}

    @app.get("/api/v1/business/tenants/{tenant_id}/stores")
    def list_business_stores(tenant_id: UUID, request: Request) -> dict[str, object]:
        session = _authenticate_business(request, container)
        if container.business_stores is None:
            raise ApiProblem(503, "STORES_UNAVAILABLE", "Stores are unavailable.")
        return {"items": container.business_stores.list(session.principal_id, tenant_id)}

    @app.get("/api/v1/agent/me")
    def agent_context(request: Request, business: str, key: str) -> dict[str, object]:
        session = _authenticate_agent(request, container)
        if container.business_agents is None:
            raise ApiProblem(503, "AGENTS_UNAVAILABLE", "Agent access is unavailable.")
        origin = _public_origin(request)
        return container.business_agents.context(session.principal_id, origin, business, key)

    @app.get("/api/v1/store/me")
    def store_context(request: Request) -> dict[str, object]:
        session = _authenticate_store(request, container)
        if container.business_stores is None:
            raise ApiProblem(503, "STORES_UNAVAILABLE", "Store access is unavailable.")
        return container.business_stores.context(session.principal_id)

    @app.get("/api/v1/store/agents")
    def store_agents(request: Request) -> dict[str, object]:
        session = _authenticate_store(request, container)
        if container.business_stores is None or container.business_agents is None:
            raise ApiProblem(503, "STORES_UNAVAILABLE", "Store access is unavailable.")
        context = container.business_stores.context(session.principal_id)
        return {
            "items": container.business_agents.list(
                session.principal_id,
                UUID(str(context["tenant_id"])),
                UUID(str(context["store_id"])),
            )
        }

    @app.get("/api/v1/store/shop-link")
    def store_shop_link(request: Request) -> dict[str, object]:
        session = _authenticate_store(request, container)
        if container.business_shop is None:
            raise ApiProblem(503, "SHOP_LINK_UNAVAILABLE", "Store shop link is unavailable.")
        return container.business_shop.store_details(session.principal_id, _public_origin(request))

    @app.get("/api/v1/store/shop-qr.png")
    def store_shop_qr(request: Request) -> Response:
        session = _authenticate_store(request, container)
        if container.business_shop is None:
            raise ApiProblem(503, "SHOP_LINK_UNAVAILABLE", "Store shop QR is unavailable.")
        details = container.business_shop.store_details(
            session.principal_id, _public_origin(request)
        )
        logo = None
        if details["logo_asset_id"] is not None:
            logo, _ = container.media.read_owned(
                UUID(str(details["logo_asset_id"])), UUID(str(details["account_id"]))
            )
        filename = f"wearo-{details['store_code']}-shop-qr.png"
        return Response(
            qr_poster(str(details["shop_url"]), str(details["display_name"]), logo),
            media_type="image/png",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.post("/api/v1/store/agents", status_code=201)
    def create_store_agent(
        body: BusinessAgentBody,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        session = _authenticate_store(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.business_stores is None or container.business_agents is None:
            raise ApiProblem(503, "STORES_UNAVAILABLE", "Store access is unavailable.")
        context = container.business_stores.context(session.principal_id)
        store_id = UUID(str(context["store_id"]))
        if body.store_id != store_id:
            raise ApiProblem(403, "STORE_SCOPE_REQUIRED", "Resource unavailable.")
        return container.business_agents.save(
            session.principal_id,
            UUID(str(context["tenant_id"])),
            agent_id=None,
            store_id=store_id,
            name=body.name,
            mobile=body.mobile,
        )

    @app.put("/api/v1/store/agents/{agent_id}")
    def update_store_agent(
        agent_id: UUID,
        body: BusinessAgentBody,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        session = _authenticate_store(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.business_stores is None or container.business_agents is None:
            raise ApiProblem(503, "STORES_UNAVAILABLE", "Store access is unavailable.")
        context = container.business_stores.context(session.principal_id)
        store_id = UUID(str(context["store_id"]))
        if body.store_id != store_id:
            raise ApiProblem(403, "STORE_SCOPE_REQUIRED", "Resource unavailable.")
        return container.business_agents.save(
            session.principal_id,
            UUID(str(context["tenant_id"])),
            agent_id=agent_id,
            store_id=store_id,
            name=body.name,
            mobile=body.mobile,
        )

    @app.delete("/api/v1/store/agents/{agent_id}", status_code=204)
    def delete_store_agent(
        agent_id: UUID,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> Response:
        session = _authenticate_store(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.business_stores is None or container.business_agents is None:
            raise ApiProblem(503, "STORES_UNAVAILABLE", "Store access is unavailable.")
        context = container.business_stores.context(session.principal_id)
        container.business_agents.delete(
            session.principal_id,
            UUID(str(context["tenant_id"])),
            agent_id,
            UUID(str(context["store_id"])),
        )
        return Response(status_code=204)

    @app.get("/api/v1/store/advertisements")
    def store_advertisement_list(request: Request) -> dict[str, object]:
        session = _authenticate_store(request, container)
        if container.store_advertisements is None:
            raise ApiProblem(503, "ADVERTISEMENT_UNAVAILABLE", "Advertisements are unavailable.")
        return container.store_advertisements.list(session.principal_id)

    @app.post("/api/v1/store/advertisements/upload", status_code=201)
    async def store_advertisement_upload(
        request: Request,
        title: Annotated[str, Form()],
        starts_on: Annotated[date, Form()],
        ends_on: Annotated[date, Form()],
        image: Annotated[UploadFile, File()],
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        session = _authenticate_store(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.store_advertisements is None:
            raise ApiProblem(503, "ADVERTISEMENT_UNAVAILABLE", "Advertisements are unavailable.")
        content = await image.read(15 * 1024 * 1024 + 1)
        return container.store_advertisements.upload(
            session.principal_id, title, starts_on, ends_on, content
        )

    @app.post("/api/v1/store/advertisements/generate", status_code=201)
    def store_advertisement_generate(
        body: AdvertisementGenerateBody,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        session = _authenticate_store(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.store_advertisements is None:
            raise ApiProblem(503, "ADVERTISEMENT_UNAVAILABLE", "Advertisements are unavailable.")
        return container.store_advertisements.generate(
            session.principal_id,
            body.title,
            body.prompt,
            body.starts_on,
            body.ends_on,
            body.advertisement_id,
        )

    @app.put("/api/v1/store/advertisements/{advertisement_id}")
    def store_advertisement_update(
        advertisement_id: UUID,
        body: AdvertisementUpdateBody,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        session = _authenticate_store(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.store_advertisements is None:
            raise ApiProblem(503, "ADVERTISEMENT_UNAVAILABLE", "Advertisements are unavailable.")
        return container.store_advertisements.update(
            session.principal_id,
            advertisement_id,
            body.title,
            body.prompt,
            body.starts_on,
            body.ends_on,
        )

    @app.put("/api/v1/store/advertisements/{advertisement_id}/activate")
    def store_advertisement_activate(
        advertisement_id: UUID,
        body: AdvertisementActivationBody,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        session = _authenticate_store(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.store_advertisements is None:
            raise ApiProblem(503, "ADVERTISEMENT_UNAVAILABLE", "Advertisements are unavailable.")
        return container.store_advertisements.activate(
            session.principal_id, advertisement_id, body.active_date
        )

    @app.delete("/api/v1/store/advertisements/active/{active_date}")
    def store_advertisement_deactivate(
        active_date: date,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        session = _authenticate_store(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.store_advertisements is None:
            raise ApiProblem(503, "ADVERTISEMENT_UNAVAILABLE", "Advertisements are unavailable.")
        return container.store_advertisements.deactivate(session.principal_id, active_date)

    @app.delete("/api/v1/store/advertisements/{advertisement_id}", status_code=204)
    def store_advertisement_delete(
        advertisement_id: UUID,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> Response:
        session = _authenticate_store(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.store_advertisements is None:
            raise ApiProblem(503, "ADVERTISEMENT_UNAVAILABLE", "Advertisements are unavailable.")
        container.store_advertisements.delete(session.principal_id, advertisement_id)
        return Response(status_code=204)

    @app.get("/api/v1/store/advertisements/{advertisement_id}/image")
    def store_advertisement_image(advertisement_id: UUID, request: Request) -> Response:
        session = _authenticate_store(request, container)
        if container.store_advertisements is None:
            raise ApiProblem(503, "ADVERTISEMENT_UNAVAILABLE", "Advertisements are unavailable.")
        content, content_type = container.store_advertisements.image(
            session.principal_id, advertisement_id
        )
        return Response(content, media_type=content_type)

    @app.get("/api/v1/public/agent-manifest")
    def public_agent_manifest(business: str, key: str) -> JSONResponse:
        if container.business_shop is None:
            raise ApiProblem(503, "SHOP_LINK_UNAVAILABLE", "Agent app is unavailable.")
        details = container.business_shop.public_details(business, key)
        start_url = f"/agent/{business}?key={key}"
        return JSONResponse(
            {
                "name": f"{details['display_name']} Agent",
                "short_name": "Wearo Agent",
                "description": "Manage customer try-on allowances for this Wearo business.",
                "id": f"/agent/{business}",
                "start_url": start_url,
                "scope": "/",
                "display": "standalone",
                "orientation": "portrait-primary",
                "background_color": "#faf7f2",
                "theme_color": "#3b1746",
                "categories": ["business", "productivity"],
                "icons": [
                    {
                        "src": "/wearo-brand.png",
                        "sizes": "1254x1254",
                        "type": "image/png",
                        "purpose": "any maskable",
                    }
                ],
            }
        )

    @app.get("/api/v1/agent/shop-qr.png")
    def agent_shop_qr(request: Request, business: str, key: str) -> Response:
        session = _authenticate_agent(request, container)
        if container.business_agents is None:
            raise ApiProblem(503, "AGENTS_UNAVAILABLE", "Agent access is unavailable.")
        origin = _public_origin(request)
        context = container.business_agents.context(session.principal_id, origin, business, key)
        return Response(
            qr_poster(str(context["shop_url"]), str(context["display_name"])),
            media_type="image/png",
        )

    @app.get("/api/v1/agent/allowances")
    def agent_allowances(
        request: Request, mobile: str, business: str, key: str
    ) -> dict[str, object]:
        session = _authenticate_agent(request, container)
        if container.business_agents is None or container.business_allowances is None:
            raise ApiProblem(503, "ALLOWANCE_UNAVAILABLE", "Allowances are unavailable.")
        context = container.business_agents.context(
            session.principal_id, _public_origin(request), business, key
        )
        allowance = container.business_allowances.get(
            session.principal_id, UUID(str(context["tenant_id"])), mobile, agent=True
        )
        user = allowance["user"]
        if not isinstance(user, dict):
            raise ApiProblem(404, "CUSTOMER_UNAVAILABLE", "Customer allowance is unavailable.")
        return {
            "customer": {
                "mobile": user["normalized_mobile"],
                "allotted": user["effective_limit"],
                "used": user["used_count"],
                "remaining": user["remaining"],
            }
        }

    @app.post("/api/v1/agent/allowances")
    def agent_adjust_allowance(
        body: UserAllowanceBody,
        request: Request,
        business: str,
        key: str,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        session = _authenticate_agent(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.business_agents is None or container.business_allowances is None:
            raise ApiProblem(503, "ALLOWANCE_UNAVAILABLE", "Allowances are unavailable.")
        context = container.business_agents.context(
            session.principal_id, _public_origin(request), business, key
        )
        allowance = container.business_allowances.adjust_user(
            session.principal_id,
            UUID(str(context["tenant_id"])),
            body.mobile,
            body.action,
            body.amount,
            agent=True,
        )
        user = allowance["user"]
        if not isinstance(user, dict):
            raise ApiProblem(404, "CUSTOMER_UNAVAILABLE", "Customer allowance is unavailable.")
        return {
            "customer": {
                "mobile": user["normalized_mobile"],
                "allotted": user["effective_limit"],
                "used": user["used_count"],
                "remaining": user["remaining"],
            }
        }

    @app.get("/api/v1/business/tenants/{tenant_id}/allowances")
    def business_allowances(
        tenant_id: UUID, request: Request, mobile: str | None = None
    ) -> dict[str, object]:
        session = _authenticate_business(request, container)
        if container.business_allowances is None:
            raise ApiProblem(503, "ALLOWANCE_UNAVAILABLE", "Allowances are unavailable.")
        return container.business_allowances.get(session.principal_id, tenant_id, mobile)

    @app.get("/api/v1/business/tenants/{tenant_id}/customers/search")
    def search_business_customer(
        tenant_id: UUID, request: Request, mobile: str
    ) -> dict[str, object]:
        session = _authenticate_business(request, container)
        if container.business_allowances is None:
            raise ApiProblem(503, "CUSTOMER_SEARCH_UNAVAILABLE", "Customer search is unavailable.")
        return container.business_allowances.find_participant(
            session.principal_id, tenant_id, mobile
        )

    @app.get("/api/v1/business/tenants/{tenant_id}/customers")
    def list_business_customers(
        tenant_id: UUID,
        request: Request,
        search: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, object]:
        session = _authenticate_business(request, container)
        if container.business_allowances is None:
            raise ApiProblem(503, "CUSTOMERS_UNAVAILABLE", "Customers are unavailable.")
        return container.business_allowances.list_participants(
            session.principal_id,
            tenant_id,
            search=search,
            page=page,
            page_size=page_size,
        )

    @app.get("/api/v1/business/tenants/{tenant_id}/smart-ads")
    def list_business_smart_ads(tenant_id: UUID, request: Request) -> dict[str, object]:
        session = _authenticate_business(request, container)
        if container.business_smart_ads is None:
            raise ApiProblem(503, "SMART_ADS_UNAVAILABLE", "SmartAds are unavailable.")
        return container.business_smart_ads.list(session.principal_id, tenant_id)

    @app.post("/api/v1/business/tenants/{tenant_id}/smart-ads", status_code=201)
    async def create_business_smart_ad(
        tenant_id: UUID,
        request: Request,
        title: Annotated[str, Form(min_length=1, max_length=120)],
        prompt: Annotated[str, Form(min_length=1, max_length=2000)],
        jewellery: Annotated[UploadFile, File()],
        model_photo: Annotated[UploadFile | None, File()] = None,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        session = _authenticate_business(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.business_smart_ads is None:
            raise ApiProblem(503, "SMART_ADS_UNAVAILABLE", "SmartAds are unavailable.")
        jewellery_content = await jewellery.read()
        model_content = await model_photo.read() if model_photo is not None else None
        return container.business_smart_ads.create(
            session.principal_id,
            tenant_id,
            title=title,
            prompt=prompt,
            jewellery=jewellery_content,
            jewellery_type=jewellery.content_type or "",
            model_photo=model_content,
            model_type=model_photo.content_type if model_photo is not None else None,
        )

    @app.post("/api/v1/business/tenants/{tenant_id}/smart-ads/{smart_ad_id}/generate")
    def generate_business_smart_ad(
        tenant_id: UUID,
        smart_ad_id: UUID,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        session = _authenticate_business(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.business_smart_ads is None:
            raise ApiProblem(503, "SMART_ADS_UNAVAILABLE", "SmartAds are unavailable.")
        return container.business_smart_ads.generate(
            session.principal_id, tenant_id, smart_ad_id
        )

    @app.post("/api/v1/business/tenants/{tenant_id}/smart-ads/{smart_ad_id}/accept")
    def accept_business_smart_ad(
        tenant_id: UUID,
        smart_ad_id: UUID,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        session = _authenticate_business(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.business_smart_ads is None:
            raise ApiProblem(503, "SMART_ADS_UNAVAILABLE", "SmartAds are unavailable.")
        return container.business_smart_ads.accept(
            session.principal_id, tenant_id, smart_ad_id
        )

    @app.put("/api/v1/business/tenants/{tenant_id}/smart-ads/{smart_ad_id}")
    def update_business_smart_ad(
        tenant_id: UUID,
        smart_ad_id: UUID,
        body: SmartAdUpdateBody,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        session = _authenticate_business(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.business_smart_ads is None:
            raise ApiProblem(503, "SMART_ADS_UNAVAILABLE", "SmartAds are unavailable.")
        return container.business_smart_ads.update(
            session.principal_id,
            tenant_id,
            smart_ad_id,
            title=body.title,
            prompt=body.prompt,
        )

    @app.delete(
        "/api/v1/business/tenants/{tenant_id}/smart-ads/{smart_ad_id}", status_code=204
    )
    def delete_business_smart_ad(
        tenant_id: UUID,
        smart_ad_id: UUID,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> Response:
        session = _authenticate_business(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.business_smart_ads is None:
            raise ApiProblem(503, "SMART_ADS_UNAVAILABLE", "SmartAds are unavailable.")
        container.business_smart_ads.delete(session.principal_id, tenant_id, smart_ad_id)
        return Response(status_code=204)

    @app.get("/api/v1/business/tenants/{tenant_id}/smart-ads/{smart_ad_id}/image")
    def business_smart_ad_image(
        tenant_id: UUID,
        smart_ad_id: UUID,
        request: Request,
        role: Literal["jewellery", "model", "creative"] = "creative",
    ) -> Response:
        session = _authenticate_business(request, container)
        if container.business_smart_ads is None:
            raise ApiProblem(503, "SMART_ADS_UNAVAILABLE", "SmartAds are unavailable.")
        content, content_type = container.business_smart_ads.image(
            session.principal_id, tenant_id, smart_ad_id, role
        )
        return Response(content, media_type=content_type)

    @app.post("/api/v1/business/tenants/{tenant_id}/smart-ad-schedules", status_code=201)
    def schedule_business_smart_ad(
        tenant_id: UUID,
        body: SmartAdScheduleBody,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        session = _authenticate_business(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.business_smart_ads is None:
            raise ApiProblem(503, "SMART_ADS_UNAVAILABLE", "SmartAds are unavailable.")
        return container.business_smart_ads.schedule(
            session.principal_id,
            tenant_id,
            body.smart_ad_id,
            occasion=body.occasion,
            scheduled_for=body.scheduled_for,
            channel=body.channel,
            target_gender=body.target_gender,
            target_age_min=body.target_age_min,
            target_age_max=body.target_age_max,
            public_origin=_public_origin(request),
        )

    @app.put("/api/v1/business/tenants/{tenant_id}/smart-ad-schedules/{schedule_id}")
    def update_business_smart_ad_schedule(
        tenant_id: UUID,
        schedule_id: UUID,
        body: SmartAdScheduleBody,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        session = _authenticate_business(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.business_smart_ads is None:
            raise ApiProblem(503, "SMART_ADS_UNAVAILABLE", "SmartAds are unavailable.")
        return container.business_smart_ads.update_schedule(
            session.principal_id,
            tenant_id,
            schedule_id,
            body.smart_ad_id,
            occasion=body.occasion,
            scheduled_for=body.scheduled_for,
            channel=body.channel,
            target_gender=body.target_gender,
            target_age_min=body.target_age_min,
            target_age_max=body.target_age_max,
            public_origin=_public_origin(request),
        )

    @app.delete(
        "/api/v1/business/tenants/{tenant_id}/smart-ad-schedules/{schedule_id}",
        status_code=204,
    )
    def delete_business_smart_ad_schedule(
        tenant_id: UUID,
        schedule_id: UUID,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> Response:
        session = _authenticate_business(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.business_smart_ads is None:
            raise ApiProblem(503, "SMART_ADS_UNAVAILABLE", "SmartAds are unavailable.")
        container.business_smart_ads.delete_schedule(
            session.principal_id, tenant_id, schedule_id
        )
        return Response(status_code=204)

    @app.put("/api/v1/business/tenants/{tenant_id}/allowances/policy")
    def update_business_allowance_policy(
        tenant_id: UUID,
        body: AllowancePolicyBody,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        session = _authenticate_business(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.business_allowances is None:
            raise ApiProblem(503, "ALLOWANCE_UNAVAILABLE", "Allowances are unavailable.")
        return container.business_allowances.update_policy(
            session.principal_id, tenant_id, body.default_try_on_limit
        )

    @app.post("/api/v1/business/tenants/{tenant_id}/allowances/user")
    def adjust_business_user_allowance(
        tenant_id: UUID,
        body: UserAllowanceBody,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        session = _authenticate_business(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.business_allowances is None:
            raise ApiProblem(503, "ALLOWANCE_UNAVAILABLE", "Allowances are unavailable.")
        return container.business_allowances.adjust_user(
            session.principal_id, tenant_id, body.mobile, body.action, body.amount
        )

    @app.get("/api/v1/business/tenants/{tenant_id}/communications")
    def business_communications(tenant_id: UUID, request: Request) -> dict[str, object]:
        session = _authenticate_business(request, container)
        if container.communications is None:
            raise ApiProblem(503, "COMMUNICATIONS_UNAVAILABLE", "Communications are unavailable.")
        return container.communications.overview(session.principal_id, tenant_id)

    @app.get("/api/v1/business/tenants/{tenant_id}/reconciliation-report")
    def business_reconciliation_report(tenant_id: UUID, request: Request) -> dict[str, object]:
        session = _authenticate_business(request, container)
        if container.business_reports is None:
            raise ApiProblem(503, "REPORT_UNAVAILABLE", "Report is unavailable.")
        return container.business_reports.reconciliation(session.principal_id, tenant_id)

    @app.get("/api/v1/business/tenants/{tenant_id}/reconciliation-report.csv")
    def download_business_reconciliation(tenant_id: UUID, request: Request) -> PlainTextResponse:
        session = _authenticate_business(request, container)
        if container.business_reports is None:
            raise ApiProblem(503, "REPORT_UNAVAILABLE", "Report is unavailable.")
        report = container.business_reports.reconciliation(session.principal_id, tenant_id)
        return PlainTextResponse(
            reconciliation_csv(report),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="wearo-reconciliation.csv"'},
        )

    @app.get("/api/v1/business/tenants/{tenant_id}/support-cases")
    def list_business_support_cases(tenant_id: UUID, request: Request) -> dict[str, object]:
        session = _authenticate_business(request, container)
        if container.support_cases is None:
            raise ApiProblem(503, "SUPPORT_UNAVAILABLE", "Support is unavailable.")
        return {"items": container.support_cases.list(session.principal_id, tenant_id)}

    @app.get("/api/v1/business/tenants/{tenant_id}/support-access-grants")
    def business_support_access_grants(tenant_id: UUID, request: Request) -> dict[str, object]:
        session = _authenticate_business(request, container)
        if container.support_access is None:
            raise ApiProblem(503, "SUPPORT_ACCESS_UNAVAILABLE", "Access grants are unavailable.")
        return {"items": container.support_access.list_for_owner(session.principal_id, tenant_id)}

    @app.delete(
        "/api/v1/business/tenants/{tenant_id}/support-access-grants/{grant_id}",
        status_code=204,
    )
    def revoke_business_support_access(
        tenant_id: UUID,
        grant_id: UUID,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> Response:
        session = _authenticate_business(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.support_access is None:
            raise ApiProblem(503, "SUPPORT_ACCESS_UNAVAILABLE", "Access grants are unavailable.")
        container.support_access.revoke(session.principal_id, tenant_id, grant_id)
        return Response(status_code=204)

    @app.post("/api/v1/business/tenants/{tenant_id}/support-cases", status_code=201)
    def create_business_support_case(
        tenant_id: UUID,
        body: SupportCaseBody,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        session = _authenticate_business(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.support_cases is None:
            raise ApiProblem(503, "SUPPORT_UNAVAILABLE", "Support is unavailable.")
        return container.support_cases.create(
            session.principal_id, tenant_id, body.case_type, body.reason
        )

    @app.get("/api/v1/business/tenants/{tenant_id}/support-cases/{case_id}")
    def business_support_case(
        tenant_id: UUID, case_id: UUID, request: Request
    ) -> dict[str, object]:
        session = _authenticate_business(request, container)
        if container.support_cases is None:
            raise ApiProblem(503, "SUPPORT_UNAVAILABLE", "Support is unavailable.")
        return container.support_cases.detail(session.principal_id, tenant_id, case_id)

    @app.post("/api/v1/business/tenants/{tenant_id}/legal-notices/{notice_id}/accept")
    def accept_business_legal_notice(
        tenant_id: UUID,
        notice_id: UUID,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        session = _authenticate_business(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.communications is None:
            raise ApiProblem(503, "COMMUNICATIONS_UNAVAILABLE", "Notices are unavailable.")
        return container.communications.accept(session.principal_id, tenant_id, notice_id)

    @app.put("/api/v1/business/tenants/{tenant_id}/communication-preference")
    def update_business_communication_preference(
        tenant_id: UUID,
        body: CommunicationPreferenceBody,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        session = _authenticate_business(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.communications is None:
            raise ApiProblem(503, "COMMUNICATIONS_UNAVAILABLE", "Communications are unavailable.")
        return container.communications.set_preference(
            session.principal_id, tenant_id, body.channel, body.topic, body.enabled
        )

    @app.post("/api/v1/business/tenants/{tenant_id}/agents", status_code=201)
    def create_business_agent(
        tenant_id: UUID,
        body: BusinessAgentBody,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        session = _authenticate_business(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.business_agents is None:
            raise ApiProblem(503, "AGENTS_UNAVAILABLE", "Agents are unavailable.")
        return container.business_agents.save(
            session.principal_id,
            tenant_id,
            agent_id=None,
            store_id=body.store_id,
            name=body.name,
            mobile=body.mobile,
        )

    @app.put("/api/v1/business/tenants/{tenant_id}/agents/{agent_id}")
    def update_business_agent(
        tenant_id: UUID,
        agent_id: UUID,
        body: BusinessAgentBody,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        session = _authenticate_business(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.business_agents is None:
            raise ApiProblem(503, "AGENTS_UNAVAILABLE", "Agents are unavailable.")
        return container.business_agents.save(
            session.principal_id,
            tenant_id,
            agent_id=agent_id,
            store_id=body.store_id,
            name=body.name,
            mobile=body.mobile,
        )

    @app.put("/api/v1/business/tenants/{tenant_id}/agents/{agent_id}/store")
    def move_business_agent(
        tenant_id: UUID,
        agent_id: UUID,
        body: AgentMoveBody,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        session = _authenticate_business(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.business_agents is None:
            raise ApiProblem(503, "AGENTS_UNAVAILABLE", "Agents are unavailable.")
        return container.business_agents.move(
            session.principal_id, tenant_id, agent_id, body.store_id
        )

    @app.delete("/api/v1/business/tenants/{tenant_id}/agents/{agent_id}", status_code=204)
    def delete_business_agent(
        tenant_id: UUID,
        agent_id: UUID,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> Response:
        session = _authenticate_business(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.business_agents is None:
            raise ApiProblem(503, "AGENTS_UNAVAILABLE", "Agents are unavailable.")
        container.business_agents.delete(session.principal_id, tenant_id, agent_id)
        return Response(status_code=204)

    @app.post("/api/v1/business/tenants/{tenant_id}/stores", status_code=201)
    def create_business_store(
        tenant_id: UUID,
        body: BusinessStoreBody,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        session = _authenticate_business(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.business_stores is None:
            raise ApiProblem(503, "STORES_UNAVAILABLE", "Stores are unavailable.")
        return container.business_stores.save(
            session.principal_id,
            tenant_id,
            store_id=None,
            name=body.name,
            code=body.code,
            admin_email=body.admin_email,
            admin_mobile=body.admin_mobile,
        )

    @app.put("/api/v1/business/tenants/{tenant_id}/stores/{store_id}")
    def update_business_store(
        tenant_id: UUID,
        store_id: UUID,
        body: BusinessStoreBody,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        session = _authenticate_business(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.business_stores is None:
            raise ApiProblem(503, "STORES_UNAVAILABLE", "Stores are unavailable.")
        return container.business_stores.save(
            session.principal_id,
            tenant_id,
            store_id=store_id,
            name=body.name,
            code=body.code,
            admin_email=body.admin_email,
            admin_mobile=body.admin_mobile,
        )

    @app.get("/api/v1/business/tenants/{tenant_id}/shop-link")
    def business_shop_link(tenant_id: UUID, request: Request) -> dict[str, object]:
        session = _authenticate_business(request, container)
        if container.business_shop is None:
            raise ApiProblem(503, "SHOP_LINK_UNAVAILABLE", "Shop link is unavailable.")
        origin = _public_origin(request)
        return container.business_shop.details(session.principal_id, tenant_id, origin)

    @app.get("/api/v1/business/tenants/{tenant_id}/shop-qr.png")
    def business_shop_qr(tenant_id: UUID, request: Request) -> Response:
        session = _authenticate_business(request, container)
        if container.business_shop is None:
            raise ApiProblem(503, "SHOP_LINK_UNAVAILABLE", "Shop QR is unavailable.")
        details = container.business_shop.details(
            session.principal_id,
            tenant_id,
            _public_origin(request),
        )
        logo = None
        if details["logo_asset_id"] is not None:
            logo, _ = container.media.read_owned(
                UUID(str(details["logo_asset_id"])), UUID(str(details["account_id"]))
            )
        return Response(
            qr_poster(str(details["shop_url"]), str(details["display_name"]), logo),
            media_type="image/png",
            headers={"Content-Disposition": 'attachment; filename="wearo-shop-qr.png"'},
        )

    @app.get("/api/v1/business/tenants/{tenant_id}/company-logo")
    def business_company_logo(tenant_id: UUID, request: Request) -> Response:
        session = _authenticate_business(request, container)
        if container.business_shop is None:
            raise ApiProblem(503, "BUSINESS_LOGO_UNAVAILABLE", "Company logo is unavailable.")
        details = container.business_shop.details(
            session.principal_id, tenant_id, _public_origin(request)
        )
        if details["logo_asset_id"] is None:
            raise ApiProblem(404, "BUSINESS_LOGO_NOT_FOUND", "No company logo has been uploaded.")
        content, mime_type = container.media.read_owned(
            UUID(str(details["logo_asset_id"])), UUID(str(details["account_id"]))
        )
        return Response(
            content, media_type=mime_type, headers={"Cache-Control": "private, no-store"}
        )

    @app.put("/api/v1/business/tenants/{tenant_id}/company-logo")
    async def update_business_company_logo(
        tenant_id: UUID,
        request: Request,
        image: Annotated[UploadFile, File()],
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        session = _authenticate_business(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.business_shop is None:
            raise ApiProblem(503, "BUSINESS_LOGO_UNAVAILABLE", "Company logo is unavailable.")
        content = await image.read()
        stored = container.media.store_business_logo(
            session.account_id, content, image.content_type or "application/octet-stream"
        )
        return container.business_shop.set_logo(session.principal_id, tenant_id, stored.asset_id)

    @app.get("/api/v1/public/shops/{business_reference}")
    def public_business_shop(business_reference: str, key: str) -> dict[str, object]:
        if container.business_shop is None:
            raise ApiProblem(503, "SHOP_LINK_UNAVAILABLE", "Shop is unavailable.")
        details = container.business_shop.public_details(business_reference, key)
        return {name: value for name, value in details.items() if name != "account_id"}

    @app.get("/api/v1/public/shops/{business_reference}/stores/{store_reference}")
    def public_store_shop(
        business_reference: str, store_reference: str, key: str
    ) -> dict[str, object]:
        if container.business_shop is None:
            raise ApiProblem(503, "SHOP_LINK_UNAVAILABLE", "Store is unavailable.")
        details = container.business_shop.public_store_details(
            business_reference, store_reference, key
        )
        return {name: value for name, value in details.items() if name != "account_id"}

    @app.get("/api/v1/public/shops/{business_reference}/stores/{store_reference}/logo")
    def public_store_shop_logo(business_reference: str, store_reference: str, key: str) -> Response:
        if container.business_shop is None:
            raise ApiProblem(503, "SHOP_LINK_UNAVAILABLE", "Store is unavailable.")
        details = container.business_shop.public_store_details(
            business_reference, store_reference, key
        )
        if details["logo_asset_id"] is None:
            raise ApiProblem(404, "BUSINESS_LOGO_NOT_FOUND", "No company logo has been uploaded.")
        content, mime_type = container.media.read_owned(
            UUID(str(details["logo_asset_id"])), UUID(str(details["account_id"]))
        )
        return Response(
            content, media_type=mime_type, headers={"Cache-Control": "public, max-age=300"}
        )

    @app.get("/api/v1/public/shops/{business_reference}/logo")
    def public_business_shop_logo(business_reference: str, key: str) -> Response:
        if container.business_shop is None:
            raise ApiProblem(503, "SHOP_LINK_UNAVAILABLE", "Shop is unavailable.")
        details = container.business_shop.public_details(business_reference, key)
        if details["logo_asset_id"] is None:
            raise ApiProblem(404, "BUSINESS_LOGO_NOT_FOUND", "No company logo has been uploaded.")
        content, mime_type = container.media.read_owned(
            UUID(str(details["logo_asset_id"])), UUID(str(details["account_id"]))
        )
        return Response(
            content,
            media_type=mime_type,
            headers={"Cache-Control": "public, max-age=300"},
        )

    @app.post("/api/v1/public/shops/{business_reference}/sessions", status_code=201)
    def activate_sponsored_session(
        business_reference: str,
        body: SponsoredSessionBody,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        session = _authenticate(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.sponsored_tryons is None:
            raise ApiProblem(503, "SPONSORED_SESSION_UNAVAILABLE", "Session is unavailable.")
        return container.sponsored_tryons.activate(
            business_reference=business_reference,
            public_key=body.key,
            consumer_account_id=session.account_id,
            consumer_principal_id=session.principal_id,
        )

    @app.post(
        "/api/v1/public/shops/{business_reference}/stores/{store_reference}/sessions",
        status_code=201,
    )
    def activate_store_sponsored_session(
        business_reference: str,
        store_reference: str,
        body: SponsoredSessionBody,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        session = _authenticate(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.sponsored_tryons is None:
            raise ApiProblem(503, "SPONSORED_SESSION_UNAVAILABLE", "Session is unavailable.")
        return container.sponsored_tryons.activate(
            business_reference=business_reference,
            store_reference=store_reference,
            public_key=body.key,
            consumer_account_id=session.account_id,
            consumer_principal_id=session.principal_id,
        )

    @app.get("/api/v1/sponsored-sessions/{session_id}")
    def sponsored_session_status(session_id: UUID, request: Request) -> dict[str, object]:
        session = _authenticate(request, container)
        if container.sponsored_tryons is None:
            raise ApiProblem(503, "SPONSORED_SESSION_UNAVAILABLE", "Session is unavailable.")
        return container.sponsored_tryons.status(
            session_id, session.account_id, session.principal_id
        )

    @app.get("/api/v1/sponsored-sessions/{session_id}/advertisement")
    def sponsored_session_advertisement(session_id: UUID, request: Request) -> Response:
        session = _authenticate(request, container)
        if container.store_advertisements is None:
            raise ApiProblem(503, "ADVERTISEMENT_UNAVAILABLE", "Advertisements are unavailable.")
        active = container.store_advertisements.active_for_sponsored_session(
            session_id, session.account_id, session.principal_id
        )
        if active is None:
            return Response(status_code=204)
        content, content_type = active
        return Response(content, media_type=content_type)

    @app.post("/api/v1/sponsored-sessions/{session_id}/try-ons", status_code=201)
    def consume_sponsored_try_on(
        session_id: UUID,
        body: SponsoredTryOnBody,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        session = _authenticate(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.sponsored_tryons is None:
            raise ApiProblem(503, "SPONSORED_SESSION_UNAVAILABLE", "Session is unavailable.")
        return container.sponsored_tryons.consume(
            session_id=session_id,
            consumer_account_id=session.account_id,
            consumer_principal_id=session.principal_id,
            request_key=body.request_key,
        )

    @app.get("/api/v1/business/tenants/{tenant_id}/billing-profile")
    def get_business_billing_profile(tenant_id: UUID, request: Request) -> dict[str, object]:
        session = _authenticate_business(request, container)
        if container.business_billing is None:
            raise ApiProblem(503, "BILLING_UNAVAILABLE", "Billing profile is unavailable.")
        return container.business_billing.get(session.principal_id, tenant_id)

    @app.get("/api/v1/business/tenants/{tenant_id}/try-on-status")
    def get_business_try_on_status(tenant_id: UUID, request: Request) -> dict[str, object]:
        session = _authenticate_business(request, container)
        if container.business_tryon_status is None:
            raise ApiProblem(503, "TRY_ON_STATUS_UNAVAILABLE", "Try-on status is unavailable.")
        return container.business_tryon_status.get(session.principal_id, tenant_id)

    @app.put("/api/v1/business/tenants/{tenant_id}/try-on-status")
    def update_business_try_on_status(
        tenant_id: UUID,
        body: BusinessTryOnStatusBody,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        session = _authenticate_business(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.business_tryon_status is None:
            raise ApiProblem(503, "TRY_ON_STATUS_UNAVAILABLE", "Try-on status is unavailable.")
        return container.business_tryon_status.transition(
            session.principal_id, tenant_id, body.status
        )

    @app.get("/api/v1/business/tenants/{tenant_id}/token-transactions")
    def business_token_transactions(
        tenant_id: UUID,
        request: Request,
        category: TransactionCategory | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict[str, object]:
        session = _authenticate_business(request, container)
        if container.wallet_transactions is None:
            raise ApiProblem(503, "TRANSACTION_HISTORY_UNAVAILABLE", "History is unavailable.")
        return container.wallet_transactions.history(
            session.principal_id,
            tenant_id,
            category=category,
            date_from=date_from,
            date_to=date_to,
        )

    @app.get("/api/v1/business/tenants/{tenant_id}/topup-packs")
    def business_topup_packs(tenant_id: UUID, request: Request) -> dict[str, object]:
        session = _authenticate_business(request, container)
        if container.topups is None:
            raise ApiProblem(503, "PAYMENT_GATEWAY_UNAVAILABLE", "Top-ups are unavailable.")
        return container.topups.purchase_context(session.principal_id, tenant_id)

    @app.post("/api/v1/business/tenants/{tenant_id}/topup-orders")
    def create_business_topup(
        tenant_id: UUID,
        body: TopUpOrderBody,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        session = _authenticate_business(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.topups is None:
            raise ApiProblem(503, "PAYMENT_GATEWAY_UNAVAILABLE", "Top-ups are unavailable.")
        return container.topups.create_order(
            session.principal_id, tenant_id, body.pack_id, body.idempotency_key
        )

    @app.post("/api/v1/payments/webhook")
    async def payment_webhook(
        request: Request,
        x_razorpay_signature: Annotated[
            str | None, Header(alias="X-Razorpay-Signature")
        ] = None,
        x_razorpay_event_id: Annotated[
            str | None, Header(alias="X-Razorpay-Event-Id")
        ] = None,
    ) -> dict[str, object]:
        if container.topups is None:
            raise ApiProblem(503, "PAYMENT_GATEWAY_UNAVAILABLE", "Payments are unavailable.")
        return container.topups.accept_webhook(
            await request.body(), x_razorpay_signature, x_razorpay_event_id
        )

    @app.post("/api/v1/business/tenants/{tenant_id}/verify-payment")
    def verify_business_payment(
        tenant_id: UUID,
        body: RazorpayVerificationBody,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        session = _authenticate_business(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.topups is None:
            raise ApiProblem(503, "PAYMENT_GATEWAY_UNAVAILABLE", "Payments are unavailable.")
        if (
            not body.razorpay_order_id
            or not body.razorpay_payment_id
            or not body.razorpay_signature
        ):
            raise ApiProblem(400, "INVALID_PAYMENT_SIGNATURE", "Payment fields are required.")
        return container.topups.verify_checkout_payment(
            session.principal_id,
            tenant_id,
            body.razorpay_order_id,
            body.razorpay_payment_id,
            body.razorpay_signature,
        )

    @app.get("/api/v1/business/tenants/{tenant_id}/payment-receipts/{receipt_id}")
    def business_payment_receipt(
        tenant_id: UUID, receipt_id: UUID, request: Request
    ) -> dict[str, object]:
        session = _authenticate_business(request, container)
        if container.topups is None:
            raise ApiProblem(503, "PAYMENT_GATEWAY_UNAVAILABLE", "Receipts are unavailable.")
        return container.topups.receipt(session.principal_id, tenant_id, receipt_id)

    @app.get("/api/v1/business/tenants/{tenant_id}/payment-reconciliation")
    def business_payment_reconciliation(tenant_id: UUID, request: Request) -> dict[str, object]:
        session = _authenticate_business(request, container)
        if container.topups is None:
            raise ApiProblem(503, "PAYMENT_GATEWAY_UNAVAILABLE", "Payments are unavailable.")
        return container.topups.reconciliation(session.principal_id, tenant_id)

    @app.get("/api/v1/business/tenants/{tenant_id}/payment-receipts/{receipt_id}.txt")
    def download_business_payment_receipt(
        tenant_id: UUID, receipt_id: UUID, request: Request
    ) -> PlainTextResponse:
        session = _authenticate_business(request, container)
        if container.topups is None:
            raise ApiProblem(503, "PAYMENT_GATEWAY_UNAVAILABLE", "Receipts are unavailable.")
        receipt = container.topups.receipt(session.principal_id, tenant_id, receipt_id)
        amount_minor = receipt["amount_minor"]
        if not isinstance(amount_minor, int):
            raise ApiProblem(500, "INVALID_RECEIPT", "Receipt amount is invalid.")
        body = (
            f"Wearo payment receipt {receipt['receipt_number']}\n"
            f"Issued: {receipt['issued_at']}\n"
            f"Payment reference: {receipt['provider_payment_id']}\n"
            f"Amount: {receipt['currency']} {amount_minor / 100:.2f}\n"
            f"Wearo Tokens credited: {receipt['tokens_credited']}\n"
        )
        return PlainTextResponse(
            body,
            headers={"Content-Disposition": 'attachment; filename="wearo-payment-receipt.txt"'},
        )

    @app.get("/api/v1/business/tenants/{tenant_id}/invoices/{invoice_id}.txt")
    def download_business_invoice(
        tenant_id: UUID, invoice_id: UUID, request: Request
    ) -> PlainTextResponse:
        session = _authenticate_business(request, container)
        if container.topups is None:
            raise ApiProblem(503, "PAYMENT_GATEWAY_UNAVAILABLE", "Invoices are unavailable.")
        invoice = container.topups.invoice(session.principal_id, tenant_id, invoice_id)
        business = invoice["business_snapshot"]
        tax = invoice["tax_snapshot"]
        if not isinstance(business, dict) or not isinstance(tax, dict):
            raise ApiProblem(500, "INVALID_INVOICE", "Invoice snapshot is invalid.")
        subtotal = invoice["subtotal_minor"]
        tax_amount = invoice["tax_minor"]
        total = invoice["amount_minor"]
        rate = tax.get("rate_basis_points", 0)
        if (
            not isinstance(subtotal, int)
            or not isinstance(tax_amount, int)
            or not isinstance(total, int)
            or not isinstance(rate, int)
        ):
            raise ApiProblem(500, "INVALID_INVOICE", "Invoice amounts are invalid.")
        address = business.get("billing_address", {})
        body = (
            "WEARO TAX INVOICE\n"
            f"Invoice number: {invoice['invoice_number']}\n"
            f"Issued: {invoice['issued_at']}\n"
            f"Bill to: {business.get('legal_name', '')}\n"
            f"Billing email: {business.get('billing_email', '')}\n"
            f"Billing address: {json.dumps(address, sort_keys=True)}\n"
            f"Jurisdiction: {business.get('jurisdiction', '')}\n"
            f"Tax identifier: {business.get('tax_identifier') or 'Not provided'}\n"
            f"Subtotal: {invoice['currency']} {subtotal / 100:.2f}\n"
            f"Tax ({rate / 100:.2f}%): "
            f"{invoice['currency']} {tax_amount / 100:.2f}\n"
            f"Total: {invoice['currency']} {total / 100:.2f}\n"
        )
        return PlainTextResponse(
            body,
            headers={"Content-Disposition": 'attachment; filename="wearo-tax-invoice.txt"'},
        )

    @app.get("/api/v1/business/tenants/{tenant_id}/token-transactions.csv")
    def download_business_token_transactions(
        tenant_id: UUID,
        request: Request,
        category: TransactionCategory | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> PlainTextResponse:
        session = _authenticate_business(request, container)
        if container.wallet_transactions is None:
            raise ApiProblem(503, "TRANSACTION_HISTORY_UNAVAILABLE", "History is unavailable.")
        history = container.wallet_transactions.history(
            session.principal_id,
            tenant_id,
            category=category,
            date_from=date_from,
            date_to=date_to,
        )
        return PlainTextResponse(
            transactions_csv(history["items"]),  # type: ignore[arg-type]
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="wearo-token-transactions.csv"'},
        )

    @app.put("/api/v1/business/tenants/{tenant_id}/billing-profile")
    def update_business_billing_profile(
        tenant_id: UUID,
        body: BillingProfileBody,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        session = _authenticate_business(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.business_billing is None:
            raise ApiProblem(503, "BILLING_UNAVAILABLE", "Billing profile is unavailable.")
        return container.business_billing.update(
            session.principal_id,
            tenant_id,
            BillingProfileUpdate(
                billing_email=body.billing_email,
                billing_phone=body.billing_phone,
                legal_name=body.legal_name,
                tax_identifier=body.tax_identifier,
                billing_address=body.billing_address,
                tax_invoice_requested=body.tax_invoice_requested,
                reason=body.reason,
            ),
        )

    @app.get("/api/v1/business/tenants/{tenant_id}/memberships")
    def list_business_memberships(tenant_id: UUID, request: Request) -> dict[str, Any]:
        session = _authenticate_business(request, container)
        if container.business_membership is None:
            raise ApiProblem(503, "MEMBERSHIP_UNAVAILABLE", "Memberships are unavailable.")
        return {"items": container.business_membership.list(session.principal_id, tenant_id)}

    @app.get("/api/v1/business/tenants/{tenant_id}/owner-contacts")
    def owner_contacts(tenant_id: UUID, request: Request) -> dict[str, str]:
        session = _authenticate_business(request, container)
        if container.business_membership is None:
            raise ApiProblem(503, "MEMBERSHIP_UNAVAILABLE", "Owner contacts are unavailable.")
        return container.business_membership.owner_contacts(session.principal_id, tenant_id)

    @app.put("/api/v1/business/tenants/{tenant_id}/owner-contacts")
    def update_owner_contacts(
        tenant_id: UUID,
        body: OwnerContactUpdateBody,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, str]:
        session = _authenticate_business(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.business_membership is None:
            raise ApiProblem(503, "MEMBERSHIP_UNAVAILABLE", "Owner contacts are unavailable.")
        if container.registration_test_otp is None:
            raise ApiProblem(
                503, "CONTACT_VERIFICATION_UNAVAILABLE", "Verification is unavailable."
            )
        if not hmac.compare_digest(body.otp, container.registration_test_otp):
            raise ApiProblem(401, "INVALID_CONTACT_OTP", "Invalid contact verification code.")
        current = container.business_membership.owner_contacts(session.principal_id, tenant_id)
        return container.business_membership.update_owner_contacts(
            session.principal_id,
            tenant_id,
            email=body.value if body.channel == "email" else current["email"],
            mobile=body.value if body.channel == "mobile" else current["mobile"],
            reason=body.reason,
        )

    @app.patch("/api/v1/business/tenants/{tenant_id}/memberships/{membership_id}")
    def change_business_membership(
        tenant_id: UUID,
        membership_id: UUID,
        body: MembershipChangeBody,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, object]:
        session = _authenticate_business(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.business_membership is None:
            raise ApiProblem(503, "MEMBERSHIP_UNAVAILABLE", "Memberships are unavailable.")
        return container.business_membership.change(
            session.principal_id,
            tenant_id,
            membership_id,
            new_role=body.role,
            reason=body.reason,
        )

    @app.get("/api/v1/business/tenants/{tenant_id}/usage")
    def business_usage(
        tenant_id: UUID,
        request: Request,
        action_code: str = "TRY_ON",
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict[str, Any]:
        session = _authenticate_business(request, container)
        if container.business_platform is None or container.plan_usage is None:
            raise ApiProblem(503, "USAGE_UNAVAILABLE", "Usage is unavailable.")
        if date_from and date_to and date_from > date_to:
            raise ApiProblem(
                422, "INVALID_DATE_RANGE", "The start date must be before the end date."
            )
        reporting_today = datetime.now(BUSINESS_REPORTING_TIMEZONE).date()
        if date_to and date_to > reporting_today:
            raise ApiProblem(422, "INVALID_DATE_RANGE", "The end date cannot be after today.")
        container.business_platform.overview(session.principal_id, tenant_id)
        return asdict(
            container.plan_usage.for_account(
                session.account_id,
                tenant_id=tenant_id,
                action_code=action_code,
                date_from=date_from,
                date_to=date_to,
            )
        )

    @app.get("/api/v1/business/tenants/{tenant_id}/audience")
    def business_audience(
        tenant_id: UUID, request: Request, store_id: UUID | None = None
    ) -> dict[str, Any]:
        session = _authenticate_business(request, container)
        if container.business_platform is None or container.plan_usage is None:
            raise ApiProblem(503, "USAGE_UNAVAILABLE", "Audience metrics are unavailable.")
        container.business_platform.overview(session.principal_id, tenant_id)
        return asdict(
            container.plan_usage.audience_for_account(
                session.account_id, tenant_id, store_id=store_id
            )
        )

    @app.get("/api/v1/business/tenants/{tenant_id}/platform")
    def business_platform_context(tenant_id: UUID, request: Request) -> dict[str, Any]:
        session = _authenticate_business(request, container)
        if container.platform_identity is None:
            raise ApiProblem(503, "PLATFORM_UNAVAILABLE", "Platform context is unavailable.")
        return asdict(
            container.platform_identity.context(
                session.principal_id,
                session.account_id,
                "BUSINESS",
                tenant_id=tenant_id,
            )
        )

    @app.get("/api/v1/business/workspaces")
    def business_workspaces(request: Request) -> dict[str, Any]:
        session = _authenticate_business(request, container)
        if container.platform_identity is None:
            raise ApiProblem(503, "PLATFORM_UNAVAILABLE", "Platform context is unavailable.")
        return {
            "items": container.platform_identity.business_workspaces(
                session.principal_id, session.account_id
            )
        }

    @app.post("/api/v1/auth/email-otp/request")
    def request_otp(body: OtpRequestBody) -> dict[str, Any]:
        realm: AuthRealm = "BUSINESS" if body.purpose == "BUSINESS_SIGN_IN" else "SHOP"
        result = container.otp.request_code(body.destination, realm)
        return {
            "challenge_id": result.challenge_id,
            "expires_at": result.expires_at,
            "message": result.message,
        }

    @app.post("/api/v1/business/register", status_code=201)
    def register_business(
        body: BusinessRegistrationBody,
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> dict[str, Any]:
        if container.business_onboarding is None:
            raise ApiProblem(503, "REGISTRATION_UNAVAILABLE", "Registration is unavailable.")
        if container.registration_test_otp is None:
            raise ApiProblem(
                503,
                "REGISTRATION_VERIFICATION_UNAVAILABLE",
                "Signup verification is not configured.",
            )
        valid_email_otp = hmac.compare_digest(body.email_otp, container.registration_test_otp)
        valid_mobile_otp = hmac.compare_digest(body.mobile_otp, container.registration_test_otp)
        if not valid_email_otp or not valid_mobile_otp:
            raise ApiProblem(
                401, "INVALID_SIGNUP_OTP", "Invalid email or mobile verification code."
            )
        logo_content: bytes | None = None
        logo_mime: str | None = None
        if body.company_logo_data_url:
            try:
                header, encoded = body.company_logo_data_url.split(",", maxsplit=1)
                logo_mime = header.removeprefix("data:").split(";", maxsplit=1)[0]
                if ";base64" not in header:
                    raise ValueError
                logo_content = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error):
                raise ApiProblem(
                    422, "INVALID_COMPANY_LOGO", "Upload a valid company logo."
                ) from None
        registration = container.business_onboarding.register(
            idempotency_key=idempotency_key,
            business_name=body.business_name,
            email=body.email,
            primary_mobile=body.primary_mobile,
            operating_profile=body.operating_profile,
            jurisdiction=body.jurisdiction,
            website_url=body.website_url,
            invoice_details=InvoiceDetails(
                requested=body.tax_invoice_requested,
                legal_name=body.legal_name,
                tax_identifier=body.tax_identifier,
                billing_address=body.billing_address,
            ),
        )
        if logo_content is not None and logo_mime is not None:
            stored_logo = container.media.store_business_logo(
                registration.account_id, logo_content, logo_mime
            )
            if container.business_shop is None:
                raise ApiProblem(503, "BUSINESS_LOGO_UNAVAILABLE", "Company logo is unavailable.")
            container.business_shop.set_logo(
                registration.principal_id, registration.tenant_id, stored_logo.asset_id
            )
        recommendation = recommendation_for(body.operating_profile)
        return {
            "registration_id": registration.registration_id,
            "tenant_id": registration.tenant_id,
            "slug": registration.slug,
            "next_step": "VERIFY_EMAIL_OTP",
            "workspace": {
                "catalog_label": recommendation.catalog_label,
                "required_catalog_fields": recommendation.required_catalog_fields,
                "eligible_offerings": recommendation.eligible_offerings,
            },
        }

    @app.post("/api/v1/auth/email-otp/verify")
    def verify_otp(body: OtpVerifyBody, response: Response) -> dict[str, Any]:
        try:
            result = container.otp.verify_code(body.challenge_id, body.code)
        except OtpAuthenticationError:
            raise ApiProblem(401, "INVALID_OTP", "Invalid or expired sign-in code.") from None
        restored_from_deletion_at = None
        if result.account_status == "DELETION_PENDING":
            if container.account_lifecycle is None:
                raise ApiProblem(
                    503, "ACCOUNT_RESTORATION_UNAVAILABLE", "Account restoration is unavailable."
                )
            restored_from_deletion_at = container.account_lifecycle.restore(
                result.account_id, result.principal_id
            )
        has_person_profile = False
        if result.realm == "SHOP":
            container.profiles.restore_requested(result.account_id)
            try:
                container.profiles.require(result.account_id)
                has_person_profile = True
            except ProfileError:
                pass
        cookie_name = CONSUMER_SESSION_COOKIE if result.realm == "SHOP" else BUSINESS_SESSION_COOKIE
        response.delete_cookie(
            LEGACY_SESSION_COOKIE, path="/", secure=container.secure_cookie, httponly=True
        )
        response.set_cookie(
            cookie_name,
            result.session_token,
            max_age=EmailOtpPolicy().session_ttl.days * 86400,
            httponly=True,
            secure=container.secure_cookie,
            samesite="lax",
            path="/",
        )
        return {
            "id": result.principal_id,
            "account_id": result.account_id,
            "type": "CONSUMER" if result.realm == "SHOP" else "BUSINESS",
            "verified": True,
            "has_person_profile": has_person_profile,
            "csrf_token": result.csrf_token,
            "expires_at": result.expires_at,
            "restored_from_deletion_at": restored_from_deletion_at,
        }

    @app.post("/api/v1/auth/agent-otp/verify")
    def verify_agent_otp(body: OtpVerifyBody, response: Response) -> dict[str, Any]:
        try:
            result = container.otp.verify_code(body.challenge_id, body.code)
        except OtpAuthenticationError:
            raise ApiProblem(401, "INVALID_OTP", "Invalid or expired sign-in code.") from None
        if result.realm != "BUSINESS" or container.business_agents is None:
            raise ApiProblem(401, "INVALID_OTP", "Invalid or expired sign-in code.")
        container.business_agents.context(result.principal_id, "http://localhost")
        response.set_cookie(
            AGENT_SESSION_COOKIE,
            result.session_token,
            max_age=EmailOtpPolicy().session_ttl.days * 86400,
            httponly=True,
            secure=container.secure_cookie,
            samesite="lax",
            path="/",
        )
        return {
            "id": result.principal_id,
            "account_id": result.account_id,
            "type": "AGENT",
            "verified": True,
            "csrf_token": result.csrf_token,
            "expires_at": result.expires_at,
        }

    @app.post("/api/v1/auth/store-otp/verify")
    def verify_store_otp(body: OtpVerifyBody, response: Response) -> dict[str, Any]:
        try:
            result = container.otp.verify_code(body.challenge_id, body.code)
        except OtpAuthenticationError:
            raise ApiProblem(401, "INVALID_OTP", "Invalid or expired sign-in code.") from None
        if result.realm != "BUSINESS" or container.business_stores is None:
            raise ApiProblem(401, "INVALID_OTP", "Invalid or expired sign-in code.")
        container.business_stores.context(result.principal_id)
        response.set_cookie(
            STORE_SESSION_COOKIE,
            result.session_token,
            max_age=EmailOtpPolicy().session_ttl.days * 86400,
            httponly=True,
            secure=container.secure_cookie,
            samesite="lax",
            path="/",
        )
        return {
            "id": result.principal_id,
            "account_id": result.account_id,
            "type": "STORE_ADMIN",
            "verified": True,
            "csrf_token": result.csrf_token,
            "expires_at": result.expires_at,
        }

    @app.post("/api/v1/store/logout")
    def store_logout(
        request: Request,
        response: Response,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, bool]:
        token = request.cookies.get(STORE_SESSION_COOKIE, "")
        if token:
            container.sessions.logout(token, x_csrf_token or "")
        response.delete_cookie(
            STORE_SESSION_COOKIE,
            path="/",
            secure=container.secure_cookie,
            httponly=True,
            samesite="lax",
        )
        return {"logged_out": True}

    @app.post("/api/v1/agent/logout")
    def agent_logout(
        request: Request,
        response: Response,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, bool]:
        token = request.cookies.get(AGENT_SESSION_COOKIE, "")
        _authenticate_agent(request, container, mutation=True, csrf_token=x_csrf_token)
        container.sessions.logout(token, x_csrf_token or "")
        response.delete_cookie(
            AGENT_SESSION_COOKIE, path="/", secure=container.secure_cookie, httponly=True
        )
        return {"ok": True}

    @app.post("/api/v1/auth/logout")
    def logout(
        request: Request,
        response: Response,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, bool]:
        cookie_name, token = _authenticated_cookie(request, container, x_csrf_token)
        container.sessions.logout(
            token,
            x_csrf_token or "",
            allowed_account_statuses=frozenset({"ACTIVE", "DELETION_PENDING"}),
        )
        response.delete_cookie(cookie_name, path="/", secure=container.secure_cookie, httponly=True)
        return {"ok": True}

    @app.get("/api/v1/auth/business/csrf")
    def refresh_business_csrf(request: Request) -> dict[str, str]:
        token = request.cookies.get(BUSINESS_SESSION_COOKIE, "")
        try:
            csrf_token = container.sessions.refresh_csrf(token, expected_realm="BUSINESS")
        except SessionAuthenticationError:
            raise ApiProblem(401, "AUTHENTICATION_REQUIRED", "Authentication required.") from None
        return {"csrf_token": csrf_token}

    @app.post("/api/v1/business/tenants/{tenant_id}/catalog/collections", status_code=201)
    def create_catalog_collection(
        tenant_id: UUID,
        body: CollectionBody,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, Any]:
        session = _authenticate_business(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.catalog is None:
            raise ApiProblem(503, "CATALOG_UNAVAILABLE", "Catalog management is unavailable.")
        collection = container.catalog.create_collection(
            session.principal_id,
            CatalogCollection(
                collection_id=uuid4(),
                tenant_id=tenant_id,
                account_id=session.account_id,
                name=body.name,
                description=body.description,
                publish_state=body.publish_state,
            ),
        )
        return asdict(collection)

    @app.get("/api/v1/business/tenants/{tenant_id}/catalog/items")
    def list_catalog_items(tenant_id: UUID, request: Request) -> dict[str, Any]:
        session = _authenticate_business(request, container)
        if container.catalog is None:
            raise ApiProblem(503, "CATALOG_UNAVAILABLE", "Catalog management is unavailable.")
        return {
            "items": [
                _catalog_item_json(item)
                for item in container.catalog.store.list_items(session.principal_id, tenant_id)
            ]
        }

    @app.post("/api/v1/business/tenants/{tenant_id}/catalog/items", status_code=201)
    def create_catalog_item(
        tenant_id: UUID,
        body: CatalogItemBody,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, Any]:
        session = _authenticate_business(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.catalog is None:
            raise ApiProblem(503, "CATALOG_UNAVAILABLE", "Catalog management is unavailable.")
        item = container.catalog.create_item(
            session.principal_id,
            CatalogItem(
                item_id=uuid4(),
                tenant_id=tenant_id,
                account_id=session.account_id,
                category_id=body.category_id,
                item_code=body.item_code,
                title=body.title,
                attributes=body.attributes,
                price_minor=body.price_minor,
                currency=body.currency,
                publish_state=body.publish_state,
                collection_ids=tuple(body.collection_ids),
            ),
        )
        return _catalog_item_json(item)

    @app.put("/api/v1/business/tenants/{tenant_id}/catalog/items/{item_id}")
    def revise_catalog_item(
        tenant_id: UUID,
        item_id: UUID,
        body: CatalogItemBody,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, Any]:
        session = _authenticate_business(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.catalog is None:
            raise ApiProblem(503, "CATALOG_UNAVAILABLE", "Catalog management is unavailable.")
        item = container.catalog.revise_item(
            session.principal_id,
            CatalogItem(
                item_id=item_id,
                tenant_id=tenant_id,
                account_id=session.account_id,
                category_id=body.category_id,
                item_code=body.item_code,
                title=body.title,
                attributes=body.attributes,
                price_minor=body.price_minor,
                currency=body.currency,
                publish_state=body.publish_state,
                collection_ids=tuple(body.collection_ids),
            ),
        )
        return _catalog_item_json(item)

    @app.post("/api/v1/business/tenants/{tenant_id}/catalog/items/{item_id}/unpublish")
    def unpublish_catalog_item(
        tenant_id: UUID,
        item_id: UUID,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, Any]:
        session = _authenticate_business(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.catalog is None:
            raise ApiProblem(503, "CATALOG_UNAVAILABLE", "Catalog management is unavailable.")
        return _catalog_item_json(
            container.catalog.unpublish(session.principal_id, tenant_id, item_id)
        )

    @app.post("/api/v1/assets", status_code=201)
    async def upload_asset(
        request: Request,
        kind: Annotated[str, Form()],
        image: Annotated[UploadFile, File()],
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, Any]:
        session = _authenticate(request, container, mutation=True, csrf_token=x_csrf_token)
        content = await image.read(container.media.maximum_bytes + 1)
        stored = container.media.store(
            session.account_id,
            kind=kind,
            content=content,
            content_type=image.content_type or "",
        )
        return asdict(stored)

    @app.get("/api/v1/assets/{asset_id}")
    def read_asset(asset_id: UUID, request: Request) -> Response:
        session = _authenticate(request, container)
        content, content_type = container.media.read_owned(asset_id, session.account_id)
        return Response(content=content, media_type=content_type)

    @app.delete("/api/v1/assets/{asset_id}", status_code=202)
    def delete_asset(
        asset_id: UUID,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, bool]:
        session = _authenticate(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.retention is None:
            raise ApiProblem(503, "ASSET_DELETION_UNAVAILABLE", "Photo deletion is unavailable.")
        try:
            container.retention.request_delete(asset_id, session.account_id)
        except LifecycleError:
            raise ApiProblem(404, "ASSET_UNAVAILABLE", "Private asset is unavailable.") from None
        return {"ok": True}

    @app.post("/api/v1/consents", status_code=201)
    def create_consent(
        body: ConsentBody,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, Any]:
        session = _authenticate(request, container, mutation=True, csrf_token=x_csrf_token)
        evidence = container.consents.accept(
            account_id=session.account_id,
            actor_principal_id=session.principal_id,
            asset_id=body.subject_asset_id,
            purpose="TRY_ON",
            attestation=ConsentAttestation(
                adult_confirmed=body.adult_confirmed,
                depicted_person_permission=body.depicted_person_permission,
                transformation_approved=body.transformation_approved,
                retention_notice_acknowledged=body.retention_notice_acknowledged,
                no_training_notice_acknowledged=body.no_training_notice_acknowledged,
            ),
        )
        return {
            "id": evidence.consent_id,
            "accepted_at": evidence.accepted_at,
            "consent_version": evidence.consent_version,
            "purpose": evidence.purpose,
        }

    @app.get("/api/v1/me/person-profile")
    def get_profile(request: Request) -> dict[str, Any]:
        session = _authenticate(request, container)
        try:
            profile = container.profiles.require(session.account_id)
        except ProfileError:
            raise ApiProblem(404, "PROFILE_NOT_FOUND", "No active person profile exists.") from None
        return _profile_json(profile)

    @app.put("/api/v1/me/person-profile")
    def put_profile(
        body: ProfileBody,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, Any]:
        session = _authenticate(request, container, mutation=True, csrf_token=x_csrf_token)
        submitted_images = list(body.images)
        if not submitted_images and body.person_asset_id and body.consent_id:
            submitted_images = [
                ProfileImageBody(
                    person_asset_id=body.person_asset_id,
                    consent_id=body.consent_id,
                    photo_type="FULL_BODY",
                    label="Full body",
                    is_primary=True,
                )
            ]
        if not submitted_images:
            raise ApiProblem(
                422, "PROFILE_PHOTO_REQUIRED", "At least one profile photo is required."
            )
        images: list[ProfileImage] = []
        has_primary = any(image.is_primary for image in submitted_images)
        for index, submitted in enumerate(submitted_images):
            evidence = container.consents.require_current(
                account_id=session.account_id,
                actor_principal_id=session.principal_id,
                asset_id=submitted.person_asset_id,
                purpose="TRY_ON",
            )
            if evidence.consent_id != submitted.consent_id:
                raise ConsentError("affirmative consent is required")
            images.append(
                ProfileImage(
                    profile_image_id=uuid4(),
                    asset_id=submitted.person_asset_id,
                    consent_id=submitted.consent_id,
                    photo_type=submitted.photo_type,
                    label=submitted.label.strip(),
                    is_primary=submitted.is_primary or (not has_primary and index == 0),
                )
            )
        primary = next((image for image in images if image.is_primary), images[0])
        profile = PersonProfile(
            profile_id=uuid4(),
            account_id=session.account_id,
            principal_id=session.principal_id,
            person_asset_id=primary.asset_id,
            consent_id=primary.consent_id,
            height_cm=decimal_or_none(body.height_cm),
            weight_kg=decimal_or_none(body.weight_kg),
            status="ACTIVE",
            last_used_at=None,
            images=tuple(images),
        )
        container.profiles.save(profile)
        return _profile_json(profile)

    @app.delete("/api/v1/me/person-profile", status_code=202)
    def delete_profile(
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, bool]:
        session = _authenticate(request, container, mutation=True, csrf_token=x_csrf_token)
        try:
            profile = container.profiles.require(session.account_id)
        except ProfileError:
            raise ApiProblem(404, "PROFILE_NOT_FOUND", "No active person profile exists.") from None
        container.profiles.delete(profile.profile_id, session.account_id)
        return {"ok": True}

    @app.get("/api/v1/me/home-caption")
    def home_caption(request: Request) -> dict[str, str]:
        _authenticate(request, container)
        return {"caption": home_captions.random_caption()}

    @app.get("/api/v1/me/daily-allowance")
    @app.get("/api/v1/me/try-on-allowance")
    def try_on_allowance(request: Request) -> dict[str, Any]:
        session = _authenticate(request, container)
        current = datetime.now(UTC)
        usage = container.quota.store.get(session.account_id)
        used = usage.successful_generations if usage else 0
        ist = current.astimezone(IST)
        token_cost = None
        token_balance = 0
        purchased_try_ons_remaining = 0
        if container.plan_usage is not None:
            usage_snapshot = container.plan_usage.for_account(
                session.account_id, action_code="TRY_ON", date_from=ist.date(), date_to=ist.date()
            )
            token_balance = usage_snapshot.token_balance
            retail_price = retail_tryon_pricing.current()
            token_cost = (
                cast(int, retail_price["tokens_per_tryon"])
                if retail_price is not None
                else usage_snapshot.action_cost
            )
            if token_cost and token_cost > 0:
                purchased_try_ons_remaining = max(token_balance, 0) // token_cost
        free_remaining = (
            container.quota.maximum
            if not container.quota.limit_enabled
            else max(container.quota.maximum - used, 0)
        )
        return {
            "successful_limit": container.quota.maximum + purchased_try_ons_remaining,
            "successful_used": used,
            "remaining": free_remaining + purchased_try_ons_remaining,
            "free_remaining": free_remaining,
            "purchased_try_ons_remaining": purchased_try_ons_remaining,
            "token_balance": token_balance,
            "unlimited": not container.quota.limit_enabled,
            "grant_type": "ONE_TIME_REGISTRATION",
            "token_cost_per_try_on": token_cost,
            "tokens_consumed_today": (
                usage_snapshot.provider_total_tokens if container.plan_usage is not None else None
            ),
            "resets_at": None,
            "active_job_id": (
                usage.active_job_id if usage and container.quota.limit_enabled else None
            ),
        }

    @app.post("/api/v1/quotes", status_code=201)
    def create_quote(
        body: QuoteBody,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, Any]:
        session = _authenticate(request, container, mutation=True, csrf_token=x_csrf_token)
        if container.preflight is None:
            raise ApiProblem(
                503,
                "VISION_PROVIDER_UNAVAILABLE",
                "Image understanding is not configured for this environment.",
            )
        profile = container.profiles.require(session.account_id)
        selected_image = profile.image_for(body.person_asset_id)
        if selected_image is None:
            raise ApiProblem(
                422,
                "PROFILE_PHOTO_UNAVAILABLE",
                "Select a photo from your active profile.",
            )
        person_image, _ = container.media.read_prepared(
            selected_image.asset_id, session.account_id, "PERSON"
        )
        item_image, _ = container.media.read_prepared(
            body.item_asset_id, session.account_id, "GARMENT"
        )
        sponsored_remaining = None
        if body.sponsored_session_id is not None:
            if container.sponsored_tryons is None:
                raise ApiProblem(503, "SPONSORED_SESSION_UNAVAILABLE", "Session is unavailable.")
            sponsored = container.sponsored_tryons.status(
                body.sponsored_session_id, session.account_id, session.principal_id
            )
            sponsored_remaining = int(str(sponsored["try_ons_remaining"]))
        quote = container.preflight.quote(
            account_id=session.account_id,
            principal_id=session.principal_id,
            person_asset_id=selected_image.asset_id,
            item_asset_id=body.item_asset_id,
            person_image=person_image,
            item_image=item_image,
            bypass_free_allowance=body.sponsored_session_id is not None,
            sponsored_remaining=sponsored_remaining,
        )
        return {
            "quote_id": quote.quote_id,
            "remaining_allowance": quote.remaining_before,
            "expires_at": quote.expires_at,
            "disclaimer": quote.limitation,
        }

    @app.post("/api/v1/renders", status_code=202)
    def create_render(
        body: RenderBody,
        request: Request,
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, Any]:
        session = _authenticate(request, container, mutation=True, csrf_token=x_csrf_token)
        job = container.renders.create_job(
            quote_id=body.quote_id,
            account_id=session.account_id,
            principal_id=session.principal_id,
            idempotency_key=idempotency_key,
        )
        return _job_json(job)

    @app.get("/api/v1/renders")
    def list_renders(
        request: Request,
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=50)] = 12,
    ) -> dict[str, Any]:
        session = _authenticate(request, container)
        gallery = container.renders.list_gallery_page(
            session.account_id,
            page=page,
            page_size=page_size,
        )
        queue = container.renders.list_queue_activity(session.account_id)
        return {
            "items": [
                {
                    "result_id": item.result_id,
                    "render_id": item.render_id,
                    "result_asset_id": item.result_asset_id,
                    "created_at": item.created_at,
                    "expires_at": item.expires_at,
                }
                for item in gallery.items
            ],
            "queue": [
                {
                    "render_id": item.render_id,
                    "status": {"PENDING": "QUEUED"}.get(item.status, item.status),
                    "attempts": item.attempts,
                    "error_code": item.error_code,
                    "created_at": item.created_at,
                    "updated_at": item.updated_at,
                    "cancel_after": item.cancel_after,
                    "can_cancel": item.can_cancel,
                }
                for item in queue
            ],
            "saved_look_count": gallery.saved_look_count,
            "page": gallery.page,
            "page_size": gallery.page_size,
            "has_next": gallery.has_next,
            "retention_days": 30,
        }

    @app.delete("/api/v1/renders/{render_id}")
    def cancel_render(
        render_id: UUID,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, Any]:
        session = _authenticate(request, container, mutation=True, csrf_token=x_csrf_token)
        job = container.renders.cancel_queued(render_id, session.account_id)
        container.media.clear_progressive_preview(render_id)
        return _job_json(job)

    @app.delete("/api/v1/renders/{render_id}/result", status_code=202)
    def delete_saved_look(
        render_id: UUID,
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, bool]:
        session = _authenticate(request, container, mutation=True, csrf_token=x_csrf_token)
        if not container.renders.delete_saved_look(render_id, session.account_id):
            raise ApiProblem(404, "SAVED_LOOK_UNAVAILABLE", "Saved look is unavailable.")
        return {"ok": True}

    @app.get("/api/v1/renders/{render_id}/preview")
    def get_progressive_preview(
        render_id: UUID,
        request: Request,
        if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
    ) -> Response:
        session = _authenticate(request, container)
        job = container.renders.get_job(render_id, session.account_id)
        if job is None:
            raise ApiProblem(404, "RENDER_UNAVAILABLE", "Render is unavailable.")
        if job.status != "PROCESSING":
            return Response(status_code=204)
        partial = container.media.read_progressive_preview(render_id)
        if partial is None:
            return Response(status_code=204)
        content, content_type = partial
        etag = f'"{hashlib.sha256(content).hexdigest()}"'
        if if_none_match == etag:
            return Response(status_code=304, headers={"ETag": etag})
        return Response(content=content, media_type=content_type, headers={"ETag": etag})

    @app.get("/api/v1/renders/{render_id}")
    def get_render(render_id: UUID, request: Request) -> dict[str, Any]:
        session = _authenticate(request, container)
        job = container.renders.get_job(render_id, session.account_id)
        if job is None:
            raise ApiProblem(404, "RENDER_UNAVAILABLE", "Render is unavailable.")
        return _job_json(job)

    return app


def _smtp_provider_from_env() -> EmailDeliveryProvider:
    host = os.environ.get("WEARO_SMTP_HOST", "")
    if not host:
        return UnavailableEmailProvider()
    return SmtpEmailDeliveryProvider(
        SmtpSettings(
            host=host,
            port=int(os.environ.get("WEARO_SMTP_PORT", "587")),
            username=os.environ.get("WEARO_SMTP_USERNAME", ""),
            password=os.environ.get("WEARO_SMTP_PASSWORD", ""),
            from_address=os.environ.get("WEARO_SMTP_FROM", ""),
            use_tls=os.environ.get("WEARO_SMTP_TLS", "true").casefold() == "true",
        )
    )


def create_app_from_env() -> FastAPI:
    load_wearo_environment()
    database_url = os.environ.get("WEARO_DATABASE_URL", "")
    pepper = os.environ.get("WEARO_AUTH_PEPPER", "").encode()
    if not database_url:
        raise RuntimeError("WEARO_DATABASE_URL is required")
    if len(pepper) < 32:
        raise RuntimeError("WEARO_AUTH_PEPPER must contain at least 32 bytes")
    contact_form_token = os.environ.get("VITE_WEARO_CONTACT_FORM_TOKEN", "").encode()
    if contact_form_token and len(contact_form_token) < 32:
        raise RuntimeError("VITE_WEARO_CONTACT_FORM_TOKEN must contain at least 32 bytes")
    secure_cookie = os.environ.get("WEARO_SECURE_COOKIE", "true").casefold() == "true"
    test_auth_enabled = os.environ.get("WEARO_TEST_AUTH_ENABLED", "false").casefold() == "true"
    embedded_worker_enabled = (
        os.environ.get("WEARO_LOCAL_EMBEDDED_WORKER", "false").casefold() == "true"
    )
    free_tryon_limit_enabled = os.environ.get(
        "WEARO_FREE_TRYON_LIMIT_ENABLED",
        os.environ.get("WEARO_DAILY_LIMIT_ENABLED", "true"),
    ).casefold() == "true"
    if test_auth_enabled and secure_cookie:
        raise RuntimeError("test authentication requires WEARO_SECURE_COOKIE=false")
    if embedded_worker_enabled and not test_auth_enabled:
        raise RuntimeError("embedded worker is restricted to local test authentication")
    fixed_test_code = os.environ.get("WEARO_TEST_OTP_CODE", "1324") if test_auth_enabled else None
    engine = create_database_engine(
        database_url,
        application_name="wearo-api",
        pool_size=3,
        max_overflow=2,
    )
    drive_config = GoogleDriveConfig.from_env()
    consent_service = ConsentService(PostgresConsentStore(engine), current_version="beta-v1")
    profile_service = PersonProfileService(PostgresProfileStore(engine))
    quota_service = FreeTryOnQuotaService(
        PostgresQuotaStore(engine), limit_enabled=free_tryon_limit_enabled
    )
    analysis_endpoint = os.environ.get("WEARO_ANALYSIS_ENDPOINT", "")
    analysis_token = os.environ.get("WEARO_ANALYSIS_TOKEN", "")
    selected_provider = os.environ.get("WEARO_RENDER_PROVIDER", "GOOGLE_VERTEX").strip().upper()
    if selected_provider == "OPENAI":
        openai_api_key = os.environ.get("WEARO_OPENAI_API_KEY", "")
        route_enabled = os.environ.get(
            "WEARO_OPENAI_ENABLED", "false"
        ).casefold() == "true" and bool(openai_api_key)
    elif selected_provider == "GOOGLE_VERTEX":
        route_enabled = os.environ.get(
            "WEARO_VERTEX_ENABLED", "false"
        ).casefold() == "true" and bool(os.environ.get("WEARO_VERTEX_PROJECT_ID", ""))
    elif selected_provider == "BYTEPLUS":
        route_enabled = os.environ.get(
            "WEARO_BYTEPLUS_ENABLED", "false"
        ).casefold() == "true" and bool(os.environ.get("WEARO_BYTEPLUS_API_KEY", ""))
    else:
        raise RuntimeError("WEARO_RENDER_PROVIDER must be OPENAI, GOOGLE_VERTEX, or BYTEPLUS")
    analyzer: VisionAnalyzer | None = None
    if route_enabled and analysis_endpoint and analysis_token:
        analyzer = HttpAnalysisClient(analysis_endpoint, bearer_token=analysis_token)
    elif route_enabled and selected_provider == "OPENAI":
        analyzer = OpenAIAnalysisClient(
            api_key=openai_api_key,
            model=os.environ.get("WEARO_OPENAI_ANALYSIS_MODEL", "gpt-6-luna"),
        )
    preflight = None
    if analyzer is not None:
        preflight = BetaRenderPreflightService(
            profile_service,
            consent_service,
            ImagePreflightService(
                analyzer,
                enforce_adult_only=not test_auth_enabled,
                require_full_body=not test_auth_enabled,
                allow_jewellery=True,
            ),
            quota_service,
            PostgresTryOnRouteRegistry(engine),
            PostgresQuoteStore(engine),
        )
    blob_store = private_blob_store_from_env()
    container = ApiContainer(
        engine=engine,
        otp=EmailOtpService(
            DevelopmentPostgresOtpStore(engine)
            if test_auth_enabled
            else PostgresEmailOtpStore(engine),
            _smtp_provider_from_env(),
            EmailOtpPolicy(),
            pepper=pepper,
            fixed_test_code=fixed_test_code,
            sms_provider=(
                AwsSmsDeliveryProvider(
                    AwsSmsSettings(
                        region=os.environ.get(
                            "WEARO_SMS_AWS_REGION", os.environ.get("AWS_REGION", "")
                        ),
                        origination_identity=os.environ["WEARO_SMS_ORIGINATION_IDENTITY"],
                        configuration_set=os.environ.get("WEARO_SMS_CONFIGURATION_SET", ""),
                        entity_id=os.environ.get("WEARO_SMS_ENTITY_ID", ""),
                        template_id=os.environ.get("WEARO_SMS_TEMPLATE_ID", ""),
                        message_template=os.environ.get(
                            "WEARO_SMS_MESSAGE_TEMPLATE",
                            "Your Wearo OTP is {code}. Do not share it with anyone.",
                        ),
                    )
                )
                if os.environ.get("WEARO_SMS_ORIGINATION_IDENTITY")
                else HttpSmsDeliveryProvider(
                    os.environ["WEARO_SMS_ENDPOINT"],
                    os.environ["WEARO_SMS_API_KEY"],
                    os.environ["WEARO_SMS_SENDER"],
                )
                if os.environ.get("WEARO_SMS_ENDPOINT")
                and os.environ.get("WEARO_SMS_API_KEY")
                and os.environ.get("WEARO_SMS_SENDER")
                else None
            ),
        ),
        sessions=BrowserSessionService(
            PostgresBrowserSessionStore(engine), SessionPolicy(), pepper=pepper
        ),
        media=PostgresMediaRuntime(engine, blob_store),
        consents=consent_service,
        profiles=profile_service,
        quota=quota_service,
        renders=PostgresRenderRuntime(engine, enforce_free_allowance=free_tryon_limit_enabled),
        retention=RetentionService(PostgresLifecycleStore(engine), blob_store),
        catalog=CatalogService(PostgresCatalogStore(engine)),
        business_platform=PostgresBusinessPlatform(engine),
        plan_usage=PostgresPlanUsage(engine),
        platform_identity=PostgresPlatformIdentity(engine),
        business_onboarding=PostgresBusinessOnboarding(engine),
        business_billing=PostgresBusinessBilling(engine),
        business_membership=PostgresBusinessMembership(engine),
        wallet_billing=PostgresWalletBilling(engine),
        wallet_transactions=PostgresWalletTransactions(engine),
        topups=PostgresTopUps(
            engine,
            RazorpayPaymentGateway(
                os.environ["RAZORPAY_KEY_ID"],
                os.environ["RAZORPAY_KEY_SECRET"],
            )
            if os.environ.get("RAZORPAY_KEY_ID") and os.environ.get("RAZORPAY_KEY_SECRET")
            else HttpPaymentGateway(
                os.environ["WEARO_PAYMENT_ORDER_ENDPOINT"],
                os.environ["WEARO_PAYMENT_API_KEY"],
            )
            if os.environ.get("WEARO_PAYMENT_ORDER_ENDPOINT")
            and os.environ.get("WEARO_PAYMENT_API_KEY")
            else UnavailablePaymentGateway(),
            (
                os.environ.get("RAZORPAY_WEBHOOK_SECRET")
                or os.environ.get("WEARO_PAYMENT_WEBHOOK_SECRET", "")
            ).encode(),
            os.environ.get("RAZORPAY_KEY_SECRET", "").encode(),
        ),
        sensitive_audit=PostgresSensitiveAudit(engine),
        business_agents=PostgresBusinessAgents(engine),
        business_stores=PostgresBusinessStores(engine),
        business_shop=PostgresBusinessShop(engine),
        business_tryon_status=PostgresBusinessTryOnStatus(engine),
        business_allowances=PostgresBusinessAllowances(engine),
        communications=PostgresCommunicationsGovernance(engine),
        business_reports=PostgresBusinessReports(engine),
        support_cases=PostgresSupportCases(engine),
        support_access=PostgresSupportAccess(engine),
        sponsored_tryons=PostgresSponsoredTryOns(engine),
        account_lifecycle=PostgresAccountLifecycle(engine, blob_store),
        contact_enquiries=PostgresContactEnquiries(engine),
        contact_form_token=contact_form_token,
        registration_test_otp=fixed_test_code,
        preflight=preflight,
        secure_cookie=secure_cookie,
        google_drive=(GoogleDriveService(engine, drive_config) if drive_config else None),
    )
    object.__setattr__(
        container,
        "store_advertisements",
        PostgresStoreAdvertisements(
            engine,
            container.media,
            OpenAIAdvertisementGenerator(
                os.environ.get("WEARO_OPENAI_API_KEY", ""),
                os.environ.get("WEARO_ADVERTISEMENT_AI_MODEL", "gpt-image-2"),
            ),
            container.retention,
        ),
    )
    object.__setattr__(
        container,
        "business_smart_ads",
        PostgresBusinessSmartAds(
            engine,
            container.media,
            OpenAISmartAdGenerator(
                os.environ.get("WEARO_OPENAI_API_KEY", ""),
                os.environ.get("WEARO_SMART_AD_AI_MODEL", "gpt-image-2.6-sunburst"),
            ),
            container.retention,
        ),
    )
    embedded_worker = None
    embedded_drive_worker = None
    if embedded_worker_enabled:
        from .worker_process import build_drive_worker, build_worker

        embedded_worker = build_worker(engine=engine)
        embedded_drive_worker = build_drive_worker(engine=engine)
    return create_app(
        container,
        embedded_worker=embedded_worker,
        embedded_drive_worker=embedded_drive_worker,
    )
