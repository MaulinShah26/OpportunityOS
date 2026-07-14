# ADR-0001: Separate orchestration, reasoning, and deterministic policy

## Status
Accepted

## Context
OpportunityOS must use CrewAI, Claude, and OpenAI without creating overlapping agent loops or making user constraints dependent on probabilistic model behaviour.

## Decision
- CrewAI owns workflow sequencing and state transitions.
- OpenAI owns structured extraction and classification.
- Claude owns nuanced business analysis and outreach drafting.
- Python owns hard constraints, scoring, validation, and learning-weight updates.
- PostgreSQL owns durable structured memory, evidence, feedback, and outcomes.
- Human approval is required before outbound communication.

## Consequences
- The system can run in deterministic mock mode.
- Model providers are replaceable behind typed ports.
- Hard constraints remain testable and explainable.
- Adding more agents requires evidence that the separation improves quality.
