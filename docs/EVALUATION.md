# OpportunityOS evaluation harness

The evaluation harness turns explicit user decisions into a frozen benchmark. It exists to answer a narrow question: does a new model or prompt produce better opportunity decisions for the same person on the same inputs?

## What is frozen

Creating a dataset snapshots:

- the current structured personal profile;
- the original opportunity URL and/or pasted text;
- the latest explicit feedback for each analysis;
- the expected `PURSUE`, `HOLD`, or `REJECT` decision;
- the source analysis identifier and feedback reasons.

The snapshot is immutable. Later profile learning or opportunity edits do not rewrite an existing dataset. Create a new named version when the benchmark should change.

## Label mapping

| Explicit action | Evaluation label |
|---|---|
| Worth pursuing / relevant | `PURSUE` |
| Save signal / maybe later | `HOLD` |
| Not relevant / reject | `REJECT` |

Only explicit feedback is eligible. Unlabelled analyses and implicit behaviour are excluded.

## Readiness rule

A dataset is marked comparison-ready when it contains at least five cases, including:

- at least one `PURSUE` case; and
- at least one `HOLD` or `REJECT` case.

Smaller or one-sided datasets can still run, but their metrics are labelled directional.

## Running a benchmark

Open **Evaluation** in the web workspace:

1. Create a frozen dataset from the current explicit feedback.
2. Select **Run current mode**.
3. Review the aggregate metrics and every case-level match or mismatch.
4. Download the full JSON report when deeper inspection is needed.

Evaluation runs use the currently deployed runtime mode. Mock mode makes no paid calls. Live mode uses the configured provider order and the same hard call/token ceilings as normal analysis.

Runs do not create new opportunity analyses and do not update personal memory. They are stored separately in `evaluation_runs`.

## Metrics

- **Decision accuracy**: exact agreement with the user's frozen decision.
- **Mean decision distance**: average ordinal distance on `REJECT → HOLD → PURSUE`.
- **False pursue rate**: non-pursue cases incorrectly promoted to `PURSUE`; this is the most safety-sensitive error.
- **False reject rate**: frozen `PURSUE` cases incorrectly reduced to `REJECT`.
- **Evidence present rate**: completed cases with at least one captured evidence claim.
- **Critic pass rate**: completed cases without blocking grounding issues.
- **Extraction accuracy**: optional manually labelled extraction checks, when present.
- **Hard-constraint accuracy**: optional manually labelled hard-constraint checks, when present.
- **Provider usage**: model calls, reported tokens, and number of cases that used fallback.

A provider should not be promoted because of decision accuracy alone. False-pursue rate, grounding failures, run failures, and cost must also remain acceptable.

## Recommended comparison sequence

1. Build a balanced benchmark of 8–15 real opportunities.
2. Run and preserve the mock baseline.
3. Enable OpenAI only, with fallback disabled, and rerun the same dataset.
4. Enable Anthropic only and rerun it.
5. Compare exact cases, not only aggregate percentages.
6. Enable fallback only after both single-provider runs are understood.

The benchmark is personal by design. It should remain in the private PostgreSQL deployment and should not be committed to the public repository.
