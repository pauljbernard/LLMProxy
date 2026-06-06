from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from app.api import admin
from app.api.dependencies import virtual_key_hash
from app.config import Settings
from app.db.models import VirtualAPIKey
from app.main import app


def test_admin_console_page_serves() -> None:
    client = TestClient(app)
    response = client.get("/admin")
    assert response.status_code == 200
    assert "llmProxy Operator Console" in response.text
    assert "health-status-grid" in response.text
    assert "config-table" in response.text
    assert "pipeline-summary" in response.text
    assert "kpi-metrics-grid" in response.text
    assert "request-detail-card" in response.text
    assert "job-detail-card" in response.text
    assert "event-detail-card" in response.text


def test_admin_static_asset_serves() -> None:
    client = TestClient(app)
    response = client.get("/admin/static/app.js")
    assert response.status_code == 200
    assert "initialize" in response.text
    assert "refreshDatasetPipeline" in response.text
    assert "renderMetricGrid" in response.text
    assert "showDetailCard" in response.text
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


def test_admin_virtual_keys_create_list_and_disable() -> None:
    created: list[VirtualAPIKey] = []

    class FakeScalarResult:
        def __init__(self, items):
            self.items = items

        def all(self):
            return self.items

    class FakeExecuteResult:
        def __init__(self, items):
            self.items = items

        def scalars(self):
            return FakeScalarResult(self.items)

    class FakeSession:
        def add(self, item):
            if item.status is None:
                item.status = "active"
            if item.spend_usd is None:
                item.spend_usd = Decimal("0")
            created.append(item)

        def commit(self):
            return None

        def refresh(self, item):
            if item.created_at is None:
                item.created_at = datetime.now(timezone.utc)

        def execute(self, statement):
            return FakeExecuteResult(created)

        def get(self, model, key):
            for item in created:
                if item.id == key:
                    return item
            return None

    def fake_session():
        yield FakeSession()

    app.dependency_overrides[admin.get_session] = fake_session
    client = TestClient(app)
    create_response = client.post(
        "/admin/api/auth/virtual-keys",
        headers={"Authorization": "Bearer change-me"},
        json={
            "display_name": "Team A",
            "owner_id": "team_a",
            "models_allowed": ["gpt-5.5", "proxy-auto"],
            "max_budget_usd": 25.0,
        },
    )
    assert create_response.status_code == 200
    created_payload = create_response.json()
    assert created_payload["token"].startswith("sk-")
    assert created_payload["models_allowed"] == ["gpt-5.5", "proxy-auto"]
    assert created[0].key_hash == virtual_key_hash(created_payload["token"])

    list_response = client.get(
        "/admin/api/auth/virtual-keys",
        headers={"Authorization": "Bearer change-me"},
    )
    assert list_response.status_code == 200
    assert list_response.json()[0]["id"] == created_payload["id"]

    disable_response = client.post(
        f"/admin/api/auth/virtual-keys/{created_payload['id']}/disable",
        headers={"Authorization": "Bearer change-me"},
    )
    assert disable_response.status_code == 200
    assert disable_response.json()["status"] == "disabled"

    update_response = client.patch(
        f"/admin/api/auth/virtual-keys/{created_payload['id']}",
        headers={"Authorization": "Bearer change-me"},
        json={"models_allowed": ["proxy-auto"], "max_budget_usd": 50.0, "display_name": "Team A Updated"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["models_allowed"] == ["proxy-auto"]
    assert update_response.json()["display_name"] == "Team A Updated"

    rotate_response = client.post(
        f"/admin/api/auth/virtual-keys/{created_payload['id']}/rotate",
        headers={"Authorization": "Bearer change-me"},
    )
    app.dependency_overrides.clear()
    assert rotate_response.status_code == 200
    rotated = rotate_response.json()
    assert rotated["token"].startswith("sk-")
    assert rotated["previous_key_prefix"] == created_payload["key_prefix"]


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
    monkeypatch.setattr(
        "app.services.observability.provider_health_snapshot",
        lambda: {"openai": {"consecutive_failures": 2, "cooled_down": True, "cooldown_remaining_seconds": 30.0}},
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
    assert payload["summary"]["provider_health"]["openai"]["cooled_down"] is True


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
