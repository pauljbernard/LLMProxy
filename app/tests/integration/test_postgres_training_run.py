import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import get_settings
from app.db.session import get_engine, get_session_factory
from app.main import create_app
from app.runtime import run_migrations


@pytest.mark.integration
def test_training_run_persists_to_postgres() -> None:
    database_url = os.getenv("LLMPROXY_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("LLMPROXY_TEST_DATABASE_URL is not set")

    with tempfile.TemporaryDirectory() as exports_dir, tempfile.TemporaryDirectory() as datasets_dir, tempfile.TemporaryDirectory() as checkpoints_dir:
        os.environ["LLMPROXY_DATABASE_URL"] = database_url
        os.environ["LLMPROXY_EXPORTS_PATH"] = exports_dir
        os.environ["LLMPROXY_DATASETS_PATH"] = datasets_dir
        os.environ["LLMPROXY_CHECKPOINTS_PATH"] = checkpoints_dir
        get_settings.cache_clear()
        get_engine.cache_clear()
        get_session_factory.cache_clear()
        run_migrations()

        app = create_app()
        client = TestClient(app)

        completion_response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer change-me"},
            json={
                "model": "proxy-auto",
                "messages": [{"role": "user", "content": "Review this coding patch."}],
                "metadata": {
                    "session_id": "sess_training_live",
                    "domain_hint": "coding",
                    "task_type_hint": "code_review",
                },
            },
        )
        assert completion_response.status_code == 200

        candidate_id = client.get(
            "/proxy/training-candidates",
            headers={"Authorization": "Bearer change-me"},
        ).json()[0]["id"]

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
        dataset_version_id = import_response.json()["dataset_version_id"]

        training_response = client.post(
            "/training/runs",
            headers={"Authorization": "Bearer change-me"},
            json={
                "dataset_version_id": dataset_version_id,
                "base_model": "Qwen/Qwen2.5-Coder-7B-Instruct",
                "training_mode": "qlora",
                "epochs": 2,
                "learning_rate": 0.00015,
            },
        )
        assert training_response.status_code == 200
        training_payload = training_response.json()
        assert training_payload["status"] == "completed"

        session = get_session_factory()()
        try:
            assert session.execute(text("select count(*) from learner.training_run")).scalar_one() == 1
        finally:
            session.close()

        assert Path(training_payload["artifact_path"]).exists()
        assert Path(training_payload["metrics"]["checkpoint_path"]).exists()
        assert Path(training_payload["metrics"]["log_path"]).exists()
        assert Path(training_payload["metrics"]["metrics_path"]).exists()
