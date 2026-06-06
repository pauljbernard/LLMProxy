import httpx
from fastapi.testclient import TestClient

from app.providers.anthropic_provider import AnthropicProvider
from app.providers.google_provider import GoogleProvider
from app.providers.ollama import OllamaProvider
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


def test_list_models_requires_auth() -> None:
    client = TestClient(app)
    response = client.get("/v1/models")
    assert response.status_code == 401


def test_list_models_returns_proxy_and_provider_models() -> None:
    client = TestClient(app)
    response = client.get("/v1/models", headers={"Authorization": "Bearer change-me"})
    assert response.status_code == 200
    payload = response.json()
    model_ids = {item["id"] for item in payload}
    assert "proxy-auto" in model_ids
    assert "qwen2.5-coder:14b" in model_ids
    assert "gpt-5.5" in model_ids
    assert "claude-3-5-sonnet" in model_ids
    assert "gemini-2.5-pro" in model_ids
    assert "grok-3-mini" in model_ids
    assert len(payload) == len(model_ids)


def test_embeddings_requires_auth() -> None:
    client = TestClient(app)
    response = client.post("/v1/embeddings", json={"model": "text-embedding-3-small", "input": "hello world"})
    assert response.status_code == 401


def test_embeddings_returns_provider_vectors(monkeypatch) -> None:
    from app.api import openai_compatible
    from app.api.dependencies import get_runtime_settings
    from app.config import Settings

    openai = OpenAIProvider(
        "gpt-5.5",
        api_key="test-openai-key",
        base_url="https://api.openai.com/v1",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "data": [
                        {"embedding": [0.1, 0.2, 0.3], "index": 0},
                        {"embedding": [0.4, 0.5, 0.6], "index": 1},
                    ],
                    "model": "text-embedding-3-small",
                    "usage": {"prompt_tokens": 4, "total_tokens": 4},
                },
            )
        ),
    )
    monkeypatch.setattr(
        openai_compatible,
        "get_provider_registry",
        lambda settings, session=None: {"openai": openai},
    )
    app.dependency_overrides[get_runtime_settings] = lambda: Settings(llmproxy_openai_api_key="test-openai-key")
    client = TestClient(app)
    response = client.post(
        "/v1/embeddings",
        headers={"Authorization": "Bearer change-me"},
        json={"model": "text-embedding-3-small", "input": ["hello world", "goodbye world"]},
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["object"] == "list"
    assert payload["model"] == "text-embedding-3-small"
    assert len(payload["data"]) == 2
    assert payload["data"][0]["object"] == "embedding"
    assert payload["data"][0]["embedding"] == [0.1, 0.2, 0.3]
    assert payload["data"][1]["embedding"] == [0.4, 0.5, 0.6]
    assert payload["data"][0]["embedding"] != payload["data"][1]["embedding"]
    assert payload["usage"]["prompt_tokens"] == 4


def test_embeddings_rejects_mismatched_embedding_provider(monkeypatch) -> None:
    from app.api import openai_compatible

    ollama = OllamaProvider(
        "qwen2.5-coder:14b",
        base_url="http://localhost:11434",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"embeddings": [[0.1, 0.2, 0.3]]})
        ),
    )
    monkeypatch.setattr(
        openai_compatible,
        "get_provider_registry",
        lambda settings, session=None: {"ollama": ollama},
    )
    client = TestClient(app)
    response = client.post(
        "/v1/embeddings",
        headers={"Authorization": "Bearer change-me"},
        json={"model": "text-embedding-3-small", "input": "hello world"},
    )

    assert response.status_code == 501


def test_chat_completions_routes_and_persists(monkeypatch) -> None:
    import httpx

    from app.api import openai_compatible
    from app.api.dependencies import get_async_session

    ollama = OllamaProvider(
        "qwen2.5-coder:14b",
        base_url="http://localhost:11434",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "model": "qwen2.5-coder:14b",
                    "message": {"role": "assistant", "content": "Ollama coding answer."},
                    "done_reason": "stop",
                    "prompt_eval_count": 14,
                    "eval_count": 5,
                },
            )
        ),
    )
    monkeypatch.setattr(
        openai_compatible,
        "get_provider_registry",
        lambda settings, session=None: {
            "ollama": ollama,
            "openai": OpenAIProvider("gpt-5.5", api_key="unused"),
            "anthropic": AnthropicProvider("claude-3-5-sonnet", api_key="unused"),
            "google": GoogleProvider("gemini-2.5-pro", api_key="unused"),
        },
    )
    fake_session = FakeSession()
    fake_async_session = FakeAsyncSession(fake_session)
    app.dependency_overrides[get_async_session] = lambda: fake_async_session
    client = TestClient(app)
    response = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer change-me"},
        json={
            "model": "proxy-auto",
            "messages": [{"role": "user", "content": "Review this coding patch."}],
            "metadata": {
                "session_id": "sess_test",
                "domain_hint": "coding",
                "task_type_hint": "code_review",
            },
        },
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["model"] == "qwen2.5-coder:14b"
    assert payload["choices"][0]["message"]["content"] == "Ollama coding answer."
    assert payload["usage"]["total_tokens"] > 0
    assert fake_session.committed is True
    assert fake_session.flush_count == 2
    assert len(fake_session.items) == 5


def test_chat_completions_routes_architecture_to_anthropic(monkeypatch) -> None:
    from app.api import openai_compatible
    from app.api.dependencies import get_async_session

    anthropic = AnthropicProvider(
        "claude-3-5-sonnet",
        api_key="test-anthropic-key",
        base_url="https://api.anthropic.com/v1",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "id": "msg_test",
                    "model": "claude-3-5-sonnet",
                    "content": [{"type": "text", "text": "Anthropic architecture answer."}],
                    "stop_reason": "end_turn",
                    "usage": {"input_tokens": 14, "output_tokens": 4},
                },
            )
        ),
    )
    monkeypatch.setattr(
        openai_compatible,
        "get_provider_registry",
        lambda settings, session=None: {
            "anthropic": anthropic,
            "openai": OpenAIProvider("gpt-5.5", api_key="unused"),
            "google": GoogleProvider("gemini-2.5-pro", api_key="unused"),
            "ollama": OllamaProvider("qwen2.5-coder:14b"),
        },
    )

    fake_session = FakeSession()
    fake_async_session = FakeAsyncSession(fake_session)
    app.dependency_overrides[get_async_session] = lambda: fake_async_session
    client = TestClient(app)
    response = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer change-me"},
        json={
            "model": "proxy-teacher",
            "messages": [{"role": "user", "content": "Design a service boundary for this architecture."}],
            "metadata": {
                "session_id": "sess_arch",
                "domain_hint": "software_architecture",
                "task_type_hint": "design_review",
            },
        },
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["model"] == "claude-3-5-sonnet"
    assert payload["choices"][0]["message"]["content"] == "Anthropic architecture answer."


def test_chat_completions_routes_research_to_google(monkeypatch) -> None:
    from app.api import openai_compatible
    from app.api.dependencies import get_async_session

    google = GoogleProvider(
        "gemini-2.5-pro",
        api_key="test-google-key",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "candidates": [
                        {
                            "content": {"parts": [{"text": "Google research answer."}]},
                            "finishReason": "STOP",
                        }
                    ],
                    "usageMetadata": {
                        "promptTokenCount": 9,
                        "candidatesTokenCount": 3,
                        "totalTokenCount": 12,
                    },
                    "modelVersion": "gemini-2.5-pro",
                },
            )
        ),
    )
    monkeypatch.setattr(
        openai_compatible,
        "get_provider_registry",
        lambda settings, session=None: {
            "google": google,
            "openai": OpenAIProvider("gpt-5.5", api_key="unused"),
            "xai": OpenAIProvider("grok-3-mini", api_key="unused"),
            "ollama": OllamaProvider("qwen2.5-coder:14b"),
        },
    )

    fake_session = FakeSession()
    fake_async_session = FakeAsyncSession(fake_session)
    app.dependency_overrides[get_async_session] = lambda: fake_async_session
    client = TestClient(app)
    response = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer change-me"},
        json={
            "model": "proxy-auto",
            "messages": [{"role": "user", "content": "Research the tradeoffs of vector indexes."}],
            "metadata": {
                "session_id": "sess_research",
                "domain_hint": "research",
                "task_type_hint": "analysis",
            },
        },
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["model"] == "gemini-2.5-pro"
    assert payload["choices"][0]["message"]["content"] == "Google research answer."
