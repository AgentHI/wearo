# Google Drive auto-sync

Wearo can copy newly completed customer try-on images to a private
`Wearo.ai/Try-Ons` folder in the customer's My Drive. Sync is opt-in, uses the
Google `drive.file` scope, and does not scan, modify, share, or delete unrelated
Drive files. It does not upload historical try-ons.

## Google Cloud setup

1. Create or select a Google Cloud project and enable **Google Drive API**.
2. Configure the OAuth consent screen. Add `openid`, `email`, and
   `https://www.googleapis.com/auth/drive.file`; do not add a broad Drive scope.
3. Create an **OAuth client ID** of type **Web application**.
4. Add the exact callback URL as an authorized redirect URI. For local use this
   is `http://localhost:8000/api/integrations/google-drive/callback`. Production
   must use the API's public HTTPS URL.
5. While the consent screen is in testing mode, add each tester as a test user.
   Publish or complete Google's verification process before the production pilot
   if Google requires it for the configured consent screen.

The OAuth client secret and credential encryption key are backend secrets. They
must be provided to both the API and render worker through the deployment secret
store and must never use a `VITE_` prefix.

## Environment

```dotenv
WEARO_GOOGLE_DRIVE_CLIENT_ID=<oauth-web-client-id>
WEARO_GOOGLE_DRIVE_CLIENT_SECRET=<oauth-web-client-secret>
WEARO_GOOGLE_DRIVE_REDIRECT_URI=https://api.example.com/api/integrations/google-drive/callback
WEARO_GOOGLE_DRIVE_SETTINGS_REDIRECT_URI=https://app.example.com/app/profile
WEARO_GOOGLE_DRIVE_ENCRYPTION_KEY=<base64url-encoded-32-byte-key>
```

Generate a key with:

```bash
openssl rand -base64 32 | tr '+/' '-_' | tr -d '='
```

Keep old encryption keys available through a controlled rotation migration
until all stored refresh tokens have been re-encrypted. The current MVP accepts
one active key and therefore requires a planned re-encryption before changing it.

## Database and local run

From the repository root:

```bash
UV_CACHE_DIR=.uv-cache uv run alembic -c apps/api/alembic.ini upgrade head
UV_CACHE_DIR=.uv-cache uv run uvicorn apps.api.wearo_api.http_api:create_app_from_env --factory --reload
UV_CACHE_DIR=.uv-cache uv run python -m apps.api.wearo_api.worker_process
pnpm --filter @wearo/web dev
```

The existing render worker also claims Drive sync jobs. At least one worker must
run in production. `WEARO_LOCAL_EMBEDDED_WORKER=true` also services Drive jobs in
the local fixed-OTP configuration.

For production, deploy in this order: apply the migration, release the API and
worker with the same encryption key and OAuth settings, release the web build,
then run the connection and one-file smoke test below. Keep the feature
unconfigured (empty client ID) until all three application layers are deployed.
Monitor `PERMANENT_FAILURE`, `RETRY`, and expired `PROCESSING` job counts during
rollout; the worker recovers expired leases automatically.

## Manual end-to-end check

1. Sign in to a consumer account and open **Profile > Google Drive**.
2. Select **Connect Google Drive**, approve the displayed minimal scopes, and
   confirm that the UI shows the chosen Google email and `Wearo.ai/Try-Ons`.
3. Confirm automatic sync is still off. Complete a try-on and verify no Drive
   file is created.
4. Enable automatic sync, complete another try-on, and confirm the API returns
   the result without waiting for Drive.
5. Wait for the worker, then confirm exactly one private JPEG, PNG, or WebP file
   appears in `My Drive/Wearo.ai/Try-Ons` and the last-sync time updates.
6. Temporarily stop the worker, complete a try-on, restart the worker, and
   confirm the durable pending job uploads once.
7. Revoke Wearo in the Google account security page, complete another try-on,
   and confirm the UI requests reconnection. Reconnect the same account and use
   **Retry failed syncs**.
8. Disconnect in Wearo. Confirm pending syncs stop and existing Drive files and
   folders remain private and unchanged.

## Operational notes and MVP limits

- Uploads at or below 5 MiB use multipart upload; larger images use a persisted,
  encrypted resumable session.
- Retryable 429, server, and transport failures use exponential backoff with
  jitter. Revoked credentials require reconnection; full Drive storage is shown
  as a permanent failure until the user frees space and retries.
- An upload is tagged with its Wearo sync-job ID. Every retry searches for that
  tag before uploading, which resolves ambiguous network outcomes without a
  duplicate file.
- The MVP supports one Google account per Wearo consumer, one fixed destination,
  and new try-ons only. It has no folder picker, historical bulk sync, two-way
  sync, or Google Photos integration.
- Disconnect does not revoke the Google grant remotely and does not delete files;
  it erases Wearo's refresh token and stops/cancels queued work. Users may also
  revoke access from their Google account.
