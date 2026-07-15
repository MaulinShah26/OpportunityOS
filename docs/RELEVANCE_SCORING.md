# Opportunity extraction and relevance scoring

OpportunityOS separates three questions that should not be collapsed into one opaque score:

1. What does the supplied opportunity actually say?
2. How well does it match the user's capabilities, preferences, constraints, and direction?
3. Does the resulting score cross the current decision policy thresholds?

## Deterministic extraction in mock mode

Mock mode does not call a model. It recognises explicit fields such as company, role, opportunity type, engagement, location, work mode, and seniority, then maps supported wording into a controlled set of skills and problem areas.

When no role title is supplied, the extractor uses the explicit engagement description or a neutral company/type fallback. It does not emit `Unspecified opportunity`.

Derived interpretations such as treating an unqualified `Data Analyst` title as junior are used during relevance scoring but are not stored as extracted facts. This keeps the critic from presenting a heuristic inference as a sourced claim.

## Capability fit

Capability fit measures coverage of the opportunity's recognised capability areas. It does not divide by every term in the user's résumé.

Direct matches use the proficiency stored in the personal profile. A small, inspectable related-capability map handles adjacent experience, for example:

- forecasting and product analytics contributing to assortment or inventory planning;
- product management and stakeholder management contributing to project management;
- data science contributing partially to AI work.

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

One high-confidence pasted role description is valid evidence. The score no longer assumes that four evidence rows are inherently better than one complete source.

## Decision policy

v0.9 does not change the production thresholds:

- below `45`: `REJECT`;
- `45` to `71`: `HOLD`;
- `72` or above with extraction confidence of at least `0.60`: `PURSUE`.

Threshold simulations in Evaluation remain diagnostic only. Relevance mechanics should be corrected before changing the policy to fit a small benchmark.
