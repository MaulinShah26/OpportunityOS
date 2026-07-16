from fastapi.testclient import TestClient

from opportunityos.api.main import app

client = TestClient(app)


def test_reviewed_extraction_labels_are_frozen_and_scored() -> None:
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

    candidates = client.get(f"/v1/users/{user_id}/evaluation-candidates")
    assert candidates.status_code == 200, candidates.text
    candidate = candidates.json()["candidates"][0]
    assert candidate["source_analysis_id"] == analysis_id
    assert candidate["current_extraction"]["title"] == "Fractional Data and AI Lead"

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
                        "remote_allowed": True,
                        "required_skills": ["product analytics", "retention", "ai"],
                        "problem_areas": ["Retention improvement"],
                    },
                }
            ],
        },
    )
    assert created.status_code == 201, created.text
    dataset = created.json()
    assert dataset["schema_version"] == "1.1"
    assert dataset["cases"][0]["expected_title"] == "Fractional Data and AI Lead"

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
    assert report["metrics"]["extraction_accuracy_by_field"]["title"] == 1.0
    assert all(report["cases"][0]["extraction_field_results"].values())
