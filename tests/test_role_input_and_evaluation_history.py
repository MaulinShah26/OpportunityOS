from fastapi.testclient import TestClient

from opportunityos.api.main import app

client = TestClient(app)


def _create_user() -> str:
    response = client.post(
        "/v1/profiles/onboard",
        json={
            "display_name": "Role Hint User",
            "headline": "Data and AI product operator",
            "resume_text": (
                "Senior data scientist and product analytics operator with Python, SQL, experimentation, "
                "retention and AI implementation experience."
            ),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["profile"]["user_id"]


def _analyse_and_decide(
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
                    "Remote consulting engagement. The person will improve product decisions, "
                    "retention workflows and practical AI implementation."
                ),
            }
        },
    )
    assert analysis.status_code == 200, analysis.text
    assert analysis.json()["opportunity"]["company_name"] == company
    assert analysis.json()["opportunity"]["title"] == role
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


def _label_for(user_id: str, analysis_id: str) -> dict:
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


def test_role_hint_is_authoritative_and_replayed_exactly() -> None:
    user_id = _create_user()
    role = "Senior Product Manager — AI and Data Products"
    analysis_id = _analyse_and_decide(
        user_id,
        company="Acme Products",
        role=role,
        action="pursue",
    )

    candidates = client.get(f"/v1/users/{user_id}/evaluation-candidates")
    assert candidates.status_code == 200, candidates.text
    candidate = next(
        item
        for item in candidates.json()["candidates"]
        if item["source_analysis_id"] == analysis_id
    )
    assert candidate["opportunity"]["role_hint"] == role
    assert candidate["current_extraction"]["title"] == role

    dataset = client.post(
        f"/v1/users/{user_id}/evaluation-datasets",
        json={
            "name": "Role input benchmark",
            "extraction_labels": [_label_for(user_id, analysis_id)],
        },
    )
    assert dataset.status_code == 201, dataset.text

    run = client.post(
        f"/v1/users/{user_id}/evaluation-datasets/{dataset.json()['dataset_id']}/runs"
    )
    assert run.status_code == 201, run.text
    case = run.json()["cases"][0]
    assert case["extracted_title"] == role
    assert case["extraction_field_results"]["title"] is True


def test_latest_endpoint_hides_older_revisions_without_changing_list_api() -> None:
    user_id = _create_user()
    first_analysis = _analyse_and_decide(
        user_id,
        company="First Company",
        role="Fractional Data Product Lead",
        action="pursue",
    )
    base = client.post(
        f"/v1/users/{user_id}/evaluation-datasets",
        json={
            "name": "Opportunity benchmark v3",
            "extraction_labels": [_label_for(user_id, first_analysis)],
        },
    )
    assert base.status_code == 201, base.text

    second_analysis = _analyse_and_decide(
        user_id,
        company="Second Company",
        role="AI Product Strategy Consultant",
        action="save",
    )
    extended = client.post(
        f"/v1/users/{user_id}/evaluation-datasets/{base.json()['dataset_id']}/extend",
        json={"extraction_labels": [_label_for(user_id, second_analysis)]},
    )
    assert extended.status_code == 201, extended.text

    latest = client.get(f"/v1/users/{user_id}/evaluation-datasets/latest")
    assert latest.status_code == 200, latest.text
    assert len(latest.json()["datasets"]) == 1
    assert latest.json()["datasets"][0]["revision"] == 2
    assert latest.json()["datasets"][0]["case_count"] == 2

    default_list = client.get(f"/v1/users/{user_id}/evaluation-datasets")
    assert default_list.status_code == 200, default_list.text
    assert [item["revision"] for item in default_list.json()["datasets"]] == [2, 1]

    history = client.get(f"/v1/users/{user_id}/evaluation-datasets/history")
    assert history.status_code == 200, history.text
    assert [item["revision"] for item in history.json()["datasets"]] == [2, 1]


def test_web_shell_exposes_role_and_history_controls() -> None:
    shell = client.get("/app/")
    evaluation_script = client.get("/static/evaluation.js")
    app_script = client.get("/static/app.js")

    assert shell.status_code == 200
    assert 'name="role_hint"' in shell.text
    assert "Known role titles are authoritative" in shell.text
    assert 'id="toggle-evaluation-history-button"' in shell.text

    assert evaluation_script.status_code == 200
    assert "Show revision history" in shell.text
    assert "generated placeholder title" in evaluation_script.text
    assert "/evaluation-datasets/latest" in evaluation_script.text
    assert "/evaluation-datasets/history" in evaluation_script.text

    assert app_script.status_code == 200
    assert '"role_hint"' in app_script.text
