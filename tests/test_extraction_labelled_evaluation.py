from fastapi.testclient import TestClient

from opportunityos.api.main import app
from opportunityos.application.factory import build_analysis_service
from opportunityos.config import Settings
from opportunityos.domain.enums import Decision, OpportunityType
from opportunityos.domain.models import OpportunityInput
from opportunityos.evaluation.models import EvaluationCase, EvaluationDataset
from opportunityos.evaluation.service import evaluate_dataset

client = TestClient(app)


def test_confirmed_extraction_labels_measure_fields_and_full_cases(strong_profile) -> None:
    dataset = EvaluationDataset(
        name="Extraction-labelled benchmark",
        profile=strong_profile,
        cases=[
            EvaluationCase(
                case_id="labelled-fractional",
                name="Acme — Fractional Data and AI Lead",
                opportunity=OpportunityInput(
                    raw_text=(
                        "Company: Acme\n"
                        "Role: Fractional Data and AI Lead\n"
                        "Location: Remote\n"
                        "Need product analytics, retention and AI support."
                    )
                ),
                expected_decision=Decision.PURSUE,
                extraction_label_confirmed=True,
                expected_company_name="Acme",
                expected_title="Fractional Data and AI Lead",
                expected_opportunity_type=OpportunityType.FRACTIONAL,
                expected_remote_allowed=True,
                expected_location="Remote",
                expected_required_skills=["product analytics", "retention", "ai"],
                expected_problem_areas=["Retention improvement"],
                expected_responsibilities=[
                    "Retention improvement",
                    "product analytics",
                    "retention",
                    "ai",
                ],
            )
        ],
    )

    report = evaluate_dataset(
        dataset,
        build_analysis_service(Settings(_env_file=None, llm_mode="mock")),
        mode="mock",
        provider_order="mock",
    )

    assert report.metrics.extraction_labelled_case_count == 1
    assert report.metrics.extraction_field_count == 8
    assert report.metrics.extraction_accuracy == 1.0
    assert report.metrics.extraction_case_accuracy == 1.0
    assert report.metrics.extraction_field_accuracy["title"] == 1.0
    assert report.cases[0].extraction_correct is True
    assert all(report.cases[0].extraction_field_results.values())


def test_confirmed_extraction_labels_expose_hidden_mismatch(strong_profile) -> None:
    dataset = EvaluationDataset(
        name="Extraction mismatch benchmark",
        profile=strong_profile,
        cases=[
            EvaluationCase(
                case_id="wrong-title",
                name="Acme case",
                opportunity=OpportunityInput(
                    raw_text="Company: Acme\nRole: Data Analyst\nNeed Excel and SQL."
                ),
                expected_decision=Decision.REJECT,
                extraction_label_confirmed=True,
                expected_company_name="Acme",
                expected_title="Senior Data Product Lead",
                expected_opportunity_type=OpportunityType.FULL_TIME,
                expected_remote_allowed=None,
                expected_location=None,
                expected_required_skills=["Excel"],
                expected_problem_areas=[],
                expected_responsibilities=["Excel"],
            )
        ],
    )

    report = evaluate_dataset(
        dataset,
        build_analysis_service(Settings(_env_file=None, llm_mode="mock")),
        mode="mock",
        provider_order="mock",
    )

    assert report.metrics.extraction_accuracy is not None
    assert report.metrics.extraction_accuracy < 1.0
    assert report.metrics.extraction_case_accuracy == 0.0
    assert report.cases[0].extraction_correct is False
    assert report.cases[0].extraction_field_results["title"] is False
    assert report.cases[0].extraction_field_results["opportunity_type"] is False


def test_api_lists_candidates_and_freezes_only_selected_confirmed_cases() -> None:
    onboarding = client.post(
        "/v1/profiles/onboard",
        json={
            "display_name": "Extraction Evaluation User",
            "headline": "Fractional Data and AI lead",
            "resume_text": "Senior data scientist with product analytics, retention, Python, SQL and AI experience.",
        },
    )
    assert onboarding.status_code == 201, onboarding.text
    user_id = onboarding.json()["profile"]["user_id"]

    analysis_ids: list[str] = []
    for raw_text, action in (
        (
            "Company: Acme\nRole: Fractional Data and AI Lead\nLocation: Remote\nNeed product analytics and retention.",
            "pursue",
        ),
        (
            "Company: Office Co\nRole: Data Analyst\nLocation: Onsite\nNeed Excel reporting.",
            "reject",
        ),
    ):
        analysis = client.post(
            f"/v1/users/{user_id}/analyses",
            json={"opportunity": {"raw_text": raw_text}},
        )
        assert analysis.status_code == 200, analysis.text
        analysis_id = analysis.json()["analysis_id"]
        analysis_ids.append(analysis_id)
        feedback = client.post(
            f"/v1/users/{user_id}/feedback",
            json={
                "feedback": {
                    "analysis_id": analysis_id,
                    "action": action,
                    "reasons": ["strong_fit" if action == "pursue" else "too_execution_heavy"],
                    "explicit": True,
                }
            },
        )
        assert feedback.status_code == 200, feedback.text

    candidates_response = client.get(f"/v1/users/{user_id}/evaluation-candidates")
    assert candidates_response.status_code == 200, candidates_response.text
    candidates = candidates_response.json()["candidates"]
    assert len(candidates) == 2

    selected = next(item for item in candidates if item["source_analysis_id"] == analysis_ids[0])
    created = client.post(
        f"/v1/users/{user_id}/evaluation-datasets-labelled",
        json={
            "name": "Out-of-sample benchmark v3",
            "extraction_labels": [
                {
                    "source_analysis_id": selected["source_analysis_id"],
                    "confirmed": True,
                    "expected_company_name": selected["extracted_company_name"],
                    "expected_title": selected["extracted_title"],
                    "expected_opportunity_type": selected["extracted_opportunity_type"],
                    "expected_remote_allowed": selected["extracted_remote_allowed"],
                    "expected_location": selected["extracted_location"],
                    "expected_required_skills": selected["extracted_required_skills"],
                    "expected_problem_areas": selected["extracted_problem_areas"],
                    "expected_responsibilities": selected["extracted_responsibilities"],
                }
            ],
        },
    )
    assert created.status_code == 201, created.text
    dataset = created.json()
    assert len(dataset["cases"]) == 1
    assert dataset["cases"][0]["source_analysis_id"] == selected["source_analysis_id"]
    assert dataset["cases"][0]["extraction_label_confirmed"] is True

    listed = client.get(f"/v1/users/{user_id}/evaluation-datasets")
    assert listed.status_code == 200, listed.text
    summary = next(item for item in listed.json()["datasets"] if item["dataset_id"] == dataset["dataset_id"])
    assert summary["extraction_labelled_case_count"] == 1
    assert summary["extraction_ready"] is True

    run = client.post(
        f"/v1/users/{user_id}/evaluation-datasets/{dataset['dataset_id']}/runs"
    )
    assert run.status_code == 201, run.text
    metrics = run.json()["metrics"]
    assert metrics["extraction_labelled_case_count"] == 1
    assert metrics["extraction_field_count"] == 8
    assert metrics["extraction_accuracy"] == 1.0
    assert metrics["extraction_case_accuracy"] == 1.0


def test_web_shell_contains_extraction_labelling_workspace() -> None:
    response = client.get("/app/")

    assert response.status_code == 200
    assert 'id="evaluation-candidates"' in response.text
    assert "Freeze labelled dataset" in response.text
