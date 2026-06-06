from contextlib import contextmanager

from fastapi.testclient import TestClient

from app.api import admin
from app.config import Settings
from app.main import app


def test_admin_console_page_serves() -> None:
    client = TestClient(app)
    response = client.get("/admin")
    assert response.status_code == 200
    assert "llmProxy Operator Console" in response.text
    assert "exports-filter-form" in response.text
    assert "streaming-support-table" in response.text
    assert "streaming-validate-form" in response.text
    assert "jobs-filter-form" in response.text
    assert "training-table" in response.text
    assert "evaluation-table" in response.text


def test_admin_static_asset_serves() -> None:
    client = TestClient(app)
    response = client.get("/admin/static/app.js")
    assert response.status_code == 200
    assert "initialize" in response.text
    assert "refreshTrainingRuns" in response.text
    assert "refreshEvaluations" in response.text
    assert "refreshStreamingSupport" in response.text
    assert "apiStream" in response.text


def test_admin_config_requires_auth() -> None:
    client = TestClient(app)
    response = client.get("/admin/api/config")
    assert response.status_code == 401


def test_admin_config_returns_payload() -> None:
    client = TestClient(app)
    response = client.get("/admin/api/config", headers={"Authorization": "Bearer change-me"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["llmproxy_openai_model"] == "gpt-5.5"
    assert "llmproxy_logs_path" in payload


def test_admin_ops_live_returns_summary_and_logs(monkeypatch) -> None:
    app.dependency_overrides[admin.get_runtime_settings] = lambda: Settings(llmproxy_logs_path="/tmp/logs")

    class FakeScalars:
        def __init__(self, items):
            self._items = items

        def all(self):
            return self._items

        def first(self):
            return self._items[0] if self._items else None

        def __iter__(self):
            return iter(self._items)

    class FakeResult:
        def __init__(self, items):
            self._items = items

        def scalars(self):
            return FakeScalars(self._items)

    class FakeSession:
        def execute(self, _statement):
            return FakeResult([])

    def fake_session():
        yield FakeSession()

    monkeypatch.setattr(
        "app.api.admin.tail_log_records",
        lambda settings, **kwargs: [{"level": "INFO", "message": "ok", "component": "test", "category": "runtime", "timestamp": "2026-06-05T00:00:00Z"}],
    )
    monkeypatch.setattr(
        "app.services.observability.build_streaming_telemetry",
        lambda settings, limit=500: {
            "stream_start_count": 1,
            "stream_complete_count": 1,
            "stream_failed_count": 0,
            "chunk_counts_by_provider": {"ollama": 4},
            "recent_stream_summaries": [{"component": "proxy.shadow", "provider": "ollama", "chunk_count": 4}],
        },
    )
    app.dependency_overrides[admin.get_session] = fake_session
    client = TestClient(app)
    response = client.get("/admin/api/ops/live", headers={"Authorization": "Bearer change-me"})
    app.dependency_overrides.clear()
    assert response.status_code == 200
    payload = response.json()
    assert "summary" in payload
    assert payload["logs"][0]["message"] == "ok"
    assert payload["summary"]["streaming"]["stream_complete_count"] == 1


def test_admin_streaming_support_returns_capabilities(monkeypatch) -> None:
    class FakeSession:
        def execute(self, _statement):
            class FakeResult:
                def scalars(self):
                    class FakeScalars:
                        def first(self):
                            return None
                    return FakeScalars()
            return FakeResult()

    def fake_session():
        yield FakeSession()

    monkeypatch.setattr(
        "app.api.admin.list_provider_capabilities",
        lambda settings, session=None: [
            type(
                "Capability",
                (),
                {
                    "model_dump": lambda self, mode="json": {
                        "provider_name": "openai",
                        "provider_family": "OpenAI",
                        "model_id": "gpt-5.5",
                        "supports_streaming": True,
                        "supports_embeddings": True,
                        "supports_tools": False,
                        "max_context_tokens": 128000,
                        "max_output_tokens": 8192,
                    }
                },
            )()
        ],
    )
    monkeypatch.setattr("app.api.admin._streaming_route_examples", lambda session, settings: [{"requested_model": "proxy-auto", "selected_provider": "openai", "supports_streaming": True}])
    app.dependency_overrides[admin.get_session] = fake_session
    client = TestClient(app)
    response = client.get("/admin/api/proxy/streaming-support", headers={"Authorization": "Bearer change-me"})
    app.dependency_overrides.clear()
    assert response.status_code == 200
    payload = response.json()
    assert payload["providers"][0]["provider_name"] == "openai"
    assert payload["providers"][0]["configured"] is False
    assert payload["route_examples"][0]["selected_provider"] == "openai"


def test_admin_streaming_validate_returns_chunk_preview(monkeypatch) -> None:
    class FakeProvider:
        provider_family = "OpenAI"
        provider_name = "openai"
        model_id = "gpt-5.5"
        supports_streaming = True

        async def stream_chat(self, request):
            yield {"delta": "Hello ", "input_tokens": 4, "output_tokens": 0, "finish_reason": None}
            yield {"delta": "world", "input_tokens": 4, "output_tokens": 2, "finish_reason": "stop"}

    class FakeSession:
        pass

    def fake_session():
        yield FakeSession()

    monkeypatch.setattr("app.api.admin.get_provider_registry", lambda settings, session=None: {"openai": FakeProvider()})
    app.dependency_overrides[admin.get_session] = fake_session
    client = TestClient(app)
    response = client.post(
        "/admin/api/ops/streaming/validate",
        headers={"Authorization": "Bearer change-me"},
        json={"provider_key": "openai", "prompt": "hello"},
    )
    app.dependency_overrides.clear()
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["provider_key"] == "openai"
    assert payload["preview_text"] == "Hello world"
    assert payload["finish_reason"] == "stop"


def test_admin_jobs_retry_requires_operator() -> None:
    app.dependency_overrides[admin.get_runtime_settings] = lambda: Settings(llmproxy_automation_tokens=["automation-token"])
    client = TestClient(app)
    response = client.post(
        "/admin/api/jobs/job_1/retry",
        headers={"Authorization": "Bearer automation-token"},
        json={"reset_attempts": True, "available_now": True},
    )
    app.dependency_overrides.clear()
    assert response.status_code == 403


def test_admin_jobs_retry_mutates_job(monkeypatch) -> None:
    from datetime import datetime, timezone

    job = type(
        "Job",
        (),
            {
                "id": "job_1",
                "job_type": "kpi.generate",
                "status": "failed",
                "payload_json": {},
            "attempts": 3,
            "max_attempts": 3,
            "available_at": datetime.now(timezone.utc),
            "claimed_at": datetime.now(timezone.utc),
            "completed_at": datetime.now(timezone.utc),
            "last_error": "boom",
            "created_at": datetime.now(timezone.utc),
        },
    )()

    class FakeSession:
        def get(self, model, key):
            assert key == "job_1"
            return job

        def commit(self):
            return None

    def fake_session():
        yield FakeSession()

    app.dependency_overrides[admin.get_session] = fake_session
    client = TestClient(app)
    response = client.post(
        "/admin/api/jobs/job_1/retry",
        headers={"Authorization": "Bearer change-me"},
        json={"reset_attempts": True, "available_now": True},
    )
    app.dependency_overrides.clear()
    assert response.status_code == 200
    payload = response.json()
    assert payload["retried"] is True
    assert payload["job"]["status"] == "pending"
