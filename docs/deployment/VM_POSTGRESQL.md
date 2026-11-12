# VM deployment with DigitalOcean Managed PostgreSQL

The main API, render worker, Cost Lab API, Cost Lab worker, scheduled operations, and Alembic all
read the same `WEARO_DATABASE_URL`. Local development continues to use the ignored repository
`.env` and its Docker PostgreSQL URL. Production must inject its configuration into every process;
it must not copy the local `.env` into a service.

## Production configuration

Start from `infra/vm/wearo-production.env.example` and store the populated values in the VM's
protected secret mechanism. At minimum, every production process must receive:

```sh
WEARO_ENVIRONMENT=production
WEARO_DATABASE_URL=postgresql://doadmin:URL_ENCODED_PASSWORD@db-pgsql-blr1-13885-do-user-960149-0.f.db.ondigitalocean.com:25060/defaultdb?sslmode=require
```

Use the rotated DigitalOcean password, URL-encoded as a URI component. Do not put it in a shell
script, systemd unit committed to Git, container image, Docker Compose file, or repository `.env`.
If systemd runs the services, use a root-readable `EnvironmentFile` outside the checkout with mode
`0600`, or use the VM/cloud secret manager. Configure the same protected file for all four service
processes. Setting `WEARO_ENVIRONMENT=production` prevents a repository `.env` from being loaded,
even if one is accidentally present on the VM.

Before restarting, verify each service manager/container has both variables. Do not print the
complete URL into deployment logs. The `sslmode=require` query parameter is mandatory for this
DigitalOcean connection.

## First production migration

1. Rotate the database password that was shared outside the secret manager and update the protected
   production value.
2. Confirm DigitalOcean's trusted sources/firewall allows the current Google VM public egress IP.
   Add the future AWS VM egress IP before moving the workload.
3. Ensure a current managed backup/restore point exists.
4. Stop or leave undeployed the API and workers for the first migration so they cannot use a
   partially initialized schema.
5. From the release checkout on the VM, load the protected environment without displaying it and
   run:

   ```sh
   UV_CACHE_DIR=.uv-cache uv run alembic -c apps/api/alembic.ini current
   UV_CACHE_DIR=.uv-cache uv run alembic -c apps/api/alembic.ini upgrade head
   UV_CACHE_DIR=.uv-cache uv run alembic -c apps/api/alembic.ini current
   ```

6. The final revision must equal the repository's Alembic head. Start the main API and check
   `/health`, then start the render worker, Cost Lab API, and Cost Lab worker.

Do not run `scripts/rehearse_migrations.sh` against production: it deliberately downgrades to the
base revision and is only for disposable databases.

For later releases, take a backup/restore point, run `upgrade head` once as a dedicated deployment
step, deploy/restart the services, then check `/health`. Alembic serializes its own revision state;
only one release job should perform migrations.

## Local development

Keep the existing ignored `.env` values:

```sh
WEARO_ENVIRONMENT=local
WEARO_LOCAL_DOTENV_OVERRIDE=true
WEARO_DATABASE_URL=postgresql://wearo:LOCAL_PASSWORD@127.0.0.1:55432/wearo_dev
```

This keeps local API, workers, Cost Lab, tests, and Alembic pointed at Docker PostgreSQL while the
production VM uses DigitalOcean.
