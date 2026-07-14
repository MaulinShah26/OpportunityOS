# OpportunityOS

OpportunityOS is a personal opportunity-intelligence system. It is designed to surface a small number of highly relevant opportunities—not to become another job board.

The current vertical slice onboards and persists a personal profile, analyses and stores one pasted opportunity or public URL, and gives the user direct control over the memory used for personalisation. It returns:

- a typed opportunity profile;
- evidence and business hypotheses;
- a transparent fit-score breakdown;
- a `PURSUE`, `HOLD`, or `REJECT` decision;
- a critic result with claim-level guardrails;
- an outreach draft only when its declared claims are supported;
- feedback that updates and persists the personal preference model;
- inspectable and editable user memory with audit history.

## Architecture principles

- **CrewAI orchestrates** multi-step agent workflows.
- **OpenAI performs** structured extraction and classification.
- **Claude performs** nuanced business analysis and outreach reasoning.
- **Python owns** constraints, scoring, validation, guardrails, and learning updates.
- **PostgreSQL stores** structured profile, memory, evidence, runs, feedback, audits, and outcomes.
- **Human approval remains mandatory** before any consequential outbound action.

The default development mode is fully deterministic and requires no API keys. Live provider integrations are lazy-loaded.

## Quick start

### Prerequisites

- Python 3.12 recommended
- `uv` recommended
- Docker, only if using PostgreSQL locally

```bash
cp .env.example .env
uv sync --extra dev
uv run pytest
uv run uvicorn opportunityos.api.main:app --reload
```

Open `http://127.0.0.1:8000/app` for the web workspace or `http://127.0.0.1:8000/docs` for the API.

### Run with Docker PostgreSQL

```bash
docker compose up -d postgres
uv run alembic upgrade head
```

### Test the stateless analysis slice

```bash
curl -X POST http://127.0.0.1:8000/v1/analyses \
  -H 'Content-Type: application/json' \
  -d @examples/analyse_request.json
```

## Persistent onboarding and analysis

Create a structured profile from resume text:

```bash
curl -X POST http://127.0.0.1:8000/v1/profiles/onboard \
  -H 'Content-Type: application/json' \
  -d @examples/onboard_request.json
```

The response contains a `user_id`. Use it to run and persist an analysis:

```bash
curl -X POST http://127.0.0.1:8000/v1/users/<user_id>/analyses \
  -H 'Content-Type: application/json' \
  -d '{"opportunity":{"raw_text":"Company: Acme\nRole: Fractional Data Lead\nLocation: Remote\nNeed product analytics and retention support."}}'
```

Resume files can also be submitted to `POST /v1/profiles/onboard-file` as multipart form data. Supported formats are `.txt`, `.pdf`, and `.docx`. OpportunityOS stores the resulting structured profile, not the uploaded file or raw resume text.

## User-controlled memory

List the active capabilities, preferences, constraints, aspirations, and problem areas that OpportunityOS uses:

```bash
curl http://127.0.0.1:8000/v1/users/<user_id>/memory
```

Confirm an inferred item:

```bash
curl -X PATCH http://127.0.0.1:8000/v1/users/<user_id>/memory/<memory_id> \
  -H 'Content-Type: application/json' \
  -d '{"action":"confirm","reason":"Verified by the user"}'
```

The same endpoint supports `update` and `reject`. `DELETE` performs a soft deletion so the audit trail remains available. Audit history is exposed at `GET /v1/users/<user_id>/memory-audit`.

Implicit behaviour cannot overwrite an explicit preference or reactivate a user-rejected memory item. Users can deliberately change those items through the memory API.

## Recommendation guardrails

Every analysis includes a `critic` object. It validates evidence references, flags overstated confidence, distinguishes speculation from supported claims, and blocks outreach when company-specific claims lack valid evidence lineage. A blocked draft is retained inside the critic result for review, but the top-level `outreach` field is removed.

Stored v0.2 analyses remain readable and receive a `legacy_unreviewed` critic marker.

## Web workspace

OpportunityOS serves a lightweight interface directly from FastAPI:

```text
/app                 onboarding, analysis, decisions, memory, and audit history
/static/base.css     layout and form styles
/static/components.css result, memory, and audit styles
/static/*.js         same-origin API client and interaction logic
```

The workspace supports résumé upload, explicit initial preferences and exclusions, loading an existing profile by ID, one-opportunity analysis, evidence and critic review, feedback capture, memory correction, and audit-history inspection. It stores the active profile ID in browser local storage for convenience. This is not an authentication mechanism.

No external frontend packages, CDNs, fonts, analytics, or third-party browser scripts are used.

## Private staging

A private Docker Compose staging stack is available for a single Linux VM:

```bash
cp .env.staging.example .env.staging
# Replace POSTGRES_PASSWORD with: openssl rand -hex 32
bash scripts/deploy_staging.sh
```

The app binds only to `127.0.0.1`, PostgreSQL is not exposed on the host, and Alembic migrations run before Uvicorn starts. Access the workspace through an SSH or Google Cloud IAP tunnel rather than opening port 8000 publicly.

See [docs/STAGING_DEPLOYMENT.md](docs/STAGING_DEPLOYMENT.md) for deployment, tunnelling, backup, restore, update, and rollback procedures.

## Runtime modes

| Setting | Value | Behaviour |
|---|---|---|
| `LLM_MODE` | `mock` | Deterministic local extraction and analysis |
| `LLM_MODE` | `live` | OpenAI extraction + Claude analysis |
| `ORCHESTRATOR` | `local` | Direct application-service orchestration |
| `ORCHESTRATOR` | `crewai` | CrewAI Flow wrapper around the same typed service |

Live mode requires `OPENAI_API_KEY`, `OPENAI_MODEL`, `ANTHROPIC_API_KEY`, and `ANTHROPIC_MODEL`.

## Repository map

```text
src/opportunityos/
├── api/                 FastAPI routes and dependency wiring
├── application/         scoring, learning, guardrails, and use-case service
├── domain/              typed business contracts
├── infrastructure/      database, LLM, resume, and research adapters
└── orchestration/       optional CrewAI Flow runtime
migrations/              Alembic database migrations
tests/                   unit and API tests
examples/                sample payloads
```

## What is intentionally not in this version

- internet-wide opportunity discovery;
- LinkedIn scraping;
- autonomous outreach sending;
- reinforcement learning;
- OCR for scanned resumes;
- a production web interface.

Those are later stages after the relevance, memory-control, evidence-safety, and staging-operability foundations are validated.
