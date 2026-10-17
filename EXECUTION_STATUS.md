# Wearo.ai execution status

**Last updated:** 17 October 2026  
**Local migration head:** `20261017_0014`  
**Current state:** Simplified upload-first beta is locally implemented; external production gates
remain fail-closed.

## Completed local beta path

- Email OTP has generic anti-enumeration responses, HMAC-hashed challenges, expiry, throttling,
  attempt caps and replay prevention. PostgreSQL stores only hashes; SMTP is replaceable.
- Browser sessions use hashed opaque cookies, realm checks, expiry/revocation and CSRF validation on
  every mutation.
- JPEG/PNG/WebP uploads are decoded and integrity-hashed before being placed in owner-scoped private
  storage. Private reads require the authenticated owner.
- Consent records all five approved attestations as immutable `beta-v1` evidence.
- A reusable person profile supports optional height/weight visual guidance, replacement and
  immediate access revocation with deletion scheduled within 24 hours.
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
  render and logout endpoints. The Shop UI is wired to the same-origin API and reuses saved profiles.
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
| Migration policy | PASS: 14 revisions |
| Latest migration rollback/reapply | PASS: `0014 → 0013 → 0014`; current is head |
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
