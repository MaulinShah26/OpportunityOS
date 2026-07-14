from fastapi.testclient import TestClient

from opportunityos.api.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_analysis_endpoint() -> None:
    payload = {
        "profile": {
            "display_name": "Test User",
            "headline": "Fractional Data and AI lead",
            "capabilities": [
                {"name": "product analytics", "proficiency": 0.9},
                {"name": "retention", "proficiency": 0.9},
                {"name": "ai", "proficiency": 0.8},
            ],
            "preferences": [
                {"key": "fractional", "weight": 0.95},
                {"key": "remote", "weight": 0.9},
            ],
            "constraints": [],
            "aspirations": [{"name": "data ai leadership", "weight": 0.9}],
        },
        "opportunity": {
            "raw_text": (
                "Company: Acme Consumer\n"
                "Role: Fractional Data and AI Lead\n"
                "Location: Remote\n"
                "Need product analytics, retention and AI support."
            )
        },
    }
    response = client.post("/v1/analyses", json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["opportunity"]["company_name"] == "Acme Consumer"
    assert body["fit_score"]["total"] >= 0
    assert body["recommendation"]["decision"] in {"pursue", "hold", "reject"}


def test_persistent_onboarding_analysis_and_feedback() -> None:
    onboarding = client.post(
        "/v1/profiles/onboard",
        json={
            "display_name": "Persistent User",
            "headline": "Fractional Data and AI lead",
            "resume_text": (
                "Senior data scientist with product analytics, retention, growth, "
                "experimentation, Python and SQL experience."
            ),
            "preferences": [
                {"key": "engagement:fractional", "weight": 0.95},
                {"key": "remote", "weight": 0.9},
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

    stored = client.get(f"/v1/users/{user_id}/analyses/{analysis_id}")
    assert stored.status_code == 200
    assert stored.json()["analysis_id"] == analysis_id

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
    assert feedback.json()["applied_updates"]

    activity = client.get(f"/v1/users/{user_id}/activity")
    assert activity.status_code == 200
    assert activity.json()["analysis_count"] == 1


def test_txt_resume_upload_onboarding() -> None:
    response = client.post(
        "/v1/profiles/onboard-file",
        data={"display_name": "Uploaded User", "headline": "Product analytics leader"},
        files={
            "file": (
                "resume.txt",
                (
                    "Senior data scientist with product analytics, retention, growth, "
                    "experimentation, Python and SQL experience."
                ),
                "text/plain",
            )
        },
    )
    assert response.status_code == 201, response.text
    assert "product analytics" in response.json()["inferred_capabilities"]
