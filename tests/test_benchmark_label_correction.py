from fastapi.testclient import TestClient

from opportunityos.api.main import app

client = TestClient(app)


def _create_user() -> str:
    response = client.post(
        "/v1/profiles/onboard",
        json={
            "display_name": "Benchmark Correction User",
            "headline": "Fractional Data and AI lead",
            "resume_text": "Senior data scientist with product analytics, Python, SQL and AI experience.",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["profile"]["user_id"]


def _create_decided_analysis(
    user_id: str,
    *,
    company: str,
    role: str,
    action: str,
) -> str:
    analysis = client.post(
        f"/v1/users/{user_id}/analyses",
        json={
            "opportunity": {
                "company_hint": company,
                "role_hint": role,
                "raw_text": (
                    f"Company: {company}\n"
                    f"Role: {role}\n"
                    "Location: Remote\n"
                    "Need product analytics, retention and AI support.\n"
                    "Responsibilities: improve retention decisions and product analytics workflows."
                ),
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
                "action": action,
                "reasons": ["strong_fit" if action == "pursue" else "missing_information"],
                "explicit": True,
            }
        },
    )
    assert feedback.status_code == 200, feedback.text
    return analysis_id


def _candidate_label(user_id: str, analysis_id: str) -> dict:
    response = client.get(f"/v1/users/{user_id}/evaluation-candidates")
    assert response.status_code == 200, response.text
    candidate = next(
        item
        for item in response.json()["candidates"]
        if item["source_analysis_id"] == analysis_id
    )
    return {
        "source_analysis_id": analysis_id,
        "expected": candidate["current_extraction"],
    }


def _freeze_dataset(user_id: str, analysis_ids: list[str]) -> dict:
    response = client.post(
        f"/v1/users/{user_id}/evaluation-datasets",
        json={
            "name": "Opportunity benchmark v3",
            "extraction_labels": [_candidate_label(user_id, analysis_id) for analysis_id in analysis_ids],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _correction(case: dict, *, title: str | None = None, decision: str | None = None) -> dict:
    return {
        "case_id": case["case_id"],
        "expected_decision": decision or case["expected_decision"],
        "expected": {
            "company_name": case["expected_company_name"],
            "title": title if title is not None else case["expected_title"],
            "opportunity_type": case["expected_opportunity_type"],
            "location": case["expected_location"],
            "remote_allowed": case["expected_remote_allowed"],
            "required_skills": case["expected_required_skills"],
            "problem_areas": case["expected_problem_areas"],
            "responsibilities": case["expected_responsibilities"],
        },
    }


def test_label_correction_creates_new_revision_and_preserves_original() -> None:
    user_id = _create_user()
    analysis_id = _create_decided_analysis(
        user_id,
        company="Acme Consumer",
        role="Consulting opportunity",
        action="pursue",
    )
    base = _freeze_dataset(user_id, [analysis_id])
    base_case = base["cases"][0]

    response = client.post(
        f"/v1/users/{user_id}/evaluation-datasets/{base['dataset_id']}/correct",
        json={
            "reason": "Replaced the generated placeholder with the title supported by the original source.",
            "corrections": [
                _correction(
                    base_case,
                    title="Fractional Data and AI Advisor",
                    decision="hold",
                )
            ],
        },
    )

    assert response.status_code == 201, response.text
    corrected = response.json()
    assert corrected["schema_version"] == "1.4"
    assert corrected["revision"] == 2
    assert corrected["parent_dataset_ids"] == [base["dataset_id"]]
    assert corrected["revision_reason"].startswith("Replaced the generated placeholder")
    assert corrected["source"] == "corrected_frozen_dataset_labels"
    assert corrected["profile"] == base["profile"]
    assert corrected["cases"][0]["expected_title"] == "Fractional Data and AI Advisor"
    assert corrected["cases"][0]["expected_decision"] == "hold"
    assert corrected["cases"][0]["opportunity"] == base_case["opportunity"]

    original = client.get(
        f"/v1/users/{user_id}/evaluation-datasets/{base['dataset_id']}"
    )
    assert original.status_code == 200, original.text
    assert original.json()["revision"] == 1
    assert original.json()["cases"][0]["expected_title"] == "Consulting opportunity"
    assert original.json()["cases"][0]["expected_decision"] == "pursue"


def test_label_correction_requires_every_case() -> None:
    user_id = _create_user()
    first_id = _create_decided_analysis(
        user_id,
        company="First Company",
        role="Data and AI Advisor",
        action="pursue",
    )
    second_id = _create_decided_analysis(
        user_id,
        company="Second Company",
        role="Project Management Specialist",
        action="save",
    )
    base = _freeze_dataset(user_id, [first_id, second_id])

    response = client.post(
        f"/v1/users/{user_id}/evaluation-datasets/{base['dataset_id']}/correct",
        json={
            "reason": "Reviewing the benchmark labels against the original source.",
            "corrections": [_correction(base["cases"][0], title="Corrected title")],
        },
    )

    assert response.status_code == 409, response.text
    assert "submit every case" in response.json()["detail"]


def test_label_correction_rejects_noop_revision() -> None:
    user_id = _create_user()
    analysis_id = _create_decided_analysis(
        user_id,
        company="No-op Company",
        role="Senior Data Scientist",
        action="save",
    )
    base = _freeze_dataset(user_id, [analysis_id])

    response = client.post(
        f"/v1/users/{user_id}/evaluation-datasets/{base['dataset_id']}/correct",
        json={
            "reason": "Reviewed the labels and found no corrections were necessary.",
            "corrections": [_correction(base["cases"][0])],
        },
    )

    assert response.status_code == 409, response.text
    assert "No benchmark labels changed" in response.json()["detail"]


def test_web_workspace_exposes_source_backed_correction_flow() -> None:
    script = client.get("/static/evaluation.js")
    assert script.status_code == 200
    assert "Correct benchmark labels" in script.text
    assert "Original frozen source" in script.text
    assert "Reviewed against source" in script.text
    assert "/correct" in script.text
    assert "Correction reason" in script.text
