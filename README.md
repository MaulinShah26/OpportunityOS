# OpportunityOS

OpportunityOS is a personal opportunity-intelligence system. It is designed to surface a small number of highly relevant opportunities—not to become another job board.

The current vertical slice onboards and persists a personal profile, then analyses and stores one pasted opportunity or public URL. It returns:

- a typed opportunity profile;
- evidence and business hypotheses;
- a transparent fit-score breakdown;
- a `PURSUE`, `HOLD`, or `REJECT` decision;
- an outreach draft;
- a feedback event that updates and persists the personal preference model.

## Architecture principles

- **CrewAI orchestrates** multi-step agent workflows.
- **OpenAI performs** structured extraction and classification.
- **Claude performs** nuanced business analysis and outreach reasoning.
- **Python owns** constraints, scoring, validation, and learning updates.
- **PostgreSQL stores** structured profile, memory, evidence, runs, feedback, and outcomes.
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

Open `http://127.0.0.1:8000/docs`.

### Run with Docker PostgreSQL

```bash
docker compose up -d postgres
uv run alembic upgrade head
```

### Test the first vertical slice

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
├── application/         scoring, learning, and use-case service
├── domain/              typed business contracts
├── infrastructure/      database, LLM, and research adapters
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
- opaque conversational memory;
- automatic modification of hard constraints.

Those are later stages after the relevance and learning foundations are validated.
