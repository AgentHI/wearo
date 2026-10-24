# Running the simplified beta locally

## Configuration

Copy the variable names from `.env.example` into the ignored `.env`. The API and worker load this
file automatically. `WEARO_LOCAL_DOTENV_OVERRIDE=true` makes the local file authoritative even if
the terminal has stale exported values; omit it or set it to `false` outside local development.
Use a random
`WEARO_AUTH_PEPPER` of at least 32 bytes. Set `WEARO_SECURE_COOKIE=false` only for local HTTP;
production must use secure same-origin HTTPS cookies.

Email OTP delivery fails closed with `EMAIL_DELIVERY_UNAVAILABLE` until the SMTP variables are
configured. Codes and credentials must never be logged.

For local testing without SMTP or SMS delivery, set `WEARO_SECURE_COOKIE=false`,
`WEARO_TEST_AUTH_ENABLED=true`, and `WEARO_TEST_OTP_CODE=9876`. Any valid email address or mobile
number will create or reuse a local consumer identity and accepts `9876` once. This mode bypasses
delivery and resend throttling. It also permits close-up person photos, jewellery, and bypasses the
vision model's suspected-minor rejection for local flow testing. File integrity, single-person,
single-item, ambiguity, and unsafe-content checks remain active. Each request returns a fresh
challenge and a response message that identifies the fake code. Expiry, attempt limits, hashing,
one-time consumption and session/CSRF checks remain active. The API refuses to start with test
authentication and secure-cookie mode enabled; never use fixed authentication in staging or
production.

Set `WEARO_DAILY_LIMIT_ENABLED=false` only during local testing to bypass daily quota and
single-active-generation reservation. The PWA displays an unlimited indicator, but every OpenAI
analysis and generation still incurs provider usage. Leave this setting enabled in production.

Set `WEARO_RENDER_QUALITY_GATE_ENABLED=false` only during local testing to publish provider
results without the post-generation quality-analysis call. This can expose inaccurate or unsafe
outputs, so leave the gate enabled outside controlled testing.

For a single-process local test setup, set `WEARO_LOCAL_EMBEDDED_WORKER=true`. The API then starts
a background render consumer, expires stale five-minute leases, and claims new queue items without
a separate worker terminal. This option is rejected unless fixed local test authentication is also
enabled; leave it disabled outside local development.

## Database and API

```sh
UV_CACHE_DIR=.uv-cache uv run alembic -c apps/api/alembic.ini upgrade head
UV_CACHE_DIR=.uv-cache uv run uvicorn \
  apps.api.wearo_api.http_api:create_app_from_env --factory --host 127.0.0.1 --port 8000
```

The health probe is `GET http://127.0.0.1:8000/health`. It executes `SELECT 1` against the
configured PostgreSQL database. `GET http://127.0.0.1:8000/health/ready` additionally confirms
that image understanding is configured without making a paid provider request.

## Web

```sh
pnpm --filter @wearo/web dev
```

Open the consumer PWA at `http://127.0.0.1:5173/app/` and the Business web app at
`http://127.0.0.1:5173/business`. The Business routes include onboarding, dashboard, Wearo experience,
customer insights, plan/billing and settings presentation; payment and business persistence remain
disabled until their server APIs and provider checkout are connected. The consumer PWA starts at
`/app/sign-in`, sends new accounts to `/app/profile` for mandatory person-profile creation, and
uses `/app/` as the authenticated try-on home. Profiles can retain a full-body photo for clothing
and a close-up photo for jewellery; users choose the appropriate saved photo beside the wearable
upload for each try-on. Jewellery references may include a person, mannequin, hands, or background;
the generation prompt isolates the primary featured wearable and ignores unrelated reference-scene
content. Returning users can replace either profile photo from the Profile tab. The Looks tab
loads the account's delivered, quality-approved previews from private storage until their 30-day
expiry. Each saved look can be downloaded, shared as a private image file through the device share
sheet, or deleted with immediate access revocation and physical purge scheduled within 24 hours.
The page shows only active queued/processing generation activity and refreshes automatically while
work is active. The PWA can be installed from a production build.

The Vite development server proxies `/api` and `/health` to the local API. Production must route
the built web assets and `/api/v1` through the same HTTPS origin and provide SPA fallback to
`index.html` for `/app/*` and `/business/*`. The consumer service worker is scoped to `/app/` and
does not cache `/api/*` responses or private customer images.

## Scheduled operations

Run both commands from a scheduler with the same database and private-storage configuration:

```sh
UV_CACHE_DIR=.uv-cache uv run python -m apps.api.wearo_api.operations recover-leases
UV_CACHE_DIR=.uv-cache uv run python -m apps.api.wearo_api.operations purge --limit 100
```

The first fails processing work whose five-minute worker lease expired, removes it from the active
queue, and releases its daily slot. The worker also performs this recovery before claiming its next
job. The second purges due blobs and retains only the database tombstone.

## Render worker

After the external activation gates are approved, configure one render provider. When OpenAI is
selected, it performs both image-understanding checks and image generation. A scoped
`WEARO_ANALYSIS_ENDPOINT`/`WEARO_ANALYSIS_TOKEN` pair remains an optional analysis override.

For OpenAI, set:

```sh
WEARO_RENDER_PROVIDER=OPENAI
WEARO_OPENAI_API_KEY=your-secret-from-a-secret-store
WEARO_OPENAI_MODEL=gpt-image-2.5-sunburst
WEARO_OPENAI_ANALYSIS_MODEL=gpt-6-luna
WEARO_OPENAI_ENABLED=true
```

`gpt-image-2.5-sunburst` is the default precise-editing model. The adapter also accepts
`gpt-image-2.5-flare`, `gpt-image-2`, and their pinned snapshots listed in
`render_provider.py`. It sends the person and wearable as two references to the OpenAI Images
edit endpoint, requests one portrait PNG, and never logs the API key or provider response body.
`gpt-6-luna` uses the Responses API with image inputs and strict structured output for quote
preflight and post-render quality checks. These checks and generation are paid provider calls.

The retained Google alternative uses `WEARO_RENDER_PROVIDER=GOOGLE_VERTEX`, Google Application
Default Credentials, `WEARO_VERTEX_PROJECT_ID`, and `WEARO_VERTEX_ENABLED=true`.

Then run:

```sh
UV_CACHE_DIR=.uv-cache uv run python -m apps.api.wearo_api.worker_process
```

Use `--once` for a scheduler or smoke test. The worker enforces the product's 7 MB upload limit,
applies the quality gate before publication, records provider/model/request provenance, and
completes quota settlement in PostgreSQL. Drain or recover all queued work before changing
`WEARO_RENDER_PROVIDER`; do not switch a live queue between providers.

## External generation gate

The API returns `VISION_PROVIDER_UNAVAILABLE` at quote creation until the selected provider
credentials and explicit route-enable flag are configured. OpenAI uses its native Responses vision
path by default. Google Vertex requires the approved HTTPS analysis service configured with
`WEARO_ANALYSIS_ENDPOINT` and `WEARO_ANALYSIS_TOKEN`. Do not replace this gate with a permissive
mock in customer-facing environments. See `docs/release/BETA_RELEASE_GATES.md`.
