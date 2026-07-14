# Implementation status

## Completed through v0.4.0

- FastAPI application with stateless and persistent analysis endpoints
- JSON profile onboarding from resume text
- `.txt`, `.pdf`, and `.docx` resume upload onboarding
- Deterministic capability and problem-area inference
- Persistent user and structured personal profile records
- Structured capability, preference, constraint, aspiration, and problem-area memory
- Persistent company, opportunity, evidence, and analysis-run records
- Persistent explicit and implicit feedback events
- Feedback-driven profile updates with bounded learning rules
- User-controlled confirm, update, reject, and delete actions for memory
- Memory audit history with actor, reason, and before/after snapshots
- Evidence-lineage and unsupported-outreach guardrails
- Critic result attached to every analysis
- SQLite development/test support and PostgreSQL production configuration
- Raw resume files and text deliberately excluded from persistence
- Same-origin web workspace served by FastAPI
- Web onboarding with explicit engagement, work-mode, aspiration, problem-area, and exclusion inputs
- Opportunity submission, fit-score explanation, evidence, critic, and outreach views
- Learned-memory controls and memory audit interface
- 31 passing automated tests

## Next implementation increment

1. Add production authentication and user sessions.
2. Create a fixed evaluation dataset and human relevance-review workflow.
3. Add opportunity history, saved decisions, and follow-up state.
4. Deploy a private staging environment with PostgreSQL.
5. Add selected public-source discovery only after relevance precision is validated.
