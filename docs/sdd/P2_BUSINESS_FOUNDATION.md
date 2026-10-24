# P2 business foundation coverage

This document records foundational coverage for `spec-0001-01a169d8`. It does not mark every P2
feature complete. A feature is complete only after its mutations, UI, failure states, integration
tests, and any external provider behavior meet the acceptance criterion.

| Capability group | Foundation |
|---|---|
| Catalogue | Tenant-owned items, collections, prices, visibility state, and authorized APIs |
| Plans and platform identity | Versioned plan assignments, shared accounts, principals, entitlements, wallet, effective pricing, usage projections, and tenant overview |
| Audience separation | SHOP and BUSINESS session realms plus separate consumer and business route families |
| Onboarding and business type | Business profile, jurisdiction, billing/tax fields, operating profile, and profile-change requests |
| Membership and agents | Tenant memberships, revocation history, agent metadata, email/phone identities, and audit events |
| Tenant and payer isolation | Composite tenant/account foreign keys and account-scoped wallet/render records |
| Tokens | Versioned action rates, token packs, idempotent holds, append-only ledger, and recredit entry type |
| Payments and invoices | Payment orders/events, provider idempotency, invoice records, and immutable business/tax snapshots |
| Shop access | Per-tenant unique public token and branded-caption metadata for a future QR renderer |
| Allowances | Tenant policy and per-mobile usage/adjustment records |
| Governance | Immutable audit/case events, legal notice versions/acceptance, and expiring revocable support grants |

External payment confirmation, tax-document rendering, branded QR image rendering, mobile OTP
delivery, and production support tooling remain fail-closed integration work. They must not be
represented as successful until their providers and operational controls are configured.
