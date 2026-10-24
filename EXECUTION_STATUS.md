# Wearo.ai execution status

**Last updated:** 23 October 2026
**Local migration head:** `20261023_0023`
**Current state:** Simplified upload-first beta is locally implemented; external production gates
remain fail-closed.

## Completed local beta path

- WEARO-F-0020 business catalogue management now provides tenant-authorized collection creation
  and item add, revise, list, price, collection assignment, publish-state, and unpublish APIs.
  Business-realm sessions and CSRF are required for mutations; active tenant membership is checked
  in the same database transaction as each write.
- P2 business-platform foundations now cover operating profiles and change requests, billing/tax
  profile data, agent metadata, tenant and per-user allowance policy, unique shop links, versioned
  legal notices and acceptance, scoped support-access grants, and immutable invoice snapshots.
  Public effective action pricing and an authenticated tenant overview expose the common identity,
  entitlement, wallet usage, recommendation, and allowance read models.
- WEARO-F-0129 plan and allowance usage now has versioned plan assignments and normalized consumer
  and business usage APIs. Responses show used and remaining previews, token balance and usage,
  the active action rate, estimated supported previews, and the projected post-action balance. The
  business billing workspace renders these states and fails honestly when no workspace is selected.
- WEARO-F-0133 platform context APIs now resolve all enabled offerings through one principal,
  account, wallet, and billing account. Consumer and business realms receive only audience-valid
  launch routes, and the business dashboard exposes enabled products without separate identities
  or billing contexts.
- WEARO-F-0134 now enforces separate SHOP and BUSINESS session realms across distinct consumer and
  workspace navigation. Business-only screens require verified business OTP state, discover only
  active memberships through `/api/v1/business/workspaces`, and route unauthenticated visitors to
  a dedicated business sign-in experience.
- WEARO-F-0144 business self-registration atomically creates an owner identity, tenant, active
  membership, business profile, wallet, starter entitlement, allowance policy, and unique shop
  link. Registration retries are idempotent, and workspace access remains gated by verified email
  OTP rather than trusting the public registration response.
- WEARO-F-0145 keeps the default onboarding form minimal and collects legal name, billing address,
  and tax identifier only when tax-ready invoices are requested. Server validation applies
  jurisdiction-specific requirements (including GSTIN for Indian invoice requests), regardless of
  browser behavior.
- WEARO-F-0147 makes business type an explicit onboarding choice and uses one server-authoritative
  mapping for workspace catalogue labels, required item fields, and eligible offerings. The form
  previews these consequences before registration, including an honest disabled recommendation
  for jewellery generation pending its quality gate.
- WEARO-F-0148 provides owner-only billing-profile reads and CSRF-protected updates. Every change
  records immutable before/after audit evidence and a required reason; the settings UI explains
  that changes apply prospectively, while issued invoices retain their stored business and tax
  snapshots.
- WEARO-F-0149 uses verified email OTP challenges scoped to the BUSINESS realm, rejects expired,
  replayed, or attempt-exhausted codes, and lists only active tenant memberships after sign-in.
  Business sessions can now log out through the shared CSRF-protected revocation endpoint without
  being incorrectly treated as consumer sessions.
- WEARO-F-0151 adds owner-only membership history, role changes, and revocation. Changes require a
  reason and append immutable audit evidence; revocation closes the affected principal's active
  sessions in the same transaction. The last active owner cannot be revoked or demoted.
- WEARO-F-0152 centralizes tenant-scope resolution across catalogue and platform read models. Scope
  requires matching principal, tenant, and account ownership plus active account, principal,
  tenant, and membership state; missing and foreign resources receive the same opaque denial.
  Tenant records continue to use composite tenant/account foreign keys and account-scoped billing.
- WEARO-F-0153 enforces one paying context on render and ledger records: consumer accounts must not
  carry a tenant, while business accounts must carry their tenant. Ledger history now stores the
  tenant context explicitly while retaining the immutable account-scoped record.
- WEARO-F-0159 publishes action-based pricing descriptions for try-ons, image variants, 3D
  previews, and other actions. Only effective database-backed rates are marked published; missing
  rates remain visibly unpublished rather than silently inventing a charge.
- WEARO-F-0160 provides an internal exactly-once debit service. It serializes requests by account
  and idempotency key, locks an eligible wallet bucket, applies the effective price once, and
  atomically writes one immutable debit plus one itemized usage record. Retries return the original
  usage record, and no public arbitrary-debit endpoint is exposed.
- WEARO-F-0161 records eligible failed, cancelled-before-processing, and non-delivered actions as
  one immutable, idempotent RECREDIT tied to the original usage and wallet bucket. Delivered
  actions and late cancellations remain review-only, and the policy is published in the business
  billing workspace.
- WEARO-F-0165 exposes tenant-scoped token purchases, promotional credits, consumption, refunds,
  and expiry as a date/type-filterable history with opening, net-change, closing reconciliation
  totals and a CSV export. The business billing workspace presents the same filters and balances.
- WEARO-F-0170 creates hosted-gateway top-up orders from effective token-pack snapshots and credits
  purchased/promotional buckets only from authenticated confirmation webhooks. Provider events,
  credits, and receipts are idempotent; failed payments never credit a wallet, and confirmed
  payments create an immutable account-scoped receipt.
- WEARO-F-0172 atomically issues a numbered invoice for each confirmed business top-up. The invoice
  snapshots the business identity, billing address, jurisdiction, tax identifier, inclusive tax
  rate and amounts, and is available through a tenant-authorized download endpoint.
- WEARO-F-0173 accepts failed and refunded states only through signed provider events. Full refunds
  reverse the original top-up ledger credits once and void the matching invoice; mismatched amounts
  or states create an open reconciliation case without silently changing wallet balances.
- WEARO-F-0189 uses the immutable audit ledger for admin authentication, tenant membership and
  billing changes, and system wallet credits/refund reversals. Records include actor, action,
  target, timestamp, and reason; tenant audit review is restricted to active owners.
- WEARO-F-0199 requires an explicit supported operating profile at registration and maps it to the
  workspace catalog label, required catalog fields, and eligible offerings. Active owners can
  submit one audited profile-change request while the current reviewed configuration remains live.
- WEARO-F-0200 restricts prepaid checkout to operating profiles with eligible offerings and shows
  estimated try-on equivalents by offering for every pack and the current post-top-up balance.
  Estimates use published action rates and explicitly warn that actual costs vary by action.
- WEARO-F-0201 extends self-onboarding with an optional primary international mobile identity.
  Business owners can request the same protected OTP session using either their primary email or
  mobile number; production SMS delivery is replaceable and environment-configured.
- WEARO-F-0202 gives active owners tenant-scoped create, update, list, and soft-delete operations
  for named mobile agents, with normalized international numbers and immutable audit events.
- WEARO-F-0203 provides each tenant a stable token-protected public shop URL and a locally generated
  downloadable QR poster containing the business identity, Wearo.ai branding, and the caption
  “Buy confidently!”.
- WEARO-F-0204 lets active owners set the tenant default allowance and period, locate an allowance
  by normalized mobile, reset its usage period, or add try-ons. Every adjustment is tenant-scoped
  and audited.
- WEARO-F-0195 exposes active versioned notices, immutable user/tenant acceptance history, and
  per-owner email/SMS preferences for product, billing, and legal communications.
- WEARO-F-0196 gives owners a business-facing reconciliation report joining confirmed top-up cost,
  token funding, usage by staff and tenant outlet, and invoice/tax-document links, with CSV export.
- WEARO-F-0193 lets tenant members submit support, billing, and render-quality cases and track their
  state, resolution, immutable event history, and any recorded adjustment.
- WEARO-F-0190 requires active support-admin scope plus a case-bound grant lasting 5 minutes to 24
  hours. Every grant and access is audited, returned data is scope-minimized, private media content
  is excluded, and active tenant owners can inspect and revoke grants immediately.

- Email OTP has generic anti-enumeration responses, HMAC-hashed challenges, expiry, throttling,
  attempt caps and replay prevention. PostgreSQL stores only hashes; SMTP is replaceable.
- Browser sessions use hashed opaque cookies, realm checks, expiry/revocation and CSRF validation on
  every mutation.
- JPEG/PNG/WebP uploads are decoded and integrity-hashed before being placed in owner-scoped private
  storage. Private reads require the authenticated owner.
- Consent records all five approved attestations as immutable `beta-v1` evidence.
- A reusable person profile supports full-body and close-up photos, per-try-on photo selection,
  optional height/weight visual guidance, replacement and immediate access revocation with
  deletion scheduled within 24 hours.
- Product and accepted result media expire after 30 days. The scheduler claims due records safely,
  deletes blobs and retains only lifecycle tombstones.
- The free allowance permits three successful generations per account per IST day and only one
  active generation. Failures do not consume allowance.
- Quotes are non-billable and expire after ten minutes. Jewellery and unsupported/ambiguous items
  fail before provider invocation.
- Render creation, idempotency, durable queueing, exclusive leases, expired-lease recovery,
  terminal failure release, result publication and successful quota settlement are transactional.
- The production worker assembly supports a selected OpenAI Images edit model or the retained
  Vertex route plus a scoped HTTPS preflight/quality analyzer; missing configuration fails closed
  before quote creation. Worker jobs verify the persisted provider/model/region before sending
  either customer image to a provider.
- The FastAPI runtime exposes health, OTP, private upload/read, consent, profile, allowance, quote,
  render and logout endpoints. The Shop UI is wired to the same-origin API and lets users select a
  saved profile photo for each try-on.
- Operations commands cover expired work recovery and retention purge. Local startup instructions
  are in `docs/development/RUNNING_BETA.md`.

## Validation evidence

| Gate | Result |
|---|---|
| Python formatting/lint/strict typing | PASS across 79 source files |
| Python unit tests | 71 passed |
| Live PostgreSQL integration tests | 37 passed using psycopg 3 against `127.0.0.1:55432` |
| Web tests and Vite production build | 4 passed; build completed |
| OpenAPI and generated TypeScript | PASS: 57 paths, 65 operations, 48 schemas |
| SDD backlog mapping | PASS: 90/90 requirements and 36/36 QA cases mapped |
| CI policy | PASS |
| Migration policy | PASS: 15 revisions |
| Latest migration apply | PASS: `0014 → 0015`; current is head |
| Python dependency audit | No known vulnerabilities |
| Node high-severity audit gate | PASS; one low-severity advisory remains |

## External release blockers

These cannot be truthfully completed from the local repository and are intentionally not replaced
with mocks in the customer path:

1. Configure a verified SMTP sender and production secret storage, then run delivery/abuse tests.
2. Supply the selected render credential (OpenAI API key for the new default path, or Google
   Vertex credentials for the retained alternative) and record the applicable terms/DPA, image
   data controls and privacy approval.
3. Deploy/approve and configure the real image-understanding and quality service. Until then quote
   creation returns `VISION_PROVIDER_UNAVAILABLE` and no customer image reaches a provider.
4. Run the rights-cleared 50-case golden evaluation, achieve at least 90% acceptance with no hard
   failure, and record Product/AI approval. Jewellery remains disabled.
5. Replace the single-host private filesystem backend with the production encrypted managed object
   store and prove lifecycle deletion, backup and restore behavior.
6. Execute staging browser/accessibility, cross-account isolation, load/timeout, penetration,
   observability/alert and rollback rehearsals and obtain final Security/Privacy go-live approval.

The detailed checklist is maintained in `docs/release/BETA_RELEASE_GATES.md`.

## Safety state

- `.env` and private storage are ignored by Git; `.env.example` contains placeholders only.
- No credential is present in tracked source or documentation.
- No production database or real AI provider was contacted.
- Commercial wallet/payment/invoice and jewellery launch paths remain outside the simplified free
  beta and are not represented as complete.
