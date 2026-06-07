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
    assert "mcp-server-grid" in response.text
    assert "provider-guide-grid" in response.text
    assert "request-mcp-trace-table" in response.text
    assert "ops-mcp-grid" in response.text
    assert "replicate-prediction-form" in response.text
    assert "routing-settings-form" in response.text
    assert "refresh-observability" in response.text
    assert "prompts-table" in response.text
    assert "prompt-template-form" in response.text
    assert 'name="prompt_template_name"' in response.text
    assert 'name="prompt_template_version"' in response.text
    assert 'name="prompt_template_variables"' in response.text
    assert 'name="route_tags"' in response.text
    assert 'name="region_hint"' in response.text
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
    assert "validateRoutingDefaultEntries" in response.text
    assert "refreshObservability" in response.text
    assert "refreshPrompts" in response.text
    assert "parseJsonObject" in response.text
    assert "Diff Prev" in response.text
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
    assert "llmproxy_routing_strategy" in payload
    assert "llmproxy_logs_path" in payload


def test_admin_routing_settings_returns_payload() -> None:
    client = TestClient(app)
    response = client.get("/admin/api/routing/settings", headers={"Authorization": "Bearer change-me"})
    assert response.status_code == 200
    payload = response.json()
    assert "llmproxy_routing_strategy" in payload
    assert "llmproxy_frontier_default_entries" in payload


def test_admin_routing_settings_update_persists_env_values(tmp_path) -> None:
    client = TestClient(app)
    env_file = tmp_path / ".env.routing"
    response = client.post(
        "/admin/api/routing/settings",
        headers={"Authorization": "Bearer change-me"},
        json={
            "routing_strategy": "latency",
            "frontier_default_entries": [
                {"provider_key": "groq", "model_id": "llama-3.3-70b-versatile", "domains": ["general"], "deployment_mode": "production"}
            ],
            "env_file": str(env_file),
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["saved"] is True
    text = env_file.read_text(encoding="utf-8")
    assert "LLMPROXY_ROUTING_STRATEGY=latency" in text
    assert "LLMPROXY_FRONTIER_DEFAULT_ENTRIES=" in text


def test_admin_provider_guides_returns_cloudflare_tgi_and_replicate() -> None:
    client = TestClient(app)
    response = client.get("/admin/api/providers/guides", headers={"Authorization": "Bearer change-me"})
    assert response.status_code == 200
    payload = response.json()
    provider_keys = {item["provider_key"] for item in payload["providers"]}
    assert "cloudflare_workers_ai" in provider_keys
    assert "huggingface_tgi" in provider_keys
    assert "replicate" in provider_keys


def test_admin_pricing_catalog_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/admin/api/pricing/catalog", headers={"Authorization": "Bearer change-me"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] >= 1
    assert any(item["provider"] == "openai" and item["model"] == "gpt-5.5" for item in payload["items"])


def test_admin_observability_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/admin/api/observability", headers={"Authorization": "Bearer change-me"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["prometheus"]["path"] == "/metrics/prometheus"
    assert "job_name" in payload["prometheus"]["scrape_config"]
    assert "service_name" in payload["otel"]


def test_admin_prompt_templates_endpoints(monkeypatch) -> None:
    created = []

    class FakeSession:
        def __init__(self) -> None:
            self.committed = False

        def execute(self, statement):
            text = str(statement)

            class ScalarOneResult:
                def scalar_one(self_inner):
                    return 0

            class ScalarList:
                def __init__(self_inner, items):
                    self_inner._items = items

                def all(self_inner):
                    return self_inner._items

                def first(self_inner):
                    return self_inner._items[0] if self_inner._items else None

            class Result:
                def scalars(self_inner):
                    return ScalarList(created)

            if "coalesce(max" in text.lower():
                return ScalarOneResult()
            return Result()

        def add(self, item):
            created.append(item)

        def commit(self):
            self.committed = True

        def refresh(self, item):
            if getattr(item, "created_at", None) is None:
                item.created_at = datetime.now(timezone.utc)

    def fake_session():
        yield FakeSession()

    app.dependency_overrides[admin.get_session] = fake_session
    client = TestClient(app)
    create_response = client.post(
        "/admin/api/prompts",
        headers={"Authorization": "Bearer change-me"},
        json={
            "name": "architecture_review",
            "description": "Architecture review system prompt",
            "template_text": "Review {service_name} for {constraints}.",
            "variables": ["service_name", "constraints"],
            "model_override": "gpt-5.5",
        },
    )
    assert create_response.status_code == 201
    created_payload = create_response.json()
    assert created_payload["name"] == "architecture_review"
    assert created_payload["version"] == 1

    list_response = client.get("/admin/api/prompts", headers={"Authorization": "Bearer change-me"})
    assert list_response.status_code == 200
    assert list_response.json()[0]["name"] == "architecture_review"

    render_response = client.post(
        "/admin/api/prompts/architecture_review/render",
        headers={"Authorization": "Bearer change-me"},
        json={"version": 1, "variables": {"service_name": "billing", "constraints": "high availability"}},
    )
    diff_response = client.get(
        "/admin/api/prompts/architecture_review/diff?from_version=1&to_version=1",
        headers={"Authorization": "Bearer change-me"},
    )
    app.dependency_overrides.clear()
    assert render_response.status_code == 200
    assert "billing" in render_response.json()["rendered_text"]
    assert diff_response.status_code == 200
    assert diff_response.json()["name"] == "architecture_review"


def test_admin_replicate_prediction_queue_endpoint(monkeypatch) -> None:
    queued_job = type("Job", (), {"id": "job_rep_1", "job_type": "replicate.prediction"})()

    class FakeSession:
        def commit(self):
            return None

    def fake_session():
        yield FakeSession()

    monkeypatch.setattr("app.api.admin.enqueue_replicate_prediction_job", lambda session, model, input_payload, wait_for_completion: queued_job)
    app.dependency_overrides[admin.get_session] = fake_session
    client = TestClient(app)
    response = client.post(
        "/admin/api/replicate/predictions",
        headers={"Authorization": "Bearer change-me"},
        json={"model": "black-forest-labs/flux-schnell", "input": {"prompt": "A cat"}, "wait_for_completion": True},
    )
    app.dependency_overrides.clear()
    assert response.status_code == 200
    payload = response.json()
    assert payload["queued"] is True
    assert payload["job_id"] == "job_rep_1"
    assert payload["job_type"] == "replicate.prediction"


def test_admin_replicate_prediction_validate_endpoint(monkeypatch) -> None:
    async def fake_run_replicate_prediction(*, settings, model, input_payload, wait_for_completion, transport=None):
        return {"id": "pred_1", "status": "succeeded", "output": "ok"}

    monkeypatch.setattr("app.api.admin.run_replicate_prediction", fake_run_replicate_prediction)
    client = TestClient(app)
    response = client.post(
        "/admin/api/replicate/predictions/validate",
        headers={"Authorization": "Bearer change-me"},
        json={"model": "replicate/hello-world", "input": {"text": "Alice"}, "wait_for_completion": True},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["model"] == "replicate/hello-world"
    assert payload["result"]["status"] == "succeeded"


def test_admin_provider_validate_endpoint_returns_structured_failure(monkeypatch) -> None:
    class FakeProvider:
        provider_family = "huggingface_tgi"
        model_id = "tgi"

        async def invoke(self, request):
            raise RuntimeError("connection refused")

    monkeypatch.setattr("app.api.admin.get_provider_registry", lambda settings, session=None: {"huggingface_tgi": FakeProvider()})
    client = TestClient(app)
    response = client.post(
        "/admin/api/providers/validate",
        headers={"Authorization": "Bearer change-me"},
        json={"provider_key": "huggingface_tgi"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["provider_key"] == "huggingface_tgi"
    assert "connection refused" in payload["error"]


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
            "rpm_limit": 90,
            "tpm_limit": 9000,
            "max_budget_usd": 25.0,
            "budget_reset_period": "monthly",
        },
    )
    assert create_response.status_code == 200
    created_payload = create_response.json()
    assert created_payload["token"].startswith("sk-")
    assert created_payload["models_allowed"] == ["gpt-5.5", "proxy-auto"]
    assert created_payload["rpm_limit"] == 90
    assert created_payload["tpm_limit"] == 9000
    assert created_payload["budget_reset_period"] == "monthly"
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
        json={
            "models_allowed": ["proxy-auto"],
            "rpm_limit": 120,
            "tpm_limit": 12000,
            "max_budget_usd": 50.0,
            "budget_reset_period": "weekly",
            "display_name": "Team A Updated",
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["models_allowed"] == ["proxy-auto"]
    assert update_response.json()["rpm_limit"] == 120
    assert update_response.json()["tpm_limit"] == 12000
    assert update_response.json()["budget_reset_period"] == "weekly"
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
    monkeypatch.setattr(
        "app.services.observability.mcp_runtime_snapshot",
        lambda: {"cluster": {"server": "cluster", "tool_call_count": 2, "validation_count": 1, "failed_tool_calls": 0, "failed_validations": 0, "last_tool_name": "status_lookup", "last_tool_at": "2026-06-05T00:00:00Z", "last_validation_at": "2026-06-05T00:00:00Z", "last_error": None}},
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
    assert payload["summary"]["mcp_runtime"]["cluster"]["tool_call_count"] == 2


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


def test_admin_mcp_servers_returns_inventory(monkeypatch) -> None:
    app.dependency_overrides[admin.get_runtime_settings] = lambda: Settings(
        llmproxy_mcp_servers={
            "cluster": {
                "transport": "stdio",
                "command": "python3",
                "args": ["/tmp/mcp_server.py"],
                "timeout_seconds": 12.0,
            }
        }
    )
    monkeypatch.setattr(
        "app.api.admin._list_mcp_tools",
        lambda settings, server_name: __import__("asyncio").sleep(0, result=[
            {"name": "status_lookup", "description": "Get status", "inputSchema": {"type": "object"}}
        ]),
    )
    client = TestClient(app)
    response = client.get("/admin/api/mcp/servers", headers={"Authorization": "Bearer change-me"})
    app.dependency_overrides.clear()
    assert response.status_code == 200
    payload = response.json()
    assert payload["server_count"] == 1
    assert payload["tool_count"] == 1
    assert payload["servers"][0]["server"] == "cluster"
    assert payload["servers"][0]["tools"][0]["name"] == "status_lookup"


def test_admin_mcp_server_validate_returns_diagnostics(monkeypatch) -> None:
    app.dependency_overrides[admin.get_runtime_settings] = lambda: Settings(
        llmproxy_mcp_servers={
            "cluster": {
                "transport": "stdio",
                "command": "python3",
                "args": ["/tmp/mcp_server.py"],
                "timeout_seconds": 12.0,
            }
        }
    )
    monkeypatch.setattr(
        "app.api.admin.inspect_mcp_server",
        lambda settings, server_name: __import__("asyncio").sleep(
            0,
            result={
                "server": server_name,
                "transport": "stdio",
                "command": "python3",
                "args": ["/tmp/mcp_server.py"],
                "cwd": None,
                "timeout_seconds": 12.0,
                "tool_count": 1,
                "tools": [{"name": "status_lookup", "description": "Get status", "input_schema": {"type": "object"}}],
                "validated": True,
                "latency_ms": 7,
            },
        ),
    )
    client = TestClient(app)
    response = client.post("/admin/api/mcp/servers/cluster/validate", headers={"Authorization": "Bearer change-me"})
    app.dependency_overrides.clear()
    assert response.status_code == 200
    payload = response.json()
    assert payload["server"] == "cluster"
    assert payload["validated"] is True
    assert payload["latency_ms"] == 7


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
