import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import get_settings
from app.db.session import get_engine, get_session_factory
from app.main import create_app


@pytest.mark.integration
def test_dataset_import_creates_dataset_version() -> None:
    database_url = os.getenv("LLMPROXY_TEST_DATABASE_URL")
    exports_path = os.getenv("LLMPROXY_TEST_EXPORTS_PATH")
    datasets_path = os.getenv("LLMPROXY_TEST_DATASETS_PATH")
    if not database_url or not exports_path or not datasets_path:
        pytest.skip("Required Phase 4 test environment variables are not set")

    os.environ["LLMPROXY_DATABASE_URL"] = database_url
    os.environ["LLMPROXY_EXPORTS_PATH"] = exports_path
    os.environ["LLMPROXY_DATASETS_PATH"] = datasets_path
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()

    app = create_app()
    client = TestClient(app)

    completion_response = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer change-me"},
        json={
            "model": "proxy-auto",
            "messages": [{"role": "user", "content": "Review this coding patch."}],
            "metadata": {
                "session_id": "sess_dataset_live",
                "domain_hint": "coding",
                "task_type_hint": "code_review",
            },
        },
    )
    assert completion_response.status_code == 200

    candidate_list = client.get(
        "/proxy/training-candidates",
        headers={"Authorization": "Bearer change-me"},
    ).json()
    candidate_id = candidate_list[0]["id"]

    approve_response = client.post(
        f"/proxy/training-candidates/{candidate_id}/approve",
        headers={"Authorization": "Bearer change-me"},
    )
    assert approve_response.status_code == 200

    export_response = client.post(
        "/proxy/export/jsonl",
        headers={"Authorization": "Bearer change-me"},
        json={"domain": "coding", "min_quality_score": 0.5},
    )
    assert export_response.status_code == 200
    export_payload = export_response.json()

    import_response = client.post(
        "/datasets/import",
        headers={"Authorization": "Bearer change-me"},
        json={
            "dataset_export_id": export_payload["dataset_export_id"],
            "manifest_path": export_payload["manifest_path"],
            "data_path": export_payload["data_path"],
        },
    )
    assert import_response.status_code == 200
    import_payload = import_response.json()
    assert import_payload["status"] == "imported"

    session = get_session_factory()()
    try:
        assert session.execute(text("select count(*) from learner.dataset_import")).scalar_one() == 1
        assert session.execute(text("select count(*) from learner.dataset_version")).scalar_one() == 1
    finally:
        session.close()

    assert list(Path(datasets_path).glob("*-train.jsonl"))
    assert list(Path(datasets_path).glob("*-validation.jsonl"))
    assert list(Path(datasets_path).glob("*-test.jsonl"))
