from fastapi.testclient import TestClient

from opportunityos.api.main import app

client = TestClient(app)


def test_application_shell_includes_evaluation_workspace() -> None:
    response = client.get("/app")

    assert response.status_code == 200
    html = response.text
    assert 'data-view="evaluation-view"' in html
    assert 'id="evaluation-view"' in html
    assert 'id="evaluation-dataset-form"' in html
    assert 'id="refresh-evaluations-button"' in html
    assert 'id="evaluation-datasets"' in html
    assert 'id="evaluation-report"' in html
    assert '<script src="/static/evaluation.js" defer></script>' in html


def test_evaluation_script_is_served() -> None:
    response = client.get("/static/evaluation.js")

    assert response.status_code == 200
    assert "function bindEvaluationEvents()" in response.text
