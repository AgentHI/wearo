# Wearo.ai MVP — Frontend specification

**wearo.ai | Engineering working spec v1.0 — 17 Oct 2026**

> This is an extracted developer view from the canonical `Wearo_MVP_Implementation_Spec_v1.0.md`; source is the uploaded MVP v1.0 and brand PDF. Do not add product WR IDs or expand FULL/BOUNDED pilot coverage. Proposed technology/contracts need approval under DEC-01..DEC-10.

## 1. Executive implementation contract

### 1.1 What the team will build

A single responsive web platform with three authenticated experiences and one optional guest storefront:

| Experience | Primary form factor | Identity and audience | Pilot outcome |
|---|---|---|---|
| **Wearo Shop** | Phone-friendly web | Guest entry; verified consumer email OTP before generation or saved content during the simple beta | Reusable person profile + uploaded wearable item -> consent -> allowance -> AI preview -> compare, zoom, feedback and repeat |
| **Wearo Business** | Desktop / tablet | Merchant owner email OTP | One boutique/jeweller tenant, up to 10–30 curated active pilot items, owner wallet, invoices, usage, one associate role |
| **Wearo Mirror-lite** | Tablet / desktop browser | Tenant associate email OTP; customer is a temporary, consented guest | Staff-guided garment or jewellery preview -> exact-item enquiry or finish and clear session |
| **Wearo Admin** | Desktop web | Separate administrator credentials + mandatory MFA | Tenant/entitlement, packs/pricing, approved model routing, audit/usage, dispute and operations |

**Shared platform:** One authentication policy layer, tenant/owner authorization, catalogue, private image workflow, render orchestration, prepaid **Wearo Token** ledger, payment confirmation, and auditable administration. Wearo Tokens are *published retail billing units*, not provider API input/output tokens.

### 1.2 Ship / do not ship boundary

**Ship:** guest exploration; phone OTP; email OTP; admin password+MFA; photo capture/upload with guidance and validation; affirmative consent; supported garment category configuration; one adult neutral mannequin; merchant photo/catalogue; static single-result rendering; original/product comparison and zoom; regeneration as separately disclosed billable action; basic feedback; necklaces/pendants and earrings behind fidelity gate; store sessions; opted-in enquiries; two token pack sizes; Indian gateway payment; business tax invoice; wallet histories/recredits; essential B2B metrics; admin model and tenant controls; deletion/support mechanisms.

**Do not ship:** native apps, 3D avatars, true fit measurement, AR/live video, stock sync, QR jewellery scanning, rings/bangles, custom blouse construction, tailor-ready Studio specs, inventory/branch hierarchy, AI wardrobe stylist, booking engine, subscription, provider fine-tuning UI, multi-country billing or public status portal.

**Category rollout is gated:** Wave 1 = approved clothing (initial Western shirts / T-shirts / tops and any individually approved kurta or curated saree slice). Wave 2 = approved necklace/pendant/earring products only if jewellery fidelity gate passes. The MVP PDF calls for selecting exactly 2–3 garment categories before launch; initial candidates are *not automatically approved*.

### 1.3 Normative and proposed language

- **SOURCE** = explicit function or boundary in either uploaded PDF; cited by original `WR-###`.
- **SPEC** = how engineering proposes to implement SOURCE, including interfaces and acceptance checks; changeable without renumbering WR.
- **DEC-XX** = unresolved product/operator decision that must be filled before production pilot. Values shown as examples are placeholders, **not commercial commitments**.
- **Must** in an implementation contract describes a proposed team-build condition. It does not upgrade a deferred source item into the MVP.

## 3. Actors, security contexts and permissions

### 3.1 Principal types

| Principal | Context | Allowed | Never allowed |
|---|---|---|---|
| Guest | Anonymous browser, no private account | Discover enabled items, mannequin preview of *catalog samples* if policy allows, inspect limitations | Access wallet, purchased tokens, persistent personal results or paid render |
| Consumer | `principal_type=consumer` + verified phone | Own photo/results, pay/recredit, own wallet, delete/report, own enquiries | Read tenant inventory administration or others' photos |
| Merchant owner | `principal_type=business` + tenant + verified email | Manage own catalog and staff, top up tenant wallet, view invoices/usage, staff sessions as permitted | Select arbitrary paying tenant, access other tenants or admin APIs |
| Merchant associate | Tenant membership + verified email | View published tenant catalog, create/end guest sessions, render with tenant wallet, create consented enquiries | Change token packs/merchant billing, invite users, export other guest photos |
| Platform admin | Dedicated admin identity + MFA + scoped permissions | Manage tenant status, pricing/model configuration, reviewed cases and aggregate operations | Default access to consumer raw photos; ordinary store roles or wallet use |
| Async worker | Service identity + per-job scoped access | Read permitted job assets; write result; report status/cost | Read arbitrary tenants or publish assets without finalization |

### 3.2 Authorization invariant

Every resource request resolves an authenticated actor, **effective paying account**, and `tenant_id` or `consumer_id` on the server. Client-supplied `tenant_id`, `wallet_id` or `owner_id` is **never sufficient** authorization. Foreign IDs return a generic `404` or `403` without confirming private object existence. No cross-tenant query, download, signed URL, feedback, payment callback or object key access is acceptable (`WR-126`, `WR-152`, `WR-153`).

Use short-lived HTTP-only secure browser sessions and CSRF protection on cookie-auth mutations. OTP: hashed one-time challenges, max attempts, expiry, resend cap, destination rate limits and generic responses to prevent account enumeration. Admin: independent realm and MFA, no bypass via merchant auth.

### 3.3 Business wallet spending delegation

An associate spends the tenant wallet **only** on authorized in-store render actions. Ownership, pack pricing, invoices, staff invitations and model controls are owner/admin privileges. Each render records both `performed_by_principal_id` and `charged_account_id`.

## 4. User journeys as executable contracts

### FE-01 / Consumer photo try-on (`WR-001…WR-043`, selected only)

**Approved upload-first simplification (PD-01 / DEC-01 / DEC-02, effective 2026-10-17):** the primary consumer path does not require a pre-listed catalogue item or a user-selected category. A signed-in user creates a reusable, consented person profile and then supplies a wearable-item image, including apparel or jewellery. Existing merchant catalogue flows remain separate. The service classifies and routes the supplied item internally, asks for clarification when multiple or ambiguous items are detected, and rejects unsupported input before quota use. During the beta, detected jewellery returns “not yet supported” until a separate jewellery-capable provider passes the fidelity gate; materially altered designs must never be delivered. Profile photo, face and optional height/weight information guide visual identity and approximate proportions only; they are not measurements and must never produce sizing or fit claims. The profile remains reusable until user deletion or expiry under the approved DEC-04 policy.

**Approved free-beta economics (PD-02 / DEC-03, effective 2026-10-17):** each verified user may receive three successful generations per calendar day. Rejected preflight inputs and failed generations do not consume the allowance. Show remaining daily allowance before confirmation. Token balances, paid packs and payment checkout remain outside the simple beta flow while their existing implementation/backlog is preserved for later commercial approval.

**Approved beta identity and payment scope (PD-03 / DEC-05, effective 2026-10-17):** consumers authenticate with verified email OTP. Phone/SMS OTP, payment checkout, GST handling and tax invoices are inactive in the simple beta; their existing requirements and implementation remain preserved for a separately approved commercial release. Email OTP must be hashed, short-lived, single-use, rate-limited and enumeration-resistant.

1. Landing/Discover (guest): present the upload-first try-on entry point; merchant catalogue discovery, when enabled separately, retains retailer-versus-concept attribution.
2. Person profile: after authentication, capture/upload the user's photo with framing, lighting and one-person guidance; optionally accept height and weight as generation guidance. Obtain affirmative consent, save the private profile for reuse, and provide a prominent delete-profile control. Do not charge invalid input.
3. Consent: check affirmative permission to transform photo, adult/age policy and retention/training notice. Record `consent_version`, timestamp, actor and intended purpose; no default training use.
4. Product input and allowance: accept a wearable-item image without requiring a pre-listed item or category selection; detect and route its type internally, request clarification for an ambiguous or multi-item image, then show the remaining free-beta daily allowance, limitations and regeneration rule. Do not invent product identity or seller details. Require a verified user before generation.
5. Preflight: upload securely, validate person profile and item image, consent, entitlement and detected capability; issue a price-locked quote/confirmation; fail before reservation for unsupported, ambiguous or invalid input.
6. Render: reserve one daily allowance slot atomically and enqueue; show pending/processing; poll status; no duplicate request on refresh. On success deliver a labelled AI preview and consume one successful-generation allowance. On rejection or failure release the slot without consuming allowance, explain correction and permit retry.
7. Result: show source photo **and** original item alongside generated result, zoom, approximate/non-fit warning, thumbs-up/down reasons, report/remove/delete, and optional repeat with newly disclosed charge.
8. Traction: capture delivered-preview, repeated-preview, first real-money pack purchase and usable feedback with no unnecessary personal content in event payloads.

**Definition of done:** Real consumer can complete this on a phone browser; the same render request cannot charge twice, and another consumer cannot open its original or result.

### FE-02 / Merchant owner onboarding and administration (`WR-144…WR-153`, etc.)

1. Choose **boutique** or **gold jeweller**; verify business email via OTP.
2. Create one `business` tenant; capture legal/trade name, contact, invoicing address, state and optional GSTIN if applicable; show summary at purchase.
3. Add 10–30 curated catalog items with original image, exact item code, category, variant/known attributes, and optional exact seller product URL; owners can unpublish items.
4. Invite or revoke **associate** by verified email. Owner buys standard/discounted pack; signed gateway webhook credits only own wallet once; download valid invoice after confirmation.
5. View wallet transactions, render volume, basic item interest and opted-in enquiry counts, with no branch-level analytics.

**Definition of done:** New merchant can self-onboard, upload an existing product, fund wallet, invite an associate and view a traceable usage/invoice record.

### FE-03 / Staff-assisted Mirror-lite (`WR-075…WR-096`, selected only)

1. Associate opens `/mirror`, sees tenant brand/categorized collection, starts fresh session on tablet or desktop.
2. Customer consents on screen, with explicit adult/permission and retention notice. Capture/uploads own portrait (not an identity account); allow neutral mannequin if policy permits.
3. Choose only approved inventory item: boutique existing garment or necklace/pendant/earring. If jewellery category disabled, it must not be selectable.
4. See source item, cost and current tenant balance; authorized associate confirms. Show render progress, original photo, AI result, full seller item identifiers, approximate size warning, compare and zoom.
5. For enquiry, **customer affirmatively chooses** to share contact and exact selected item. Associate submits; UI names receiving merchant and follow-up channel. No appointment scheduling or real-time stock assurance.
6. Press **Finish / Clear for next customer**; immediately revoke temporary access, remove session URLs/state from browser, and enqueue object cleanup per retention policy. Idle timeout must do the same without staff action.

**Definition of done:** The next shopper cannot recover the previous shopper's photo/result through back navigation, reload, cached storage or old signed links. Backend scope/TTL always enforces revocation.

### FE-04 / Admin operational loop (`WR-175…WR-193`, selected only)

1. Admin signs in separately (username/password + MFA); role-specific dashboard includes user/tenant counts, submitted/succeeded/failed renders, purchased/spent tokens, revenue, model cost and B2C/B2B filters.
2. Admin activates/suspends tenant/offering with logged reason, manages pack prices/discount effective dates and approved renderer versions by use case.
3. Disabling a model or category immediately blocks **new** jobs/quotes; in-flight jobs finish or are cancelled/recredited under published policy.
4. Review job failures, anonymous feedback aggregates, unusual spend/OTP rate alerts, customer requests and payment discrepancy statuses; log any manual correction to the append-only financial record.

## 5. Frontend specification: application information architecture

### 5.1 Routes, views and guard conditions

| FE view / route | Form | Required guard / important behavior | Source IDs |
|---|---|---|---|
| `FE-S01 /` and `/shop` | Phone-first, guest allowed | Visible category gate, retailer-vs-concept labels, premium plum CTA | WR-001,002,011,021,043 |
| `FE-S02 /shop/item/:itemId` | Phone | Original product image, category/variant and exact seller link only when verified | WR-013,017,020,110 |
| `FE-S03 /shop/photo` | Phone | Camera/gallery, adult neutral mannequin, framing; validate before paid confirmation | WR-003,004,007,125 |
| `FE-S04 /shop/consent` | Phone | Mandatory affirmative checkbox/action, permission and storage/training notice | WR-006,124,130 |
| `FE-S05 /auth/phone` | Phone | OTP expiry/resend/retry; only before paid or persistent content | WR-140,141,142 |
| `FE-S06 /shop/confirm` | Phone | Action, item, exact tokens, wallet balance, limitations, new-charge consent | WR-027,129,158,159 |
| `FE-S07 /shop/jobs/:id` | Phone | Poll progress, recover/retry, accessible live status; never auto-buy twice | WR-040,128,191 |
| `FE-S08 /shop/results/:id` | Phone | AI label, comparison, zoom, feedback/report, delete and new price for re-render | WR-010,025–030,039,120–122,127 |
| `FE-S09 /wallet` | Phone | Balance, promo label/expiry, top-up, debits and recredits | WR-157–167 |
| `FE-S10 /wallet/top-up` | Phone | Standard and bulk discount pack, checkout and receipt; authenticated | WR-162,163,170,171 |
| `FE-S11 /business/register` | Desktop/tablet | Business type, required invoice data, email OTP and creation | WR-144–149 |
| `FE-S12 /business` | Desktop/tablet | Tenant KPIs, wallet balance, usage/enquiries | WR-134,096,129 |
| `FE-S13 /business/catalog` | Desktop/tablet | Owner add/update/unpublish 10–30 validated records | WR-017,020,075,083 |
| `FE-S14 /business/staff` | Desktop | Owner-only invite/revoke associate | WR-150 |
| `FE-S15 /business/credits` | Desktop/tablet | Owner top-up, history and business invoice downloads | WR-157–173 |
| `FE-S16 /business/enquiries` | Desktop/tablet | Consented item-linked enquiry summary; no direct guest photo by default | WR-084,092,113,119 |
| `FE-S17 /mirror` | Tablet-first | Tenant associate, catalog, fresh session, prominent reset | WR-086,089,093 |
| `FE-S18 /mirror/session/:id` | Tablet-first | Linear capture, consent, item, render, compare, enquiry, finish | WR-075–096 |
| `FE-S19 /admin/login` | Desktop | Separate login + mandatory MFA | WR-175 |
| `FE-S20 /admin` | Desktop | B2C/B2B period metrics and cost | WR-176 |
| `FE-S21 /admin/tenants` | Desktop | Entitlement status, reasoned activate/suspend, audit | WR-177,189 |
| `FE-S22 /admin/packs` | Desktop | Effective-dated published pack / pricing controls | WR-178 |
| `FE-S23 /admin/models` | Desktop | Approved renderer versions, capability & category on/off | WR-181,182 |
| `FE-S24 /admin/operations` | Desktop | Render/payment problems, support/data requests, protected audit | WR-188,189,192,193 |

Route names are **proposed implementation paths**, not source-prescribed URLs. No link may expose unentitled or unsupported features merely because the route exists.

### 5.2 Design system: exact source colours

| Design token | Hex | Required use |
|---|---|---|
| `brand.plum` | `#3B1746` | Primary action, main navigation, brand emphasis |
| `brand.aubergine` | `#251129` | Premium dark surfaces |
| `brand.gold` | `#C9A46B` | Sparse premium highlights, jewellery accents, star motifs |
| `canvas.ivory` | `#FAF7F2` | Light Shop and Business primary canvas |
| `surface.white` | `#FFFFFF` | Cards, text inputs |
| `state.lilac` | `#F1EAF1` | Selected cards/options; *always* also icon/text state |
| `ink.charcoal` | `#261C2A` | Main heading and reading text |
| `ink.mauve` | `#716775` | Secondary text |
| `border.mauve` | `#E8DFE7` | Thin separators and input borders |
| `dark.midnight` | `#190E1C` | Mirror-lite base canvas |
| `dark.surface` | `#2D1C32` | Mirror-lite panel surface |
| `ink.deepGold` | `#866037` | Readable small gold-toned copy on pale surfaces |

**Source colour balance for B2C** (guideline rather than screen-by-screen enforcement): 60% ivory, 25% plum, 10% gold, 5% lilac; product/photo imagery remains dominant. **Screen profile:** Shop + Business/Admin = light/neutral; Mirror-lite = cinematic dark/plum with contrasting source/preview. Do **not** use low-contrast champagne gold as small text on ivory. On plum primary buttons use white text. Use gold on dark plum for high-value accents, not every action.

**Proposed (not source-prescribed) spacing/shape breakpoints:** 4/8/12/16/24/32 px spacing steps; rounded cards 12–16 px; 44 px minimum tap target; phone up to 767 px; tablet 768–1199 px; desktop >= 1200 px. Use a consistent readable system sans font pending typography sign-off. Check WCAG 2.2 AA contrast, keyboard sequence and screen reader labeling on all money/consent steps.

### 5.3 Component contracts

| Component | Props / emitted events | Required states |
|---|---|---|
| `CategoryGrid` | enabled categories, onSelect | loading, visible, disabled-with-reason, empty |
| `ProductSourceCard` | id, type, image, seller, code, variant, item URL | original vs concept, no fabricated stock badge |
| `PersonImageUploader` | temporary upload intent, file, onValidated | camera/gallery, size/type error, pose error, processing |
| `ConsentCapture` | consent version, purpose, store-session flag | unchecked, accepted, validation error; never prechecked |
| `TokenQuoteCard` | action, quoteId, price, balance, expiration, onApprove | enough, insufficient/top-up, expired/reprice, unavailable |
| `RenderProgress` | renderId/status, polling/backoff | queued, processing, quality-check, delivered, failed |
| `PreviewComparison` | original person, item source, result, label, limitation | side-by-side, mobile slider/toggle, zoom, missing/private asset |
| `ResultFeedback` | resultId, positive/reason, report/delete | unsent, sent, moderation, delete confirmation |
| `BusinessCatalogEditor` | item meta, image intent, active flag | draft, quality pending, approved, disabled, unpublished |
| `MerchantSessionShell` | sessionId, timeout, finish, consent | fresh, active, cleared, timed-out; blocks stale back |
| `WalletSummary` | purchased, promo, reserved, spendable, history | refresh, pending provider, credited, reversal, discrepancy |
| `AdminModelSelector` | category, approved versions, status | active, disabled, changed with audited reason |

### 5.4 Screen-level UI acceptance and privacy

**Consumer:** At width 360 px, the complete consent, price and primary action are reachable without sideways scrolling. Try-on CTA prominent in plum; photo/source image each gets a meaningful accessible label; high-contrast error text plus icon; mobile camera permission denied falls back to gallery.

**Mirror-lite:** At tablet landscape width, preview uses largest available area. Collapsible collection side rail, large image stage, bottom compare/enquiry/finish controls. The **Finish / Clear** control remains visible, with confirmation and automatic idle expiry. Avoid browser persistence of guest raw photos (no localStorage, indexedDB, durable cache, analytics image payloads). `Cache-Control: no-store` for session/private responses.

**Business/Admin:** Neutral compact tables, clear filters and obvious financial difference between **available**, **reserved** and **used** tokens. Counts shown in the brand PDF's example dashboard are **illustrative**, not seed data or expected business metrics.

**Accessibility:** Keyboardable dialogs, focus return, explicit error announcements, logical heading order, zoom to 200%, inputs with labels rather than placeholders only, visible token price in text (not color) and empty/error/recovery screens.

### 5.5 Frontend async and error policy

- Only render calls explicitly triggered by `Approve` may carry idempotency keys; if network disconnects, use the same key and check existing job instead of submitting again.
- When user navigates away, a processing job remains associated with its paying account; UI can resume via `GET /renders/{id}`. User logout removes local sensitive references.
- Failed input check: show guidance and no debit. Provider/model failure after reservation: show `tokens restored / not charged` **only after authoritative wallet result**, never preemptively.
- Payment redirect return is **not** payment proof; show “Verifying payment” until backend webhook+verification completes.
- Transient API retries: exponential backoff on GET; no auto-retry of non-idempotent POST unless `Idempotency-Key` reused.
- Anonymous events exclude image bytes, exact phone/email, OTP, face data and unrestricted image links.

## 11. Contract-first test scenarios (Given / When / Then)

| QA ID | Given / When | Then / required proof | Trace |
|---|---|---|---|
| QA-001 | Guest opens mobile Shop and picks enabled product | Can browse; paid render prompts phone OTP; no account data exposed | WR-001,002,142 |
| QA-002 | Upload poor-light/cropped/multi-person image | Actionable rejection **before** any reservation/debit | WR-003,004 |
| QA-003 | Personal image, consent unchecked or permission false | Render quote rejected; no provider invocation | WR-006,124,125 |
| QA-004 | Unsupported garment or disabled jewellery category | Not offered/charged; safe reason displayed | WR-014,015,043,075,076 |
| QA-005 | Verified shopper approves fixed-price quote | Single render status chain, original + AI label + fit limitation + zoom | WR-024–030,120,121 |
| QA-006 | Same render POST retried 10 times with identical key | One canonical job, one reservation, one final debit | WR-160 |
| QA-007 | Two associates draw on the same low-balance tenant wallet | At most available amount reserved; no negative balance/double spend | WR-153,157,160 |
| QA-008 | Model timeout, invalid output or job failure | No net token cost, safe retry and refund/release visible | WR-040,128,161 |
| QA-009 | Duplicate/late gateway webhooks arrive | Tokens credited exactly once after verification; failed payment never credits | WR-162,170,173 |
| QA-010 | Buyer selects standard vs bulk pack | Base, savings, total, tokens and purchase confirmation match immutable price version | WR-158,159,163 |
| QA-011 | Business owner onboards in India | Email OTP, one tenant, optional GSTIN, proper issued invoice available | WR-144–149,172 |
| QA-012 | Owner revokes associate | Associate immediately loses merchant session/catalog spend; owner retains control | WR-150,152 |
| QA-013 | Tenant A guesses tenant B's item/render/wallet/invoice IDs | No content, balance, image URL, usage or tenant existence leaked | WR-126,152,153,187 |
| QA-014 | Showroom customer finishes; next customer uses Back/Reload/old URL | Prior photo/result hidden and unresolvable, cleanup scheduled | WR-086,089,093,123 |
| QA-015 | Customer opts in enquiry with exact item and phone | Enquiry shown to correct merchant; receipt names item and next follow-up | WR-084,092,113,119 |
| QA-016 | User reports/removes preview | Report tied to result; private asset unavailable on deletion; complaint tracked | WR-122,127,188,193 |
| QA-017 | Admin toggles category/model, pack price and tenant with reason | Only approved routes used for new jobs, effective dates honored, audit written | WR-177,178,181,182,189 |
| QA-018 | Consumer tries using merchant owner credentials in admin login | Denied; admin password+MFA separate; audit and throttling operate | WR-175,192 |
| QA-019 | Product has no verified seller URL | Enquiry, not invented Buy button/checkout; source item always accessible | WR-017,079,110 |
| QA-020 | Jewellery result fabricates stones/changes shape in quality review | Reject/not release affected output; disable item/category pending fidelity review | WR-026,076,083 |
| QA-021 | Guest consented image reaches TTL / owner deletes | Revoke access immediately, remove object asynchronously, preserve legally necessary audit only | WR-122,123,130,187,188 |
| QA-022 | B2C promo credit issued once | Purchased/promo balances and validity distinct; no duplicate promo on repeat OTP | WR-165,167 |
| QA-023 | Admin reports use B2C/B2B filter and date range | Totals reconcile with underlying jobs/payments/ledger, no real customer photo | WR-096,176 |
| QA-024 | Long provider outage during quoted/held render | User sees progress -> failure and funds restored, no orphaned reservation | WR-161,191 |
| QA-025 | UI tested in phone/tablet/desktop and keyboard/screenreader | Main actions accessible; selection/errors not color-only; dark Mirror contrast checked | WR-011,135 |
| QA-026 | Customer chooses neutral adult mannequin instead of own photo | Renderable only for supported categories; no avatar customization or personal consent bypass | WR-007 |
| QA-027 | Signed-in customer opens/deletes recent results | Only own delivered recent previews listed and removed; no mood boards | WR-010 |
| QA-028 | User uploads one valid product reference instead of SKU | Product clearly labelled as nonmerchant concept, supported category only | WR-013 |
| QA-029 | Merchant owner adds, updates, unpublishes 10–30 real pilot products | Published display follows tenant ownership, no inventory/branch sync | WR-020 |
| QA-030 | Shop displays retailer-listed product beside AI render | Source product and generated illustration unmistakably distinguished | WR-021 |
| QA-031 | Shopper presses thumbs down with wrong-color reason | Feedback attached to correct render without exposing private result | WR-039 |
| QA-032 | Jewellery item with merchant dimensions visualized | UI says approximate dimensions, never asserts calibrated scale or gold weight | WR-077 |
| QA-033 | Wallet has promo/paid balance and insufficient funds | Price, spendable balance and top-up guidance visible; no negative spend | WR-129,166 |
| QA-034 | Account switches among entitled offerings/form factors | One core billing/identity, separate B2C/B2B shells, disabled features hidden and blocked | WR-133,134,136 |
| QA-035 | OTP expired, guessed, resent too frequently or used twice | Login fails safely, limits enforced, legitimate new challenge can verify | WR-140,141 |
| QA-036 | Payment checkout offers provider-enabled India rails | Actual enabled UPI/card options visible; unavailable rails not falsely promised | WR-171 |

**Quality gate for all tests:** unit test, API contract, integration against test PostgreSQL/queue/store, browser E2E, negative authorization tests, and representative photo/golden evaluation. Payment provider sandbox != completed live payment approval.

## 12. Spec-driven delivery sequence, source control and handoffs

### 12.1 Work breakdown with dependencies

| Sprint slice | Frontend deliverable | Backend deliverable | Evidence / unlock |
|---|---|---|---|
| **S0 / Spec freeze** | Approved route map, brand tokens, wireframes and error states | OpenAPI baseline, schema migrations, security decisions, gateway/provider shortlist | DEC choices recorded, 90 trace rows mapped; no coding from unresolved semantics |
| **S1 / Secure foundation** | Shells, phone/email OTP, business onboarding, admin MFA | Principals, tenants, RBAC, OTP/rate limiting, audit and private upload pipeline | QA-001, 002, 003, 011, 012, 013, 018 |
| **S2 / Catalog and single render** | Consumer selection, upload, consent, quote, polling, comparison | Catalog, enabled categories, model registry/adapter, render queue and quality gate | QA-004, 005, 019, 020, 025 |
| **S3 / Money and trust** | Pack checkout, balance/history, result report/delete/retry | Ledger, holds, provider callbacks, invoicing, retention, refunds, support | QA-006–010, 016, 021, 022, 024 |
| **S4 / Merchant pilot** | Owner catalog/usage, Mirror-lite guided tablet flow, enquiries | Temporary guest session, tenant wallet delegation, enquiry/aggregate analytics | QA-014, 015, 023; boutique pilot enabled |
| **S5 / Jewellery gate & pilot** | Jewellery item details, source/preview controls | Golden dataset gate, category enablement, admin monitoring and cost metrics | Verified jewellery fidelity or vertical stays disabled |

**Critical path:** auth & tenancy -> private uploads/consent -> approved category/model + catalog -> quotes -> exactly-once ledger & payment -> successful render and replay safety -> guest showroom -> pilot acceptance. A mocked render can be used for contract/UI tests but **cannot** count as passing real visual fidelity/traction.

### 12.2 Story / PR spec template

Every coding story carries: `Story ID`, **source WR-IDs**, `FULL|BOUNDED treatment`, impacted FE-S/BE/API modules, typed input/output contract, behavior transitions, threat/PII review, migration impact, observability, test IDs, non-goals, review screenshots (3 breakpoints if UI), and precise acceptance proof. PR is not complete if a changed API is not reflected in OpenAPI or if a selected WR acceptance test is missing.

**Example:** `STORY-RENDER-001` -> `WR-024,027,028,128,158,160,161` -> quote/create/status/result interfaces -> idempotent reservation and settle -> result source+AI label -> QA-005/006/008 -> reject unsupported items before debit.

### 12.3 Release environment and pipeline

`local` -> `test` -> `staging` -> `pilot-prod`. CI: lint/typecheck, unit tests, OpenAPI lint and generated client drift, schema migration rehearsal, contract tests, SAST/dependency scan, tenant authorization tests, payment replay concurrency test, E2E responsive visual snapshots, golden-set evaluation summary. CD uses masked secrets and staggered deploy: migrate compatible DB -> deploy API/worker -> web -> smoke -> enable via entitlement flags. Every model route and token price change has an audit and safe rollback.

## 13. Release acceptance checklist and decisions

### 13.1 Mandatory pilot release gates

- **Coverage:** All 90 selected WR records in the trace matrix are assigned an owner and a pass/fail test. FULL retains master expected outcome; BOUNDED satisfies **only** the limited pilot treatment; all 107 unselected WR remain out of release scope.
- **Consumer end-to-end:** an adult user can get a legitimate delivered paid render on mobile; original person/item + AI disclosure, feedback, recover and delete work.
- **Merchant end-to-end:** real merchant can self-register, verify, upload genuine inventory, invite associate, buy pack, view invoice/usage; associate runs private session and consented enquiry, clears next guest.
- **Money:** duplicate gateway callbacks, concurrent wallet use, refresh, retries and failures create no unexplained double charge, orphan hold or wrong account credit.
- **Trust:** adult/permission policy, explicit consent, tenant isolation, data retention/deletion and no default model training are verified; admin password+MFA is separate.
- **Quality:** category-specific golden review passes; materially fabricated jewellery or garment and repeated face distortion stop that category; no false exact fit/weight/stock claims.
- **Traction:** B2C paid conversion and merchant paid continuation by vertical are measurable from real payments; no conversion claim from free credits.

### 13.2 Required decisions before engineers freeze configuration

| Decision | Who signs off | Effect / current safe stance |
|---|---|---|
| **DEC-01** Upload-first wearable scope | Product + AI quality lead | One category-free upload UI; classify and route internally; clarify ambiguity and reject unsupported inputs before generation |
| **DEC-02** Jewellery handling | Merchant pilot + AI lead | Same upload UI and automatic detection; beta generation is unavailable until a separate provider passes jewellery-specific fidelity checks |
| **DEC-03** Beta economics | Product/Finance | Three successful generations per verified user per calendar day; failures/rejections do not count; paid tokens/packs remain inactive pending commercial approval |
| **DEC-04** Personal result / temporary store image retention duration and TTL | Privacy/Product | Reusable person profile until deletion, account closure, or 12 months inactivity; results and wearable-item uploads 30 days; invalid uploads and deleted active-storage assets within 24 hours; store access revoked immediately and assets purged within 24 hours |
| **DEC-05** India payment and OTP providers, business invoicing/GST review | Finance/Legal/Engineering | Beta: verified email OTP and no payments/tax invoices. Commercial release remains gated on provider and tax/legal approval; no vendor or tax percentage is invented. |
| **DEC-06** Adult-only pilot vs guardian compliance | Legal/Product | Beta is 18+ with age and depicted-person permission attestations; no guardian flow; suspected-minor imagery is rejected and purged within 24 hours; neutral adult mannequin remains allowed where supported. |
| **DEC-07** Rendering provider, region/data processing terms and pricing | AI/Security | Apparel: Vertex AI `virtual-try-on-001` via provider-neutral adapter in `asia-southeast1`; record provenance, disable caching where supported, verify Cloud terms/DPA, and never authorize customer-photo training; no beta jewellery route |
| **DEC-08** Product quality thresholds and human review sampling | Product/AI/Merchant | At least 50 rights-cleared golden cases, >=90% acceptable and no unresolved final-evaluation hard failure; automate every-result checks, human-review 100% of golden cases, and review customer imagery only after explicit report/consent; disable a route after 3 confirmed hard failures in its latest 20 deliveries |
| **DEC-09** Latency, quota, timeout, rate limits and incident ownership | Engineering/Ops | One active job/user; 3 successes/day resetting midnight IST; preflight p95 <=3s, generation target p95 <=60s, hard timeout 120s, one same-job transient retry; 10 concurrent workers, 2-minute maximum queue wait; alert at >10% failures/15m or p95 >90s; Engineering responds and Product controls communication/re-enablement |
| **DEC-10** Final font, mobile typography and any production logo assets | Design | Bundle Inter locally; temporary text-only `Wearo` wordmark; H1 32/40 700, H2 24/32 700, H3 20/28 600, body 16/24 400, small 14/20 400, caption 12/16 400, button 16/20 600; retain ivory/plum/gold/lilac roles and use no imitated third-party logo |

### 13.3 Source references and precedence

- **MVP source:** *Wearo AI MVP Product and Platform Requirements v1.0*, 18 pages. Sections 1–5 scope and gates; pages 7–15 the complete 90-identifier mapping; page 16 traction; page 18 sync protocol.
- **Brand source:** *Wearo AI Brand Colours and UI Guidelines v1.0*, 6 pages. Page 2 all primary colours; page 3 mobile/light Shop; page 4 dark tablet Mirror/Studio; page 5 neutral Business/Admin; page 6 exact implementation tokens and contrast guidance.
- **Master version:** Master Product and Platform Requirements v3.0 is referenced by the MVP PDF, but was **not separately attached in this request**. Master wording/acceptance in the traceability appendix is copied from the provided MVP PDF, not independently reconciled with the full master document.

**Change-control rule:** If a truly new product behavior is requested, edit/version **Master v3.0** and its MVP overlay first, then modify this implementation spec. Do not silently insert a new WR ID or mark a BOUNDED residual as done.

---
