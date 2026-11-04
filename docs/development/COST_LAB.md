# Wearo Model Cost Lab

Cost Lab is an independently deployed FastAPI service and worker. It shares the PostgreSQL
cluster but writes only to the `cost_lab` schema. Its login and cookie are independent from the
Wearo Super Admin. USD is always retained as the accounting value; INR is display-only.

## Local setup

1. Copy the Cost Lab variables from `.env.example` into the ignored `.env`.
2. Generate credentials:

   ```sh
   UV_CACHE_DIR=.uv-cache uv run python -m apps.cost_lab_api.credentials hash-password
   UV_CACHE_DIR=.uv-cache uv run python -m apps.cost_lab_api.credentials generate-secrets
   ```

3. Install and migrate, then start each process in a separate terminal:

   ```sh
   UV_CACHE_DIR=.uv-cache uv sync --python /opt/homebrew/bin/python3.11 --extra dev
   UV_CACHE_DIR=.uv-cache uv run alembic -c apps/api/alembic.ini upgrade head
   UV_CACHE_DIR=.uv-cache uv run uvicorn apps.cost_lab_api.app:create_app --factory --host 127.0.0.1 --port 8011
   UV_CACHE_DIR=.uv-cache uv run python -m workers.cost_lab_worker.main
   pnpm --filter @wearo/web dev
   ```

Vite development should proxy `/api/cost-lab` to port 8011 (the repository configuration does
this). Open `http://localhost:5173/admin/cost-lab`.

## First benchmark

1. Sign in with `COST_LAB_ADMIN_USERNAME` and the password used for the hash.
2. Add an OpenAI-compatible or BytePlus provider. Prefer environment references such as
   `env:WEARO_OPENAI_API_KEY` or `env:WEARO_BYTEPLUS_API_KEY` to pasting a key; pasted keys are
   encrypted with `COST_LAB_ENCRYPTION_KEY` and are never returned by the API.
3. Add a model, then add its effective pricing components. Current prices are deliberately not
   hardcoded.
4. Under Dataset, choose a configured model and click **Generate dataset now**. The worker creates
   one synthetic adult woman reference plus ten jewellery, ten saree, and ten varied dress images.
   It then creates Low, Medium, and High local variants for every original. This one-time generation
   cost is recorded separately from try-on benchmark expenditure. You can also upload additional
   authorized images manually.
5. Under Run Benchmark, select a model and start it. Cost Lab automatically queues 30 try-ons:
   ten each for Low, Medium, and High. Each quality uses its matching person/product variants and
   internally reproducible random jewellery, saree, or dress pairings. The prompt and seed are
   managed and recorded automatically. Keep the worker running and follow progress/results.

Automated tests never call a paid provider. Run targeted verification with:

```sh
UV_CACHE_DIR=.uv-cache uv run pytest tests/test_cost_lab.py
pnpm --filter @wearo/web check
```

## Final model check and production promotion

After a candidate has at least one completed benchmark, open **Final checks**, select the model
and a person image, and start the fixed production-readiness suite. It creates 12 outputs: two
jewellery images and one saree and dress image at each of Low, Medium, and High quality. The normal
Cost Lab worker processes these linked runs.

Score every output from 1–10. Comments are currently hidden in the UI. After all 12 scores are
stored, Cost Lab calculates separate Low, Medium, and High percentages and shows the configured
per-image price for each quality. These summaries are advisory: there is no automatic promotion
threshold. The administrator decides whether to promote and which qualities to approve. Promotion
adds the candidate to the auditable `cost_lab.production_model_releases` history with its selected
quality levels (Low, Medium, and/or High). Promoted models are managed from the separate
**Promoted models** menu. Multiple
models can remain active, with unique consecutive priorities where priority 1 is the first routing
choice. Promoting a newer release of the same model retires its earlier active release while
preserving the history and priority position.

## Adding an adapter

Implement the `ProviderAdapter` protocol in `apps/cost_lab_api/adapters.py`, including an explicit
validation and generation request contract. Add a new `provider_type`, dispatch it in the worker,
and create mocked response tests. OpenAI Images-compatible, BytePlus ModelArk, and Black Forest
Labs adapters are currently executable. Do not route another provider through the OpenAI-compatible
adapter unless its image edit API is actually compatible. Normalize only usage fields the provider
really reports; preserve aggregate-only token usage rather than inventing a split.

BFL diagnostics are emitted as structured `bfl_upstream` log entries. They include the phase,
upstream status, sanitized response, request ID, generation ID, and elapsed time; credentials and
image/base64 request data are never logged. Model tests currently wait synchronously while the BFL
job is polled. Keep the reverse proxy timeout above `COST_LAB_REQUEST_TIMEOUT_SECONDS` until the
planned browser-facing asynchronous test-job API is introduced.

## GCP VM deployment

Run the migration during the normal compatible migration step. Install two systemd services using
the API and worker commands above, with the existing private `.env` supplied through
`EnvironmentFile`. Run the API on loopback only. Add this location ahead of the general `/api/`
location and retain the existing SPA fallback for `/admin/cost-lab/*`:

```nginx
location /api/cost-lab/ {
    proxy_pass http://127.0.0.1:8011/api/cost-lab/;
    proxy_read_timeout 150s;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

After deploying the migration and frontend, restart the Cost Lab API and worker only. No automatic
deployment is performed by this change.

## Known MVP limitations

- Executable adapters are available for OpenAI Images-compatible providers and BytePlus ModelArk.
  Other providers require their own adapter.
- Local filesystem assets are suitable for one VM; use an object-store implementation before
  horizontal scaling.
- Live progress uses polling. Output-quality scoring remains a human review step.
- FX refresh uses the configured HTTP source and falls back to the most recent database rate.
