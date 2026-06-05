import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import get_settings
from app.db.session import get_engine, get_session_factory
from app.main import create_app


@pytest.mark.integration
def test_candidate_approval_and_export_flow() -> None:
    database_url = os.getenv("LLMPROXY_TEST_DATABASE_URL")
    exports_path = os.getenv("LLMPROXY_TEST_EXPORTS_PATH")
    if not database_url or not exports_path:
        pytest.skip("LLMPROXY_TEST_DATABASE_URL or LLMPROXY_TEST_EXPORTS_PATH is not set")

    os.environ["LLMPROXY_DATABASE_URL"] = database_url
    os.environ["LLMPROXY_EXPORTS_PATH"] = exports_path
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
                "session_id": "sess_candidate_live",
                "domain_hint": "coding",
                "task_type_hint": "code_review",
            },
        },
    )
    assert completion_response.status_code == 200

    list_response = client.get(
        "/proxy/training-candidates",
        headers={"Authorization": "Bearer change-me"},
    )
    assert list_response.status_code == 200
    candidates = list_response.json()
    assert len(candidates) == 1
    candidate_id = candidates[0]["id"]
    assert candidates[0]["approval_status"] == "needs_review"

    approve_response = client.post(
        f"/proxy/training-candidates/{candidate_id}/approve",
        headers={"Authorization": "Bearer change-me"},
    )
    assert approve_response.status_code == 200
    assert approve_response.json()["approval_status"] == "approved"

    export_response = client.post(
        "/proxy/export/jsonl",
        headers={"Authorization": "Bearer change-me"},
        json={"domain": "coding", "min_quality_score": 0.5},
    )
    assert export_response.status_code == 200
    export_payload = export_response.json()
    assert export_payload["record_count"] == 1

    session = get_session_factory()()
    try:
        assert session.execute(text("select count(*) from proxy.training_candidate")).scalar_one() == 1
        assert session.execute(text("select count(*) from proxy.dataset_export")).scalar_one() == 1
        status = session.execute(text("select status from proxy.training_candidate limit 1")).scalar_one()
        assert status == "exported"
    finally:
        session.close()
