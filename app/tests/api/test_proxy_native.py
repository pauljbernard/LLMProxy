import httpx
from fastapi.testclient import TestClient

from app.db.models import TrainingCandidate
from app.providers.anthropic_provider import AnthropicProvider
from app.providers.google_provider import GoogleProvider
from app.providers.openai_provider import OpenAIProvider
from app.main import app


class FakeSession:
    def __init__(self) -> None:
        self.items: list[object] = []
        self.committed = False
        self.flush_count = 0

    def add(self, item: object) -> None:
        self.items.append(item)

    def flush(self) -> None:
        self.flush_count += 1

    def commit(self) -> None:
        self.committed = True

    def close(self) -> None:
        return None


class FakeAsyncSession:
    def __init__(self, sync_session: FakeSession) -> None:
        self.sync_session = sync_session

    async def run_sync(self, fn):
        return fn(self.sync_session)

    async def commit(self) -> None:
        self.sync_session.commit()

    async def rollback(self) -> None:
        return None

    async def close(self) -> None:
        self.sync_session.close()


def test_ensemble_requires_auth() -> None:
    client = TestClient(app)
    response = client.post(
        "/proxy/ensemble",
        json={
            "model": "proxy-ensemble",
            "messages": [{"role": "user", "content": "Evaluate this architecture decision."}],
            "metadata": {"session_id": "sess_auth"},
        },
    )
    assert response.status_code == 401


def test_ensemble_returns_synthesized_answer_and_persists(monkeypatch) -> None:
    from app.proxy import ensemble as ensemble_module
    from app.api.dependencies import get_async_session

    registry = {
        "anthropic": AnthropicProvider(
            "claude-3-5-sonnet",
            api_key="test-anthropic-key",
            base_url="https://api.anthropic.com/v1",
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json={
                        "id": "msg_1",
                        "model": "claude-3-5-sonnet",
                        "content": [{"type": "text", "text": "Anthropic ensemble answer."}],
                        "stop_reason": "end_turn",
                        "usage": {"input_tokens": 12, "output_tokens": 4},
                    },
                )
            ),
        ),
        "openai": OpenAIProvider(
            "gpt-5.5",
            api_key="test-openai-key",
            base_url="https://api.openai.com/v1",
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json={
                        "id": "chatcmpl_1",
                        "model": "gpt-5.5",
                        "choices": [
                            {
                                "message": {"role": "assistant", "content": "OpenAI ensemble answer."},
                                "finish_reason": "stop",
                            }
                        ],
                        "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
                    },
                )
            ),
        ),
        "google": GoogleProvider(
            "gemini-2.5-pro",
            api_key="test-google-key",
            base_url="https://generativelanguage.googleapis.com/v1beta",
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json={
                        "candidates": [
                            {
                                "content": {"parts": [{"text": "Google ensemble answer."}]},
                                "finishReason": "STOP",
                            }
                        ],
                        "usageMetadata": {"promptTokenCount": 11, "candidatesTokenCount": 3, "totalTokenCount": 14},
                        "modelVersion": "gemini-2.5-pro",
                    },
                )
            ),
        ),
    }
    monkeypatch.setattr(ensemble_module, "get_provider_registry", lambda settings: registry)

    fake_session = FakeSession()
    fake_async_session = FakeAsyncSession(fake_session)
    app.dependency_overrides[get_async_session] = lambda: fake_async_session
    client = TestClient(app)
    response = client.post(
        "/proxy/ensemble",
        headers={"Authorization": "Bearer change-me"},
        json={
            "model": "proxy-ensemble",
            "messages": [{"role": "user", "content": "Evaluate this architecture decision."}],
            "metadata": {
                "session_id": "sess_ensemble",
                "domain_hint": "software_architecture",
                "task_type_hint": "design_review",
            },
        },
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["response"]["model"] == "proxy-ensemble"
    assert len(payload["teacher_candidates"]) == 3
    assert payload["judge_critique"]["judge_provider"] == "rule_based_judge"
    assert payload["judge_critique"]["selected_provider"] in {"anthropic", "openai", "google"}
    assert fake_session.committed is True
    assert fake_session.flush_count == 2
    assert len(fake_session.items) == 7


def test_register_model_requires_auth() -> None:
    client = TestClient(app)
    response = client.post(
        "/proxy/models/register",
        json={
            "model_registry_id": "model_1",
            "model_alias": "coding-lora-1",
            "base_model": "Qwen/Qwen2.5-Coder-7B-Instruct",
            "adapter_type": "lora",
            "adapter_path": "/tmp/adapter.bin",
            "runtime": "ollama",
            "endpoint_url": "http://localhost:11434",
            "domains": ["coding"],
            "task_types": ["code_review"],
            "status": "approved",
        },
    )
    assert response.status_code == 401


def test_register_model_requires_operator_token(tmp_path) -> None:
    from app.api.dependencies import get_runtime_settings
    from app.config import Settings

    app.dependency_overrides[get_runtime_settings] = lambda: Settings(
        llmproxy_models_path=str(tmp_path),
        llmproxy_automation_tokens=["automation-token"],
    )
    client = TestClient(app)
    response = client.post(
        "/proxy/models/register",
        headers={"Authorization": "Bearer automation-token"},
        json={
            "model_registry_id": "model_1",
            "model_alias": "coding-lora-1",
            "base_model": "Qwen/Qwen2.5-Coder-7B-Instruct",
            "adapter_type": "lora",
            "adapter_path": "/tmp/adapter.bin",
            "runtime": "ollama",
            "endpoint_url": "http://localhost:11434",
            "domains": ["coding"],
            "task_types": ["code_review"],
            "status": "approved",
        },
    )
    app.dependency_overrides.clear()
    assert response.status_code == 403


def test_register_model_writes_model_package(tmp_path, monkeypatch) -> None:
    from app.api.dependencies import get_runtime_settings
    from app.config import Settings

    app.dependency_overrides[get_runtime_settings] = lambda: Settings(
        llmproxy_models_path=str(tmp_path),
        llmproxy_automation_tokens=["automation-token"],
    )
    client = TestClient(app)
    response = client.post(
        "/proxy/models/register",
        headers={"Authorization": "Bearer change-me"},
        json={
            "model_registry_id": "model_1",
            "model_alias": "coding-lora-1",
            "base_model": "Qwen/Qwen2.5-Coder-7B-Instruct",
            "adapter_type": "lora",
            "adapter_path": "/tmp/adapter.bin",
            "runtime": "ollama",
            "endpoint_url": "http://localhost:11434",
            "domains": ["coding"],
            "task_types": ["code_review"],
            "quality": {"promotion_status": "approved"},
            "status": "approved",
        },
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["model_registry_id"] == "model_1"
    assert payload["model_alias"] == "coding-lora-1"
    manifest_path = tmp_path / "coding-lora-1" / "model-package.json"
    assert manifest_path.exists()


def test_list_training_candidates_supports_paginated_payload(monkeypatch) -> None:
    from app.api import proxy_native
    from app.api.dependencies import get_session

    class FakeSession:
        def close(self) -> None:
            return None

    monkeypatch.setattr(
        proxy_native,
        "list_training_candidates",
        lambda session, **kwargs: [
            TrainingCandidate(
                id="cand_1",
                request_log_id="req_1",
                routing_decision_id="rd_1",
                session_id="sess_1",
                domain="coding",
                task_type="analysis",
                status="captured",
                quality_score=0.8,
                approval_status="pending",
                export_eligible=False,
                selected_response="answer",
                messages_json=[],
                provenance_json={},
                validation_json={},
                metadata_json={
                    "requested_model": "proxy-auto",
                    "effective_model": "gpt-5",
                    "prompt_template_name": "architecture_review",
                    "prompt_template_version": 3,
                    "prompt_template_render_hash": "a" * 64,
                },
            ),
            TrainingCandidate(
                id="cand_2",
                request_log_id="req_2",
                routing_decision_id="rd_2",
                session_id="sess_2",
                domain="coding",
                task_type="analysis",
                status="captured",
                quality_score=0.9,
                approval_status="approved",
                export_eligible=True,
                selected_response="answer",
                messages_json=[],
                provenance_json={},
                validation_json={},
                metadata_json={
                    "requested_model": "proxy-teacher",
                    "effective_model": "gpt-5-mini",
                    "prompt_template_name": "lineage_probe",
                    "prompt_template_version": 4,
                    "prompt_template_render_hash": "b" * 64,
                },
            ),
        ],
    )

    app.dependency_overrides[get_session] = lambda: FakeSession()
    client = TestClient(app)
    response = client.get("/proxy/training-candidates?paginated=true&limit=1&offset=1", headers={"Authorization": "Bearer change-me"})
    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert payload["items"][0]["id"] == "cand_2"
    assert payload["items"][0]["interaction_protocols"] == []
    assert payload["items"][0]["interaction_operations"] == []
    assert payload["items"][0]["interaction_outcome"] == "unknown"
    assert payload["items"][0]["interaction_trace_count"] == 0
    assert payload["items"][0]["requested_model"] == "proxy-teacher"
    assert payload["items"][0]["effective_model"] == "gpt-5-mini"
    assert payload["items"][0]["prompt_template_name"] == "lineage_probe"
    assert payload["items"][0]["prompt_template_version"] == 4
    assert payload["items"][0]["prompt_template_render_hash"] == "b" * 64


def test_list_training_candidates_forwards_interaction_filters(monkeypatch) -> None:
    from app.api import proxy_native
    from app.api.dependencies import get_session

    captured = {}

    class FakeSession:
        def close(self) -> None:
            return None

    def fake_list_training_candidates(session, **kwargs):
        captured.update(kwargs)
        return [
            TrainingCandidate(
                id="cand_3",
                request_log_id="req_3",
                routing_decision_id="rd_3",
                session_id="sess_3",
                domain="coding",
                task_type="analysis",
                status="captured",
                quality_score=0.95,
                approval_status="approved",
                export_eligible=True,
                selected_response="answer",
                messages_json=[],
                provenance_json={
                    "interaction_traces": [
                        {"protocol": "rest", "operation": "invoke_endpoint", "success": True},
                    ],
                },
                validation_json={},
                metadata_json={
                    "requested_model": "proxy-auto",
                    "effective_model": "gpt-5",
                    "prompt_template_name": "architecture_review",
                    "prompt_template_version": 7,
                    "prompt_template_render_hash": "c" * 64,
                    "prompt_template_selection_mode": "challenger_canary",
                    "prompt_template_rollout_percentage": 15.0,
                },
            ),
        ]

    monkeypatch.setattr(proxy_native, "list_training_candidates", fake_list_training_candidates)

    app.dependency_overrides[get_session] = lambda: FakeSession()
    client = TestClient(app)
    response = client.get(
        "/proxy/training-candidates"
        "?domain=coding&approval_status=approved&interaction_protocol=rest"
        "&interaction_operation=invoke_endpoint&interaction_outcome=success"
        "&prompt_template_name=architecture_review&prompt_template_version=7"
        "&prompt_template_selection_mode=challenger_canary",
        headers={"Authorization": "Bearer change-me"},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert captured == {
        "domain": "coding",
        "approval_status": "approved",
        "interaction_protocol": "rest",
        "interaction_operation": "invoke_endpoint",
        "interaction_outcome": "success",
        "prompt_template_name": "architecture_review",
        "prompt_template_version": 7,
        "prompt_template_selection_mode": "challenger_canary",
    }
    assert payload[0]["interaction_protocols"] == ["rest"]
    assert payload[0]["interaction_operations"] == ["invoke_endpoint"]
    assert payload[0]["interaction_outcome"] == "success"
    assert payload[0]["interaction_trace_count"] == 1
    assert payload[0]["prompt_template_name"] == "architecture_review"
    assert payload[0]["prompt_template_version"] == 7
    assert payload[0]["prompt_template_selection_mode"] == "challenger_canary"
    assert payload[0]["prompt_template_rollout_percentage"] == 15.0
