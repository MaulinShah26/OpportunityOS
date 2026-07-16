# OpportunityOS evaluation harness

The evaluation harness turns explicit user decisions and user-confirmed opportunity facts into an immutable benchmark. It answers two separate questions:

1. Did the system read the opportunity correctly?
2. Did it make the same decision as the user?

A correct final decision does not imply correct extraction. These metrics must remain separate.

## What is frozen

Creating a labelled dataset snapshots:

- the current structured personal profile;
- the original opportunity URL and/or pasted text;
- the latest explicit feedback for each selected analysis;
- the expected `PURSUE`, `HOLD`, or `REJECT` decision;
- user-confirmed extraction labels;
- the source analysis identifier and feedback reasons.

The snapshot is immutable. Later learning, extraction changes, or opportunity edits do not rewrite an existing dataset.

## Decision labels

| Explicit action | Evaluation label |
|---|---|
| Worth pursuing / relevant | `PURSUE` |
| Save signal / maybe later | `HOLD` |
| Not relevant / reject | `REJECT` |

Only explicit feedback is eligible. Unlabelled analyses and implicit behaviour are excluded.

## Extraction labels

Before freezing a new dataset, the Evaluation workspace displays the current extraction for each eligible analysis. The user selects the cases to include, checks them against the original source, corrects any errors, and confirms the label.

A confirmed extraction label can cover:

- company name;
- role or opportunity title;
- opportunity type;
- remote status;
- location;
- required skills;
- problem areas;
- responsibilities.

List fields use exact set comparison after case and whitespace normalisation. A missing required item and an unsupported extra item both count as extraction errors.

Legacy datasets without confirmed extraction labels remain runnable. They continue to report decision metrics, while extraction accuracy remains unavailable rather than being inferred from model confidence.

## Calibration and out-of-sample sets

Do not keep adding corrected cases to the same benchmark and then claim generalisation.

- **Benchmark v2** is the completed calibration set. It was used to diagnose and correct extraction, scoring, and decision-gate failures.
- **Benchmark v3** must contain only entirely new opportunities that were not used to design v0.9–v0.12.
- Select only the new cases in the labelling workspace before freezing v3.

A useful first v3 target is at least ten new opportunities with a varied decision distribution, such as three `PURSUE`, four `HOLD`, and three `REJECT` cases.

## Readiness rules

A dataset is decision-comparison-ready when it contains at least five cases, including:

- at least one `PURSUE` case; and
- at least one `HOLD` or `REJECT` case.

A dataset is extraction-ready when every frozen case has a confirmed extraction label.

Five cases can expose obvious failures but cannot establish stable production calibration. Aim for 12–20 varied cases before changing thresholds.

## Running a benchmark

Open **Evaluation** in the web workspace:

1. Analyse and explicitly decide new opportunities.
2. Select only the new cases intended for the next benchmark.
3. Expand every selected case and compare the extracted fields with the source.
4. Correct errors and confirm each extraction label.
5. Freeze the new immutable dataset.
6. Select **Run current mode**.
7. Review extraction metrics, decision metrics, and every case-level mismatch.
8. Download the complete JSON report for deeper inspection.

Evaluation runs use the currently deployed runtime mode. Mock mode makes no paid calls. Live mode uses the configured provider order and the same hard call and token ceilings as normal analysis.

Runs do not create new opportunity analyses and do not update personal memory. They are stored separately in `evaluation_runs`.

## Extraction metrics

- **Field accuracy**: correct labelled fields divided by all labelled fields.
- **Fully correct cases**: labelled cases where every checked field matched.
- **Per-field accuracy**: separate accuracy for title, company, type, remote status, location, skills, problems, and responsibilities.
- **Label coverage**: number of extraction-labelled cases and checked fields.

Extraction confidence is still displayed, but it is not treated as ground truth.

## Decision metrics and diagnostics

- **Decision accuracy**: exact agreement with the user's frozen decision.
- **Mean decision distance**: average ordinal distance on `REJECT → HOLD → PURSUE`.
- **False pursue rate**: non-pursue cases incorrectly promoted to `PURSUE`.
- **False reject rate**: frozen `PURSUE` cases incorrectly reduced to `REJECT`.
- **Underprediction rate**: cases where the system chose a more conservative action than the user.
- **Overprediction rate**: cases where the system chose a more aggressive action than the user.
- **Prediction counts and confusion matrix**: distribution of decisions and exact expected-versus-predicted combinations.
- **Evidence present rate**: completed cases with at least one captured evidence claim.
- **Critic pass rate**: completed cases without blocking grounding issues.
- **Hard-constraint accuracy**: optional manually labelled hard-constraint checks, when present.
- **Provider usage**: model calls, reported tokens, and number of cases that used fallback.

Each case also records dimension contributions, extraction confidence, extraction-field outcomes, critic issue codes, decision gates, and threshold margins.

A provider should not be promoted because of decision accuracy alone. Extraction accuracy, false-pursue behaviour, grounding failures, run failures, and cost must all remain acceptable.

## Exploratory threshold simulation

For a decision-comparison-ready dataset, OpportunityOS can search for a threshold pair that improves agreement while prioritising a low false-pursue rate. It compares the simulation with the current policy:

- `HOLD` at 45;
- `PURSUE` at 72;
- minimum extraction confidence of 0.60 for score-based `PURSUE`.

The simulation is diagnostic only. It does not alter production decisions, environment settings, profile memory, or stored analyses. Suggestions from fewer than 12 cases are explicitly marked unstable.

Threshold changes should be considered only after:

1. the benchmark contains enough varied, out-of-sample cases;
2. extraction quality is acceptable;
3. false-pursue behaviour remains safe;
4. case-level changes make sense, not only the aggregate percentage.

## Recommended provider comparison

1. Freeze an extraction-labelled out-of-sample dataset.
2. Run and preserve the mock baseline.
3. Inspect extraction failures and decision errors before spending model credits.
4. Enable OpenAI only, with fallback disabled, and rerun the identical dataset.
5. Enable Anthropic only and rerun it.
6. Compare exact cases, extraction fields, cost, and decisions.
7. Enable fallback only after both single-provider runs are understood.

The benchmark is personal by design. It should remain in the private PostgreSQL deployment and should not be committed to the public repository.
