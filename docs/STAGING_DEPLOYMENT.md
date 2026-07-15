# Private staging deployment

This runbook deploys OpportunityOS to a single Linux VM with Docker Compose and PostgreSQL. The application is intentionally bound to the VM loopback interface, and PostgreSQL is never published to the host network.

The staging workspace is reached through an SSH or Identity-Aware Proxy tunnel. Do not create a public firewall rule for the application port.

## Architecture

```text
Browser on your computer
        |
        | SSH / IAP tunnel
        v
127.0.0.1:<STAGING_PORT> on the VM
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

The VM does not need an inbound rule for the application port. SSH or IAP access is sufficient.

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

From your computer or Cloud Shell, substitute the actual VM name, zone, and configured `STAGING_PORT`:

```bash
gcloud compute ssh VM_NAME --zone ZONE -- -4 -N \
  -L 0.0.0.0:8800:127.0.0.1:8800
```

For a VM without an external IP, add `--tunnel-through-iap` before `--`.

Keep the tunnel process running and open:

```text
http://127.0.0.1:8800/app/
```

Cloud Shell Web Preview must use the same local port as the tunnel.

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

## 9. Enable bounded live models

Live mode accepts either OpenAI, Anthropic, or both. A provider is considered configured only when both its API key and model are present.

Edit the protected environment file without echoing secrets into shell history:

```bash
cd /opt/opportunityos
sudo nano .env.staging
```

For OpenAI only:

```text
LLM_MODE=live
LLM_PRIMARY_PROVIDER=openai
OPENAI_API_KEY=<secret>
OPENAI_MODEL=<model-name>
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=
```

For Anthropic only, use `LLM_PRIMARY_PROVIDER=anthropic` and populate the Anthropic pair. For provider fallback, configure both pairs and use either a named primary or `auto`.

Keep the initial ceilings conservative:

```text
LLM_FALLBACK_ENABLED=true
LLM_MAX_CALLS_PER_ANALYSIS=5
LLM_MAX_ESTIMATED_INPUT_TOKENS_PER_ANALYSIS=18000
LLM_MAX_OUTPUT_TOKENS_PER_ANALYSIS=6000
LLM_MAX_PROMPT_CHARS=60000
LLM_MAX_SOURCE_CHARS=30000
LLM_EXTRACTION_MAX_OUTPUT_TOKENS=1200
LLM_ANALYSIS_MAX_OUTPUT_TOKENS=1600
LLM_OUTREACH_MAX_OUTPUT_TOKENS=900
```

Redeploy and verify provider readiness:

```bash
sudo bash scripts/deploy_staging.sh
curl --fail --silent http://127.0.0.1:${STAGING_PORT:-8800}/health
```

The health response lists configured provider names, never keys. Run one known opportunity and inspect the decision screen's **Provider and budget trace**. Confirm:

- provider roles are visible;
- reported tokens are present when the provider returns usage;
- fallback remains false for a normal run;
- unsupported extracted facts appear as critic warnings and do not influence scoring;
- unsupported outreach is still blocked.

Provider failures return an explicit service error; OpportunityOS never silently downgrades a live run to mock mode. Outreach failure is non-fatal and is shown as a critic warning because the decision itself remains useful.

Never put model keys in GitHub, Compose YAML, command arguments, screenshots, browser fields, or application logs. This staging setup still uses a local permissioned environment file; managed secret storage is required before production.

## Staging limitations

This is a private single-user staging deployment, not a production architecture. It does not yet include:

- authentication or account isolation;
- managed secret storage;
- managed PostgreSQL or automated off-VM backups;
- TLS termination or a public domain;
- centralized logs, metrics, and alerting;
- high availability or horizontal scaling.

Those controls are required before public or multi-user access.
