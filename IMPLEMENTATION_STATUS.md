# Implementation status

## Completed in v0.2.0

- FastAPI application with stateless and persistent analysis endpoints
- JSON profile onboarding from resume text
- `.txt`, `.pdf`, and `.docx` resume upload onboarding
- Deterministic capability and problem-area inference
- Persistent user and structured personal profile records
- Structured preference, constraint, and aspiration memory records
- Persistent company, opportunity, evidence, and analysis-run records
- Persistent explicit and implicit feedback events
- Feedback-driven profile updates with bounded learning rules
- Stored analysis retrieval and per-user activity count
- SQLite development/test support and PostgreSQL production configuration
- Resume size, type, parseability, and extractable-text validation
- Raw resume files and text deliberately excluded from persistence
- 20 passing automated tests

## Next implementation increment

1. Add profile review and correction APIs for individual memory items.
2. Add evidence-quality and unsupported-claim guardrails.
3. Add a critic result to every recommendation and outreach draft.
4. Build a minimal web interface for onboarding, analysis, and learned-preference review.
5. Create the fixed evaluation dataset before internet-wide opportunity discovery.
