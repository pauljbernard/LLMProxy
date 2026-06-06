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
def test_evaluation_run_persists_to_postgres() -> None:
    database_url = os.getenv("LLMPROXY_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("LLMPROXY_TEST_DATABASE_URL is not set")

    with tempfile.TemporaryDirectory() as exports_dir, tempfile.TemporaryDirectory() as datasets_dir, tempfile.TemporaryDirectory() as checkpoints_dir, tempfile.TemporaryDirectory() as models_dir:
        os.environ["LLMPROXY_DATABASE_URL"] = database_url
        os.environ["LLMPROXY_EXPORTS_PATH"] = exports_dir
        os.environ["LLMPROXY_DATASETS_PATH"] = datasets_dir
        os.environ["LLMPROXY_CHECKPOINTS_PATH"] = checkpoints_dir
        os.environ["LLMPROXY_MODELS_PATH"] = models_dir
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
                    "session_id": "sess_eval_live",
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
        assert client.post(
            f"/proxy/training-candidates/{candidate_id}/approve",
            headers={"Authorization": "Bearer change-me"},
        ).status_code == 200

        export_payload = client.post(
            "/proxy/export/jsonl",
            headers={"Authorization": "Bearer change-me"},
            json={"domain": "coding", "min_quality_score": 0.5},
        ).json()
        import_payload = client.post(
            "/datasets/import",
            headers={"Authorization": "Bearer change-me"},
            json={
                "dataset_export_id": export_payload["dataset_export_id"],
                "manifest_path": export_payload["manifest_path"],
                "data_path": export_payload["data_path"],
            },
        ).json()
        training_payload = client.post(
            "/training/runs",
            headers={"Authorization": "Bearer change-me"},
            json={
                "dataset_version_id": import_payload["dataset_version_id"],
                "base_model": "Qwen/Qwen2.5-Coder-7B-Instruct",
                "training_mode": "lora",
            },
        ).json()

        evaluation_response = client.post(
            "/evaluation/runs",
            headers={"Authorization": "Bearer change-me"},
            json={"training_run_id": training_payload["training_run_id"]},
        )
        assert evaluation_response.status_code == 202
        evaluation_payload = evaluation_response.json()
        assert evaluation_payload["queued"] is True

        from app.runtime import run_worker_iteration

        run_worker_iteration()

        local_models_response = client.get(
            "/models/local",
            headers={"Authorization": "Bearer change-me"},
        )
        assert local_models_response.status_code == 200
        assert len(local_models_response.json()) == 1

        session = get_session_factory()()
        try:
            assert session.execute(text("select count(*) from learner.evaluation_run")).scalar_one() == 1
        finally:
            session.close()

        evaluation_runs = client.get("/evaluation/runs", headers={"Authorization": "Bearer change-me"}).json()
        assert Path(evaluation_runs[0]["package_manifest_path"]).exists()
