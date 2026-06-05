import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import get_settings
from app.db.session import get_engine, get_session_factory
from app.main import create_app


@pytest.mark.integration
def test_ensemble_persists_teacher_outputs_and_judge_critique() -> None:
    database_url = os.getenv("LLMPROXY_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("LLMPROXY_TEST_DATABASE_URL is not set")

    os.environ["LLMPROXY_DATABASE_URL"] = database_url
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()

    app = create_app()
    client = TestClient(app)
    response = client.post(
        "/proxy/ensemble",
        headers={"Authorization": "Bearer change-me"},
        json={
            "model": "proxy-ensemble",
            "messages": [{"role": "user", "content": "Evaluate this architecture decision."}],
            "metadata": {
                "session_id": "sess_ensemble_live",
                "domain_hint": "software_architecture",
                "task_type_hint": "design_review",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["response"]["model"] == "proxy-ensemble"
    assert len(payload["teacher_candidates"]) == 3

    session = get_session_factory()()
    try:
        assert session.execute(text("select count(*) from proxy.request_log")).scalar_one() == 1
        assert session.execute(text("select count(*) from proxy.routing_decision")).scalar_one() == 1
        assert session.execute(text("select count(*) from proxy.model_response")).scalar_one() == 3
        assert session.execute(text("select count(*) from proxy.judge_critique")).scalar_one() == 1
    finally:
        session.close()
