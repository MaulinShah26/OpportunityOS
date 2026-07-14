# ADR-0003: Persist structured profiles, not raw resumes

## Status
Accepted

## Context
OpportunityOS needs enough durable information to personalise analysis and learn from user feedback. Resumes are useful onboarding inputs, but retaining raw files or full resume text creates unnecessary privacy and security exposure.

## Decision

- Accept `.txt`, `.pdf`, and `.docx` resumes up to 5 MB.
- Extract text only for the onboarding request.
- Infer capabilities and problem areas with a deterministic parser in mock mode.
- Persist the resulting structured profile and memory items.
- Do not persist the uploaded file or raw resume text in v0.2.
- Treat user-entered preferences, constraints, aspirations, and corrections as authoritative.
- Keep profile, opportunity, evidence, analysis, and feedback records in the relational store.

## Consequences

- Users can inspect and correct the structured data that affects recommendations.
- A database compromise does not automatically expose original resume documents.
- Scanned PDFs without an extractable text layer are rejected until an OCR workflow is added.
- Future model-assisted resume extraction can replace the deterministic parser without changing the persistence contract.
