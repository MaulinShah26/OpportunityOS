# Private staging deployment

This runbook deploys OpportunityOS to a single Linux VM with Docker Compose and PostgreSQL. The application is intentionally bound to the VM loopback interface, and PostgreSQL is never published to the host network.

The staging workspace is reached through an SSH or Identity-Aware Proxy tunnel. Do not create a public firewall rule for port 8000.

## Architecture

```text
Browser on your computer
        |
        | SSH / IAP tunnel
        v
127.0.0.1:8000 on the VM
        |
        v
OpportunityOS container
        |
        | private Docker network
        v
PostgreSQL container + named volume
```

The container entrypoint waits for PostgreSQL, runs all Alembic migrations, and only then starts Uvicorn. The application container runs as a non-root user with all Linux capabilities removed and a read-only root filesystem.

## 1. VM prerequisites

Use an existing private staging VM or create a small Debian/Ubuntu VM. Install:

- Git
- Docker Engine
- Docker Compose plugin
- `curl`

Confirm:

```bash
docker --version
docker compose version
```

The VM does not need an inbound rule for port 8000. SSH or IAP access is sufficient.

## 2. Check out the application

```bash
git clone https://github.com/MaulinShah26/OpportunityOS.git
cd OpportunityOS
git checkout main
```

For later deployments:

```bash
git fetch origin
git checkout main
git pull --ff-only origin main
```

## 3. Create staging secrets

```bash
cp .env.staging.example .env.staging
chmod 600 .env.staging
```

Generate a URL-safe PostgreSQL password:

```bash
openssl rand -hex 32
```

Place that value in `POSTGRES_PASSWORD`. Keep `LLM_MODE=mock` for the first deployment. This validates persistence, onboarding, analysis, memory controls, and the web workspace without model-provider cost or secret exposure.

Do not commit `.env.staging`. It is ignored by Git.

## 4. Deploy

```bash
bash scripts/deploy_staging.sh
```

The script:

1. validates Docker and Compose;
2. validates the Compose configuration;
3. builds the non-root application image;
4. starts PostgreSQL and waits for it to become healthy;
5. runs Alembic migrations before application startup;
6. verifies `/health` and `/app/`.

Inspect services and logs:

```bash
docker compose --env-file .env.staging -f docker-compose.staging.yml ps
docker compose --env-file .env.staging -f docker-compose.staging.yml logs -f app
```

## 5. Open a private tunnel

From your computer or Cloud Shell, substitute the actual VM name and zone:

```bash
gcloud compute ssh VM_NAME --zone ZONE -- -N -L 8000:127.0.0.1:8000
```

For a VM without an external IP:

```bash
gcloud compute ssh VM_NAME --zone ZONE --tunnel-through-iap -- -N -L 8000:127.0.0.1:8000
```

Keep the tunnel process running and open:

```text
http://127.0.0.1:8000/app/
```

If local port 8000 is occupied, map another local port while keeping the VM destination unchanged:

```bash
gcloud compute ssh VM_NAME --zone ZONE -- -N -L 8080:127.0.0.1:8000
```

Then open `http://127.0.0.1:8080/app/`.

## 6. Back up PostgreSQL

Create a compressed logical backup:

```bash
bash scripts/backup_staging.sh
```

Backups are written to `backups/staging/`, permissioned for the current user, ignored by Git, and retained for 14 days by default.

Override retention:

```bash
BACKUP_RETENTION_DAYS=30 bash scripts/backup_staging.sh
```

Copy important backups off the VM. A backup stored only on the same VM is not sufficient disaster protection.

## 7. Restore a backup

Restoring replaces the staging database. The app is stopped during restore and restarted only after `pg_restore` succeeds.

```bash
RESTORE_CONFIRM=YES bash scripts/restore_staging.sh backups/staging/opportunityos-TIMESTAMP.dump
```

## 8. Update or roll back

Before an update:

```bash
bash scripts/backup_staging.sh
git pull --ff-only origin main
bash scripts/deploy_staging.sh
```

To roll back application code, check out a known-good commit and redeploy:

```bash
git checkout COMMIT_SHA
bash scripts/deploy_staging.sh
```

Database migrations are forward-applied. Do not downgrade a migrated database casually. Restore the pre-deployment backup when a schema rollback is required.

## 9. Enable live models later

Only after mock-mode staging is stable:

1. add the OpenAI and Anthropic keys to `.env.staging`;
2. add the selected model names;
3. change `LLM_MODE=live`;
4. redeploy;
5. verify that unsupported outreach remains blocked by deterministic guardrails.

Never put model keys in GitHub, Compose YAML, shell history, screenshots, or application logs.

## Staging limitations

This is a private single-user staging deployment, not a production architecture. It does not yet include:

- authentication or account isolation;
- managed secret storage;
- managed PostgreSQL or automated off-VM backups;
- TLS termination or a public domain;
- centralized logs, metrics, and alerting;
- high availability or horizontal scaling.

Those controls are required before public or multi-user access.
