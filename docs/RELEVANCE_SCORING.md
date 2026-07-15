# Opportunity extraction and relevance scoring

OpportunityOS separates four questions that should not be collapsed into one opaque score:

1. What does the supplied opportunity actually say?
2. Which parts of the source describe the role rather than the company, hiring process, or benefits?
3. How well does the opportunity match the user's capabilities, preferences, constraints, and direction?
4. Does the score satisfy the decision policy and its safety gates?

## Deterministic extraction in mock mode

Mock mode does not call a model. It recognises explicit fields such as company, role, opportunity type, engagement, location, work mode, and seniority, then maps supported wording into a controlled set of skills and problem areas.

The extractor gives explicit fields priority. When a source has no explicit role field, it can recover a concrete first-line headline such as `Expert Opportunity - Advisory Consultant`. Generated fallback titles remain visibly generic.

Role skills and problem areas are extracted from role-relevant sections such as:

- About the role;
- What you'll do;
- Requirements and qualifications;
- Key requirements;
- Responsibilities;
- Potential business problems.

Company descriptions, hiring-process text, AI-interviewer notices, benefits, and similar boilerplate do not create role skills or business problems. Generic words such as `partner`, `partnerships`, and `high-growth` are not sufficient to classify an engagement as a partnership or a role as growth work.

Derived interpretations such as treating an unqualified `Data Analyst` title as junior are used during relevance scoring but are not stored as extracted facts. This keeps the critic from presenting a heuristic inference as a sourced claim.

## Capability fit

Capability fit measures coverage of the opportunity's recognised capability areas. It does not divide by every term in the user's résumé.

Direct matches use the proficiency stored in the personal profile. A small, inspectable related-capability map handles adjacent experience, for example:

- forecasting and product analytics contributing to assortment or inventory planning;
- product management and stakeholder management contributing to project management;
- data science contributing partially to AI work;
- business strategy contributing partially to advisory consulting;
- communication contributing partially to storylining.

Presentation design, PowerPoint, storylining, and advisory-practice experience remain distinct capability requirements. A strong preference for consulting cannot silently substitute for those requirements.

Unrecognised roles fall back to direct term coverage with a capped score.

## Preference fit

Preference keys are matched to explicit opportunity facets:

- engagement;
- work mode;
- seniority;
- execution-only work style;
- location.

A preference weight of `0.5` is neutral. Values above it increase affinity and values below it express aversion. Explicit user feedback has a stronger effect than inferred memory. Internal or generic keys that do not describe an opportunity facet are excluded from this dimension.

## Constraint compatibility

Hard and soft constraints are matched against opportunity type, location, work mode, seniority, title, recognised role concepts, and execution-only work. Hard breaches still force the total fit score to zero.

## Future-direction fit

Future direction considers aspiration wording, recognised capability/problem concepts, and engagement direction. Consulting, fractional, and advisory work can match an explicit independent-consulting aspiration even when their role vocabulary differs.

## Evidence quality

Evidence quality combines:

- the confidence of captured source material; and
- the extraction confidence retained after grounding.

One high-confidence pasted role description is valid evidence. The score does not assume that four evidence rows are inherently better than one complete source.

Canonical extracted values may be grounded by supported aliases. For example, `data analyst` can support the canonical capability label `analytics` without generating a false unsupported-value warning.

## Decision policy

v0.11 keeps the production thresholds unchanged:

- below `45`: `REJECT`;
- `45` to `71`: `HOLD`;
- `72` or above with extraction confidence of at least `0.60`: score-based `PURSUE`.

A score-based PURSUE is capped at HOLD when:

- the opportunity still has only a generated fallback identity; or
- capability fit is below `0.35`, indicating that engagement preference and future direction may be masking a material qualification gap.

Junior execution-heavy roles and explicit low-ownership aversions can still force REJECT. Every gate is recorded separately from the numerical score.

Threshold simulations in Evaluation remain diagnostic only. Relevance mechanics should be corrected before changing the policy to fit a small benchmark.
