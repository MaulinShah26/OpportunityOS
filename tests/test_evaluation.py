from fastapi.testclient import TestClient

from opportunityos.api.main import app
from opportunityos.application.factory import build_analysis_service
from opportunityos.config import Settings
from opportunityos.domain.enums import Decision
from opportunityos.domain.models import OpportunityInput
from opportunityos.evaluation.models import EvaluationCase, EvaluationCaseResult, EvaluationDataset
from opportunityos.evaluation.service import _threshold_simulation, evaluate_dataset

client = TestClient(app)


def test_mock_evaluation_reports_decision_and_constraint_metrics(strong_profile) -> None:
    dataset = EvaluationDataset(
        name="Deterministic benchmark",
        profile=strong_profile,
        cases=[
            EvaluationCase(
                case_id="strong-fractional-fit",
                name="Strong fractional fit",
                opportunity=OpportunityInput(
                    raw_text=(
                        "Company: Acme Consumer\n"
                        "Role: Fractional Data and AI Lead\n"
                        "Location: Remote\n"
                        "Need product analytics, retention and AI support."
                    )
                ),
                expected_decision=Decision.PURSUE,
                expected_opportunity_type="fractional",
                expected_remote_allowed=True,
                expected_required_skills=["product analytics", "retention", "ai"],
                expected_hard_constraint_breach=False,
            ),
            EvaluationCase(
                case_id="onsite-hard-breach",
                name="Onsite hard constraint",
                opportunity=OpportunityInput(
                    raw_text=(
                        "Company: Office Co\n"
                        "Role: Full-time Data Analyst\n"
                        "Location: Onsite\n"
                        "Need analytics and Python execution."
                    )
                ),
                expected_decision=Decision.REJECT,
                expected_opportunity_type="full_time",
                expected_remote_allowed=False,
                expected_hard_constraint_breach=True,
            ),
        ],
    )
    settings = Settings(_env_file=None, llm_mode="mock")
    report = evaluate_dataset(
        dataset,
        build_analysis_service(settings),
        mode="mock",
        provider_order="mock",
    )

    assert report.metrics.completed_count == 2
    assert report.metrics.failed_count == 0
    assert report.metrics.decision_accuracy == 1.0
    assert report.metrics.false_pursue_rate == 0.0
    assert report.metrics.hard_constraint_accuracy == 1.0
    assert report.metrics.extraction_accuracy == 1.0
    assert sum(report.metrics.prediction_labels.values()) == 2
    assert report.metrics.underprediction_rate == 0.0
    assert report.metrics.overprediction_rate == 0.0
    assert report.threshold_simulation is None
    assert report.decision_policy.hold_threshold == 45
    assert report.decision_policy.pursue_threshold == 72
    assert report.cases[0].fit_dimensions
    assert report.cases[0].fit_contributions
    assert report.cases[0].extraction_confidence is not None


def test_threshold_simulation_surfaces_conservative_policy_candidate() -> None:
    results = [
        EvaluationCaseResult(
            case_id="reject",
            name="Reject case",
            expected_decision=Decision.REJECT,
            predicted_decision=Decision.HOLD,
            fit_score=47,
            extraction_confidence=0.8,
            actual_hard_constraint_breach=False,
        ),
        EvaluationCaseResult(
            case_id="hold-one",
            name="Hold one",
            expected_decision=Decision.HOLD,
            predicted_decision=Decision.HOLD,
            fit_score=46,
            extraction_confidence=0.8,
            actual_hard_constraint_breach=False,
        ),
        EvaluationCaseResult(
            case_id="pursue-one",
            name="Pursue one",
            expected_decision=Decision.PURSUE,
            predicted_decision=Decision.HOLD,
            fit_score=53,
            extraction_confidence=0.8,
            actual_hard_constraint_breach=False,
        ),
        EvaluationCaseResult(
            case_id="hold-two",
            name="Hold two",
            expected_decision=Decision.HOLD,
            predicted_decision=Decision.REJECT,
            fit_score=43,
            extraction_confidence=0.8,
            actual_hard_constraint_breach=False,
        ),
        EvaluationCaseResult(
            case_id="pursue-two",
            name="Pursue two",
            expected_decision=Decision.PURSUE,
            predicted_decision=Decision.HOLD,
            fit_score=50,
            extraction_confidence=0.8,
            actual_hard_constraint_breach=False,
        ),
    ]

    simulation = _threshold_simulation(results)

    assert simulation is not None
    assert simulation.hold_threshold == 43
    assert simulation.pursue_threshold == 50
    assert simulation.decision_accuracy == 0.8
    assert simulation.false_pursue_rate == 0.0
    assert simulation.changed_case_count == 3
    assert "Exploratory only" in simulation.sample_warning


def test_api_freezes_explicit_feedback_and_runs_same_dataset() -> None:
    onboarding = client.post(
        "/v1/profiles/onboard",
        json={
            "display_name": "Evaluation User",
            "headline": "Fractional Data and AI lead",
            "resume_text": (
                "Senior data scientist with product analytics, retention, growth, "
                "experimentation, Python, SQL and AI implementation experience."
            ),
            "preferences": [
                {"key": "engagement:fractional", "weight": 0.95},
                {"key": "work_mode:remote", "weight": 0.9},
            ],
            "aspirations": [{"name": "data ai leadership", "weight": 0.9}],
        },
    )
    assert onboarding.status_code == 201, onboarding.text
    user_id = onboarding.json()["profile"]["user_id"]

    analysis = client.post(
        f"/v1/users/{user_id}/analyses",
        json={
            "opportunity": {
                "raw_text": (
                    "Company: Acme Consumer\n"
                    "Role: Fractional Data and AI Lead\n"
                    "Location: Remote\n"
                    "Need product analytics, retention and AI support."
                )
            }
        },
    )
    assert analysis.status_code == 200, analysis.text
    analysis_id = analysis.json()["analysis_id"]

    feedback = client.post(
        f"/v1/users/{user_id}/feedback",
        json={
            "feedback": {
                "analysis_id": analysis_id,
                "action": "pursue",
                "reasons": ["strong_fit"],
                "explicit": True,
            }
        },
    )
    assert feedback.status_code == 200, feedback.text

    created = client.post(
        f"/v1/users/{user_id}/evaluation-datasets",
        json={"name": "User-labelled benchmark v1"},
    )
    assert created.status_code == 201, created.text
    dataset = created.json()
    dataset_id = dataset["dataset_id"]
    assert dataset["frozen"] is True
    assert len(dataset["cases"]) == 1
    assert dataset["cases"][0]["expected_decision"] == "pursue"
    assert dataset["cases"][0]["source_analysis_id"] == analysis_id

    listed = client.get(f"/v1/users/{user_id}/evaluation-datasets")
    assert listed.status_code == 200, listed.text
    summary = listed.json()["datasets"][0]
    assert summary["case_count"] == 1
    assert summary["decision_labels"] == {"pursue": 1}
    assert summary["ready_for_comparison"] is False

    run = client.post(
        f"/v1/users/{user_id}/evaluation-datasets/{dataset_id}/runs"
    )
    assert run.status_code == 201, run.text
    report = run.json()
    assert report["dataset_id"] == dataset_id
    assert report["mode"] == "mock"
    assert report["metrics"]["case_count"] == 1
    assert report["metrics"]["completed_count"] == 1
    assert report["decision_policy"] == {
        "hold_threshold": 45,
        "pursue_threshold": 72,
        "min_extraction_confidence": 0.6,
    }
    assert report["threshold_simulation"] is None
    assert report["cases"][0]["fit_contributions"]

    runs = client.get(
        f"/v1/users/{user_id}/evaluation-datasets/{dataset_id}/runs"
    )
    assert runs.status_code == 200, runs.text
    assert runs.json()["runs"][0]["run_id"] == report["run_id"]

    stored = client.get(
        f"/v1/users/{user_id}/evaluation-datasets/{dataset_id}/runs/{report['run_id']}"
    )
    assert stored.status_code == 200, stored.text
    assert stored.json()["metrics"] == report["metrics"]
