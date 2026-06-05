import json
import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import get_settings
from app.db.session import get_engine, get_session_factory
from app.integration.outbox import process_pending_events
from app.main import create_app
from app.runtime import run_migrations


def write_package(root: Path, *, model_alias: str) -> None:
    package_dir = root / model_alias
    package_dir.mkdir(parents=True, exist_ok=True)
    (package_dir / "model-package.json").write_text(
        json.dumps(
            {
                "package_version": "1.0",
                "model_registry_id": f"model_{model_alias}",
                "model_alias": model_alias,
                "base_model": "Qwen/Qwen2.5-Coder-7B-Instruct",
                "adapter_type": "lora",
                "artifact_format": "adapter-binary",
                "artifact_paths": [str(package_dir / "adapter.bin")],
                "domains": ["coding"],
                "task_types": ["code_review"],
                "quality_summary": {
                    "overall_score": 0.9,
                    "domain_scores": {"coding": 0.9},
                    "quality_delta_vs_frontier": 0.02,
                    "value_per_dollar_gain_vs_frontier": 4.0,
                    "promotion_status": "approved",
                },
                "compatibility": {
                    "model_contract_version": "1.0",
                    "learner_version": "0.1.0",
                    "compatible_proxy_versions": ["0.1.0"],
                    "runtime_targets": ["ollama"],
                },
                "provenance": {"source": "test"},
                "created_at": "2026-06-05T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )


@pytest.mark.integration
def test_continuous_improvement_flow_processes_outbox_and_reports_kpis() -> None:
    database_url = os.getenv("LLMPROXY_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("LLMPROXY_TEST_DATABASE_URL is not set")

    with tempfile.TemporaryDirectory() as models_dir, tempfile.TemporaryDirectory() as exports_dir, tempfile.TemporaryDirectory() as datasets_dir, tempfile.TemporaryDirectory() as reports_dir:
        write_package(Path(models_dir), model_alias="coding-lora-v1")

        os.environ["LLMPROXY_DATABASE_URL"] = database_url
        os.environ["LLMPROXY_MODELS_PATH"] = models_dir
        os.environ["LLMPROXY_EXPORTS_PATH"] = exports_dir
        os.environ["LLMPROXY_DATASETS_PATH"] = datasets_dir
        os.environ["LLMPROXY_REPORTS_PATH"] = reports_dir
        get_settings.cache_clear()
        get_engine.cache_clear()
        get_session_factory.cache_clear()
        run_migrations()

        app = create_app()
        client = TestClient(app)

        activate = client.post(
            "/deployment/models/coding-lora-v1/activate",
            headers={"Authorization": "Bearer change-me"},
            json={"deployment_mode": "production"},
        )
        assert activate.status_code == 200

        chat_response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer change-me"},
            json={
                "model": "proxy-auto",
                "messages": [{"role": "user", "content": "Review this coding patch."}],
                "metadata": {
                    "session_id": "sess_phase8",
                    "domain_hint": "coding",
                    "task_type_hint": "code_review",
                },
            },
        )
        assert chat_response.status_code == 200
        assert chat_response.json()["model"] == "coding-lora-v1"

        candidate_id = client.get(
            "/proxy/training-candidates",
            headers={"Authorization": "Bearer change-me"},
        ).json()[0]["id"]
        assert client.post(
            f"/proxy/training-candidates/{candidate_id}/approve",
            headers={"Authorization": "Bearer change-me"},
        ).status_code == 200

        export_response = client.post(
            "/proxy/export/jsonl",
            headers={"Authorization": "Bearer change-me"},
            json={"domain": "coding", "min_quality_score": 0.5},
        )
        assert export_response.status_code == 200

        session = get_session_factory()()
        try:
            outbox_result = process_pending_events(session, settings=get_settings())
            session.commit()
            assert outbox_result.processed_count >= 1
            assert outbox_result.imported_count >= 1
        finally:
            session.close()

        kpi_response = client.get("/evaluation/kpis", headers={"Authorization": "Bearer change-me"})
        assert kpi_response.status_code == 200
        payload = kpi_response.json()
        metrics = {item["metric_name"]: item for item in payload["metrics"]}
        assert metrics["avoided_frontier_spend"]["metric_value"] > 0
        assert metrics["frontier_to_local_substitution_rate"]["metric_value"] > 0
        assert Path(payload["report_path"]).exists()

        session = get_session_factory()()
        try:
            assert session.execute(text("select count(*) from learner.dataset_import")).scalar_one() >= 1
            assert session.execute(text("select count(*) from integration.model_performance_sample")).scalar_one() >= 1
        finally:
            session.close()
