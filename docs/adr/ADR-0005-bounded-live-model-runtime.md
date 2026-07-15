# ADR-0005: Bounded interchangeable live-model runtime

## Status

Accepted for OpportunityOS v0.6.

## Context

The deterministic vertical slice proved the product workflow but cannot provide production-quality extraction and business reasoning. Enabling model APIs directly would introduce three unacceptable risks: unbounded cost, provider lock-in, and ungrounded model output influencing personal recommendations or outreach.

## Decision

OpportunityOS treats OpenAI and Anthropic as interchangeable adapters behind the existing typed application ports.

A live analysis:

1. starts a request-scoped runtime budget;
2. collects evidence;
3. invokes the primary extraction provider;
4. uses the secondary provider only after a provider, JSON, or schema failure;
5. removes extracted facts that cannot be grounded in supplied text or evidence;
6. invokes the business analyst under the same budget;
7. computes fit and recommendation deterministically in Python;
8. generates outreach only for `PURSUE`, and treats outreach failure as non-fatal;
9. applies deterministic claim/evidence guardrails;
10. returns provider, fallback, and usage metadata without secrets.

The runtime enforces ceilings before paid calls for model-call count, estimated input tokens, reserved output tokens, prompt characters, source characters, and role-specific output tokens. A live provider failure never silently downgrades to mock output.

## Consequences

- Either provider can run the complete workflow.
- A second provider is optional rather than mandatory.
- The maximum work attempted per analysis is predictable from configuration.
- Token usage is inspectable when providers report it.
- Model quality can improve without moving scoring, constraints, or trust controls into prompts.
- Provider/schema failures are explicit and testable without API keys.

This does not provide an exact USD budget because pricing differs by model and can change independently. Token and call ceilings are the stable hard-control layer; external provider billing alerts remain an operational requirement.
