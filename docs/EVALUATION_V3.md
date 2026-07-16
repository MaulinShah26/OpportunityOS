# Opportunity benchmark v3

Benchmark v2 is the calibration set. Its cases must not be reused in benchmark v3.

## Build the out-of-sample set

1. Analyse at least ten new real opportunities after v0.12.1 is deployed.
2. Record an explicit decision and reason for every opportunity.
3. In Evaluation, choose **Review new extraction labels**.
4. OpportunityOS excludes analyses already present in any earlier frozen dataset.
5. Confirm every selected case against its original source:
   - company;
   - title;
   - opportunity type;
   - location and remote status;
   - required skills;
   - problem areas;
   - responsibilities or workflows.
6. Remove values that are inferred, irrelevant, or absent from the source.
7. Freeze the reviewed cases as `Opportunity benchmark v3`.
8. Run mock mode once and preserve the report before changing extraction or scoring logic.

## Metrics

Decision quality and extraction quality are separate:

- decision accuracy measures agreement with the user's frozen pursue, hold, or reject decision;
- extraction field accuracy measures all reviewed field checks individually;
- fully correct case accuracy requires every reviewed extraction field in a case to match;
- per-field accuracy identifies whether title, type, work mode, skills, problems, or responsibilities are failing.

A case may have the correct final decision and still fail extraction. Do not treat decision accuracy as proof that the underlying opportunity representation is correct.

## Product guardrail

Extraction-labelled datasets reject any analysis that already belongs to an earlier frozen dataset. This prevents tuning on benchmark v2 and then presenting the same cases as out-of-sample evidence.
