import httpx
from fastapi.testclient import TestClient

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
    from app.api.dependencies import get_session

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
    app.dependency_overrides[get_session] = lambda: fake_session
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
