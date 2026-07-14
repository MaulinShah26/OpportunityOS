# ADR-0004: User-controlled memory and deterministic claim guardrails

## Status
Accepted

## Context

OpportunityOS continuously learns from explicit feedback and observed behaviour. Without inspectable memory and claim-level controls, the system could silently reinforce wrong assumptions or produce outreach that overstates what is known about a company.

## Decision

- Persist capabilities, preferences, constraints, aspirations, and problem areas as individual memory records.
- Store source, confidence, lifecycle status, active state, and user-override state for each record.
- Allow users to confirm, update, reject, or soft-delete memory items.
- Retain an append-only audit record for memory changes.
- Never allow implicit behaviour to modify an explicit preference.
- Never allow learning to reactivate a user-rejected or deleted memory item.
- Validate evidence references for every factual or supported hypothesis.
- Attach a critic result to every analysis.
- Remove outreach from the executable result when its company-specific claims are unsupported, while preserving the blocked draft for review.
- Treat older stored analyses as unreviewed rather than failing to deserialize them.

## Consequences

- Personalisation becomes inspectable and reversible.
- Learning updates remain bounded by user authority.
- Outreach safety is enforced by deterministic code rather than model self-assessment alone.
- Database migrations and audit storage add implementation complexity.
- The current text guardrail is intentionally conservative and will require evaluation before production use.
