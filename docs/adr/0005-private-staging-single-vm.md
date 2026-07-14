# ADR-0005: Use a private single-VM staging deployment

## Status

Accepted

## Context

OpportunityOS needs a real browser-accessible environment to validate onboarding, PostgreSQL persistence, personal memory controls, analysis guardrails, and the web workspace. It does not yet have authentication, account isolation, operational monitoring, or the controls required for public access.

Introducing a managed Kubernetes platform, a public ingress, or separate frontend infrastructure at this stage would add cost and operational complexity before the product workflow is validated.

## Decision

The first staging environment will run on one Linux VM using Docker Compose:

- one non-root OpportunityOS application container;
- one PostgreSQL container with a named persistent volume;
- Alembic migrations executed before application startup;
- the application published only on `127.0.0.1` of the VM;
- PostgreSQL available only on an internal Docker network;
- browser access through SSH or Google Cloud IAP port forwarding;
- mock LLM mode enabled for initial workflow validation;
- manual logical backups with a documented restore procedure.

No public firewall rule, domain, TLS endpoint, or anonymous access will be created.

## Consequences

### Positive

- The actual application and PostgreSQL paths are exercised.
- Staging remains private despite the lack of authentication.
- Deployment is inexpensive and understandable.
- The same container image can later move to a managed runtime.
- Operational failure modes such as migrations, restarts, backups, and restores become testable.

### Negative

- The VM and PostgreSQL container are single points of failure.
- Backups must be copied off the VM manually.
- Access requires an active tunnel.
- Scaling and multi-user security are deliberately deferred.

## Exit criteria

Move beyond this architecture only after:

1. the end-to-end user workflow is validated in staging;
2. authentication and account isolation are implemented;
3. the fixed evaluation dataset meets agreed relevance and safety thresholds;
4. public or multi-user access becomes a genuine requirement;
5. managed secrets, database backups, logging, and alerting are designed.
