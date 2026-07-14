from fastapi.testclient import TestClient

from opportunityos.api.main import app

client = TestClient(app)


def test_root_redirects_to_web_workspace() -> None:
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/app"


def test_web_workspace_is_served() -> None:
    response = client.get("/app")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "OpportunityOS" in response.text
    assert 'id="onboarding-form"' in response.text
    assert 'id="analysis-form"' in response.text
    assert 'id="memory-content"' in response.text
    assert 'id="audit-content"' in response.text


def test_static_assets_are_served() -> None:
    stylesheet = client.get("/static/base.css")
    components = client.get("/static/components.css")
    script = client.get("/static/app.js")
    analysis = client.get("/static/analysis.js")
    memory = client.get("/static/memory.js")

    assert stylesheet.status_code == 200
    assert "--accent" in stylesheet.text
    assert components.status_code == 200
    assert ".result-hero" in components.text
    assert script.status_code == 200
    assert analysis.status_code == 200
    assert "renderAnalysis" in analysis.text
    assert memory.status_code == 200
    assert "loadMemory" in memory.text
