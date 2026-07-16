from uuid import UUID

from fastapi.testclient import TestClient

from opportunityos.api.dependencies import get_database
from opportunityos.api.main import app
from opportunityos.evaluation.models import EvaluationDataset
from opportunityos.infrastructure.database.models import EvaluationDatasetRecord

client = TestClient(app)


def _create_user() -> str:
    onboarding = client.post(
        "/v1/profiles/onboard",
        json={
            "display_name": "Extraction Label User",
            "headline": "Fractional Data and AI lead",
            "resume_text": "Senior data scientist with product analytics, Python, SQL and AI experience.",
        },
    )
    assert onboarding.status_code == 201, onboarding.text
    return onboarding.json()["profile"]["user_id"]


def _create_decided_analysis(
    user_id: str,
    *,
    company: str = "Acme Consumer",
    role: str = "Fractional Data and AI Lead",
    action: str = "pursue",
) -> str:
    analysis = client.post(
        f"/v1/users/{user_id}/analyses",
        json={
            "opportunity": {
                "raw_text": (
                    f"Company: {company}\n"
                    f"Role: {role}\n"
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
                "action": action,
                "reasons": ["strong_fit" if action == "pursue" else "missing_information"],
                "explicit": True,
            }
        },
    )
    assert feedback.status_code == 200, feedback.text
    return analysis_id


def _reviewed_label(user_id: str, analysis_id: str) -> dict:
    candidates = client.get(f"/v1/users/{user_id}/evaluation-candidates")
    assert candidates.status_code == 200, candidates.text
    candidate = next(
        item
        for item in candidates.json()["candidates"]
        if item["source_analysis_id"] == analysis_id
    )
    return {
        "source_analysis_id": analysis_id,
        "expected": candidate["current_extraction"],
    }


def _freeze(user_id: str, name: str, analysis_id: str) -> dict:
    created = client.post(
        f"/v1/users/{user_id}/evaluation-datasets",
        json={"name": name, "extraction_labels": [_reviewed_label(user_id, analysis_id)]},
    )
    assert created.status_code == 201, created.text
    return created.json()


def test_reviewed_extraction_labels_are_frozen_and_scored() -> None:
    user_id = _create_user()
    analysis_id = _create_decided_analysis(user_id)

    candidates = client.get(f"/v1/users/{user_id}/evaluation-candidates")
    assert candidates.status_code == 200, candidates.text
    candidate = candidates.json()["candidates"][0]
    assert candidate["source_analysis_id"] == analysis_id
    assert candidate["current_extraction"]["title"] == "Fractional Data and AI Lead"
    assert candidate["previously_frozen"] is False

    dataset = _freeze(user_id, "Extraction benchmark v1", analysis_id)
    assert dataset["schema_version"] == "1.3"
    assert dataset["revision"] == 1
    assert dataset["parent_dataset_ids"] == []
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


def test_duplicate_dataset_name_requires_extension() -> None:
    user_id = _create_user()
    first_analysis_id = _create_decided_analysis(user_id)
    _freeze(user_id, "Opportunity benchmark v3", first_analysis_id)

    second_analysis_id = _create_decided_analysis(
        user_id,
        company="Second Company",
        role="AI Product Strategy Consultant",
        action="save",
    )
    duplicate = client.post(
        f"/v1/users/{user_id}/evaluation-datasets",
        json={
            "name": "  opportunity   BENCHMARK v3 ",
            "extraction_labels": [_reviewed_label(user_id, second_analysis_id)],
        },
    )

    assert duplicate.status_code == 409, duplicate.text
    assert "Use Extend" in duplicate.json()["detail"]


def test_extend_dataset_creates_new_immutable_revision() -> None:
    user_id = _create_user()
    first_analysis_id = _create_decided_analysis(user_id)
    base = _freeze(user_id, "Opportunity benchmark v3", first_analysis_id)

    second_analysis_id = _create_decided_analysis(
        user_id,
        company="Second Company",
        role="AI Product Strategy Consultant",
        action="save",
    )
    extended_response = client.post(
        f"/v1/users/{user_id}/evaluation-datasets/{base['dataset_id']}/extend",
        json={"extraction_labels": [_reviewed_label(user_id, second_analysis_id)]},
    )
    assert extended_response.status_code == 201, extended_response.text
    extended = extended_response.json()

    assert extended["name"] == "Opportunity benchmark v3"
    assert extended["revision"] == 2
    assert extended["parent_dataset_ids"] == [base["dataset_id"]]
    assert len(extended["cases"]) == 2
    assert {item["source_analysis_id"] for item in extended["cases"]} == {
        first_analysis_id,
        second_analysis_id,
    }

    unchanged_base = client.get(
        f"/v1/users/{user_id}/evaluation-datasets/{base['dataset_id']}"
    )
    assert unchanged_base.status_code == 200, unchanged_base.text
    assert len(unchanged_base.json()["cases"]) == 1

    summaries = client.get(f"/v1/users/{user_id}/evaluation-datasets").json()["datasets"]
    revisions = {item["dataset_id"]: item["revision"] for item in summaries}
    assert revisions[base["dataset_id"]] == 1
    assert revisions[extended["dataset_id"]] == 2


def test_merge_legacy_split_snapshots_creates_union_revision() -> None:
    user_id = _create_user()
    first_analysis_id = _create_decided_analysis(user_id)
    first = _freeze(user_id, "Opportunity benchmark v3", first_analysis_id)

    second_analysis_id = _create_decided_analysis(
        user_id,
        company="Second Company",
        role="AI Product Strategy Consultant",
        action="save",
    )
    second = _freeze(user_id, "Temporary v3 part two", second_analysis_id)

    with get_database().session() as session:
        record = session.get(EvaluationDatasetRecord, second["dataset_id"])
        assert record is not None
        legacy_dataset = EvaluationDataset.model_validate(record.dataset_json)
        legacy_dataset.name = "Opportunity benchmark v3"
        record.name = legacy_dataset.name
        record.dataset_json = legacy_dataset.model_dump(mode="json")

    merged_response = client.post(
        f"/v1/users/{user_id}/evaluation-datasets/merge",
        json={"source_dataset_ids": [first["dataset_id"], second["dataset_id"]]},
    )
    assert merged_response.status_code == 201, merged_response.text
    merged = merged_response.json()

    assert merged["name"] == "Opportunity benchmark v3"
    assert merged["revision"] == 3
    assert merged["parent_dataset_ids"] == [first["dataset_id"], second["dataset_id"]]
    assert len(merged["cases"]) == 2
    assert {item["source_analysis_id"] for item in merged["cases"]} == {
        first_analysis_id,
        second_analysis_id,
    }

    for original in (first, second):
        unchanged = client.get(
            f"/v1/users/{user_id}/evaluation-datasets/{original['dataset_id']}"
        )
        assert unchanged.status_code == 200, unchanged.text
        assert len(unchanged.json()["cases"]) == 1


def test_extraction_labelled_dataset_cannot_reuse_a_frozen_analysis() -> None:
    user_id = _create_user()
    analysis_id = _create_decided_analysis(user_id)
    payload = {"extraction_labels": [_reviewed_label(user_id, analysis_id)]}

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
    assert "already belong" in second.json()["detail"]


def test_evaluation_shell_exposes_revision_and_merge_flow() -> None:
    response = client.get("/app/")
    assert response.status_code == 200
    evaluation_script = client.get("/static/evaluation.js")
    assert evaluation_script.status_code == 200
    assert "Review new extraction labels" in evaluation_script.text
    assert "Extend with new cases" in evaluation_script.text
    assert "Combine split benchmark snapshots" in evaluation_script.text
    assert "/evaluation-datasets/merge" in evaluation_script.text
    assert "/extend" in evaluation_script.text
    assert "responsibilities" in evaluation_script.text
    assert "fully correct cases" in evaluation_script.text
