# ADR-0005: Serve the first web workspace from FastAPI

## Status
Accepted

## Context
OpportunityOS needs a usable interface for onboarding, single-opportunity analysis, evidence review, feedback, memory control, and audit history. The workflow is still being validated and does not yet justify a separately deployed frontend application.

## Decision
The v0.4 interface is a same-origin, dependency-free HTML/CSS/JavaScript workspace served by FastAPI.

- FastAPI serves `/app` and package-owned assets under `/static`.
- The interface calls the existing `/v1` JSON and multipart endpoints.
- The active profile ID is stored in browser local storage; authentication is explicitly out of scope.
- No external JavaScript, CSS, fonts, analytics, or CDN resources are loaded.
- The web layer contains presentation logic only. Scoring, learning, evidence validation, persistence, and guardrails remain in Python application services.
- A separate React or Next.js frontend will be considered only after the workflow, information hierarchy, and API contracts stabilise.

## Consequences

- The first interface is easy to run locally and deploy as one service.
- There is no CORS or frontend build-chain complexity.
- The UI remains replaceable because it consumes the same public API contracts.
- Browser local storage is convenience state, not an identity or security boundary.
- Production authentication, account recovery, accessibility testing, browser automation, and deployment hardening remain future work.
