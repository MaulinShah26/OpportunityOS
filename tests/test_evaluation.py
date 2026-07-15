from fastapi.testclient import TestClient

from opportunityos.api.main import app
from opportunityos.application.factory import build_analysis_service
from opportunityos.config import Settings
from opportunityos.domain.enums import Decision
from opportunityos.domain.models import OpportunityInput
from opportunityos.evaluation.models import EvaluationCase, EvaluationDataset
from opportunityos.evaluation.service import evaluate_dataset

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
