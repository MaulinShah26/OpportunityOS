# OpportunityOS

OpportunityOS is a personal opportunity-intelligence system. It is designed to surface a small number of highly relevant opportunities—not to become another job board.

The first vertical slice accepts a structured personal profile plus one pasted opportunity or public URL, then returns:

- a typed opportunity profile;
- evidence and business hypotheses;
- a transparent fit-score breakdown;
- a `PURSUE`, `HOLD`, or `REJECT` decision;
- an outreach draft;
- a feedback event that can update the personal preference model.

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

## What is intentionally not in this first slice

- internet-wide opportunity discovery;
- LinkedIn scraping;
- autonomous outreach sending;
- reinforcement learning;
- opaque conversational memory;
- automatic modification of hard constraints.

Those are later stages after the relevance and learning foundations are validated.
