from fastapi.testclient import TestClient

from opportunityos.api.main import app

client = TestClient(app)


def _create_decided_analysis() -> tuple[str, str]:
    onboarding = client.post(
        "/v1/profiles/onboard",
        json={
            "display_name": "Extraction Label User",
            "headline": "Fractional Data and AI lead",
            "resume_text": "Senior data scientist with product analytics, Python, SQL and AI experience.",
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
                    "Need product analytics, retention and AI support.\n"
                    "Responsibilities: improve retention decisions and product analytics workflows."
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
    return user_id, analysis_id


def test_reviewed_extraction_labels_are_frozen_and_scored() -> None:
    user_id, analysis_id = _create_decided_analysis()

    candidates = client.get(f"/v1/users/{user_id}/evaluation-candidates")
    assert candidates.status_code == 200, candidates.text
    candidate = candidates.json()["candidates"][0]
    assert candidate["source_analysis_id"] == analysis_id
    assert candidate["current_extraction"]["title"] == "Fractional Data and AI Lead"
    assert candidate["previously_frozen"] is False

    created = client.post(
        f"/v1/users/{user_id}/evaluation-datasets",
        json={
            "name": "Extraction benchmark v1",
            "extraction_labels": [
                {
                    "source_analysis_id": analysis_id,
                    "expected": {
                        "company_name": "Acme Consumer",
                        "title": "Fractional Data and AI Lead",
                        "opportunity_type": "fractional",
                        "location": "Remote",
                        "remote_allowed": True,
                        "required_skills": ["product analytics", "retention", "ai"],
                        "problem_areas": ["Retention improvement"],
                        "responsibilities": ["Retention improvement", "product analytics", "retention", "ai"],
                    },
                }
            ],
        },
    )
    assert created.status_code == 201, created.text
    dataset = created.json()
    assert dataset["schema_version"] == "1.2"
    assert dataset["cases"][0]["expected_title"] == "Fractional Data and AI Lead"
    assert dataset["cases"][0]["expected_location"] == "Remote"
    assert dataset["cases"][0]["expected_responsibilities"]

    listed = client.get(f"/v1/users/{user_id}/evaluation-datasets")
    assert listed.status_code == 200, listed.text
    assert listed.json()["datasets"][0]["extraction_label_count"] == 1

    run = client.post(
        f"/v1/users/{user_id}/evaluation-datasets/{dataset['dataset_id']}/runs"
    )
    assert run.status_code == 201, run.text
    report = run.json()
    assert report["metrics"]["extraction_labelled_case_count"] == 1
    assert report["metrics"]["extraction_accuracy"] == 1.0
    assert report["metrics"]["extraction_case_accuracy"] == 1.0
    assert report["metrics"]["extraction_accuracy_by_field"]["location"] == 1.0
    assert report["metrics"]["extraction_accuracy_by_field"]["responsibilities"] == 1.0
    assert report["cases"][0]["extraction_case_correct"] is True
    assert all(report["cases"][0]["extraction_field_results"].values())

    refreshed = client.get(f"/v1/users/{user_id}/evaluation-candidates")
    assert refreshed.status_code == 200, refreshed.text
    frozen_candidate = refreshed.json()["candidates"][0]
    assert frozen_candidate["previously_frozen"] is True
    assert frozen_candidate["previous_dataset_names"] == ["Extraction benchmark v1"]


def test_extraction_labelled_dataset_cannot_reuse_a_frozen_analysis() -> None:
    user_id, analysis_id = _create_decided_analysis()
    payload = {
        "extraction_labels": [
            {
                "source_analysis_id": analysis_id,
                "expected": {
                    "company_name": "Acme Consumer",
                    "title": "Fractional Data and AI Lead",
                },
            }
        ]
    }

    first = client.post(
        f"/v1/users/{user_id}/evaluation-datasets",
        json={"name": "Calibration dataset", **payload},
    )
    assert first.status_code == 201, first.text

    second = client.post(
        f"/v1/users/{user_id}/evaluation-datasets",
        json={"name": "Out-of-sample dataset", **payload},
    )
    assert second.status_code == 409, second.text
    assert "already frozen" in second.json()["detail"]


def test_evaluation_shell_requires_reviewed_new_cases() -> None:
    response = client.get("/app/")
    assert response.status_code == 200
    evaluation_script = client.get("/static/evaluation.js")
    assert evaluation_script.status_code == 200
    assert "Review new extraction labels" in evaluation_script.text
    assert "previously_frozen" in evaluation_script.text
    assert "responsibilities" in evaluation_script.text
    assert "fully correct cases" in evaluation_script.text
