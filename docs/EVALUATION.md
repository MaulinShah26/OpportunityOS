# OpportunityOS evaluation harness

The evaluation harness turns explicit user decisions into a frozen benchmark. It exists to answer a narrow question: does a new model, prompt, or decision policy produce better opportunity decisions for the same person on the same inputs?

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

Smaller or one-sided datasets can still run, but their metrics are labelled directional. Five cases are enough to expose obvious failure modes, not enough to establish a stable production calibration. Aim for 12–20 cases before changing thresholds.

## Running a benchmark

Open **Evaluation** in the web workspace:

1. Create a frozen dataset from the current explicit feedback.
2. Select **Run current mode**.
3. Review aggregate metrics, decision bias, and every case-level match or mismatch.
4. Expand **Why this score and decision?** to inspect extraction confidence, threshold margins, dimension contributions, and critic issues.
5. Download the full JSON report when deeper inspection is needed.

Evaluation runs use the currently deployed runtime mode. Mock mode makes no paid calls. Live mode uses the configured provider order and the same hard call/token ceilings as normal analysis.

Runs do not create new opportunity analyses and do not update personal memory. They are stored separately in `evaluation_runs`.

## Metrics and diagnostics

- **Decision accuracy**: exact agreement with the user's frozen decision.
- **Mean decision distance**: average ordinal distance on `REJECT → HOLD → PURSUE`.
- **False pursue rate**: non-pursue cases incorrectly promoted to `PURSUE`; this is the most safety-sensitive error.
- **False reject rate**: frozen `PURSUE` cases incorrectly reduced to `REJECT`.
- **Underprediction rate**: cases where the system chose a more conservative action than the user.
- **Overprediction rate**: cases where the system chose a more aggressive action than the user.
- **Prediction counts and confusion matrix**: distribution of decisions and exact expected-versus-predicted combinations.
- **Evidence present rate**: completed cases with at least one captured evidence claim.
- **Critic pass rate**: completed cases without blocking grounding issues.
- **Extraction accuracy**: optional manually labelled extraction checks, when present.
- **Hard-constraint accuracy**: optional manually labelled hard-constraint checks, when present.
- **Provider usage**: model calls, reported tokens, and number of cases that used fallback.

Each case also records the score contribution from every fit dimension, extraction confidence, critic issue codes, and distance from the current `HOLD` and `PURSUE` thresholds.

A provider should not be promoted because of decision accuracy alone. False-pursue rate, grounding failures, run failures, and cost must also remain acceptable.

## Exploratory threshold simulation

For a comparison-ready dataset, OpportunityOS searches for a threshold pair that improves agreement while prioritising a low false-pursue rate. It compares the simulated policy with the current defaults:

- `HOLD` at 45;
- `PURSUE` at 72;
- minimum extraction confidence of 0.60 for `PURSUE`.

The simulation is diagnostic only. It does not alter production decisions, environment settings, profile memory, or stored analyses. Suggestions from fewer than 12 cases are explicitly marked unstable because small personal datasets can overfit easily.

Threshold changes should be considered only after:

1. the benchmark has enough varied cases;
2. extraction quality is acceptable;
3. false-pursue behaviour remains safe;
4. case-level changes make sense, not just the aggregate percentage.

## Recommended comparison sequence

1. Build a balanced benchmark of 8–15 real opportunities.
2. Run and preserve the mock baseline.
3. Inspect extraction failures and threshold bias before spending model credits.
4. Enable OpenAI only, with fallback disabled, and rerun the same dataset.
5. Enable Anthropic only and rerun it.
6. Compare exact cases, not only aggregate percentages.
7. Enable fallback only after both single-provider runs are understood.

The benchmark is personal by design. It should remain in the private PostgreSQL deployment and should not be committed to the public repository.
