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

    async def get(self, model, key):
        return self.sync_session.get(model, key)


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
    assert payload["usage"]["prompt_tokens"] == 14
    assert payload["usage"]["completion_tokens"] == 5
    assert payload["usage"]["total_tokens"] == 19
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
    assert payload["usage"]["prompt_tokens"] == 14
    assert payload["usage"]["completion_tokens"] == 4


def test_chat_completions_returns_tool_calls(monkeypatch) -> None:
    from app.api import openai_compatible
    from app.api.dependencies import get_async_session

    openai = OpenAIProvider(
        "gpt-5.5",
        api_key="test-openai-key",
        base_url="https://api.openai.com/v1",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "id": "chatcmpl_tools",
                    "model": "gpt-5.5",
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": "",
                                "tool_calls": [
                                    {
                                        "id": "call_1",
                                        "type": "function",
                                        "function": {"name": "lookup", "arguments": "{\"id\":1}"},
                                    }
                                ],
                            },
                            "finish_reason": "tool_calls",
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13},
                },
            )
        ),
    )
    monkeypatch.setattr(
        openai_compatible,
        "get_provider_registry",
        lambda settings, session=None: {"openai": openai, "ollama": OllamaProvider("qwen2.5-coder:14b")},
    )
    fake_session = FakeSession()
    fake_async_session = FakeAsyncSession(fake_session)
    app.dependency_overrides[get_async_session] = lambda: fake_async_session
    client = TestClient(app)
    response = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer change-me"},
        json={
            "model": "gpt-5.5",
            "messages": [{"role": "user", "content": "Look this up."}],
            "tool_choice": {"type": "function", "function": {"name": "lookup"}},
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "lookup",
                        "parameters": {"type": "object"},
                    },
                }
            ],
            "metadata": {"session_id": "sess_tools", "domain_hint": "general"},
        },
    )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["choices"][0]["finish_reason"] == "tool_calls"
    assert payload["choices"][0]["message"]["tool_calls"][0]["function"]["name"] == "lookup"
    assert payload["usage"]["prompt_tokens"] == 10
    assert payload["usage"]["completion_tokens"] == 3


def test_chat_completions_rejects_disallowed_virtual_key_model(monkeypatch) -> None:
    from app.api import openai_compatible
    from app.api.dependencies import AuthPrincipal, get_async_session, require_api_token

    monkeypatch.setattr(
        openai_compatible,
        "get_provider_registry",
        lambda settings, session=None: {"openai": OpenAIProvider("gpt-5.5", api_key="unused")},
    )

    fake_session = FakeSession()
    fake_async_session = FakeAsyncSession(fake_session)
    app.dependency_overrides[get_async_session] = lambda: fake_async_session
    app.dependency_overrides[require_api_token] = lambda: AuthPrincipal(
        token="sk-test-secret",
        role="api",
        key_id="vkey_denied",
        models_allowed=("proxy-local",),
        spend_usd=0.0,
        max_budget_usd=10.0,
    )
    client = TestClient(app)
    response = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer sk-test-secret"},
        json={
            "model": "gpt-5.5",
            "messages": [{"role": "user", "content": "Hello"}],
            "metadata": {"session_id": "sess_virtual"},
        },
    )
    app.dependency_overrides.clear()

    assert response.status_code == 403


def test_chat_completions_rejects_exhausted_virtual_key_budget(monkeypatch) -> None:
    from app.api import openai_compatible
    from app.api.dependencies import AuthPrincipal, get_async_session, require_api_token

    monkeypatch.setattr(
        openai_compatible,
        "get_provider_registry",
        lambda settings, session=None: {"openai": OpenAIProvider("gpt-5.5", api_key="unused")},
    )

    fake_session = FakeSession()
    fake_async_session = FakeAsyncSession(fake_session)
    app.dependency_overrides[get_async_session] = lambda: fake_async_session
    app.dependency_overrides[require_api_token] = lambda: AuthPrincipal(
        token="sk-budget-secret",
        role="api",
        key_id="vkey_budget",
        models_allowed=("gpt-5.5",),
        spend_usd=10.0,
        max_budget_usd=10.0,
    )
    client = TestClient(app)
    response = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer sk-budget-secret"},
        json={
            "model": "gpt-5.5",
            "messages": [{"role": "user", "content": "Hello"}],
            "metadata": {"session_id": "sess_budget"},
        },
    )
    app.dependency_overrides.clear()

    assert response.status_code == 429


def test_chat_completions_streams_ollama_sse_and_persists(monkeypatch) -> None:
    from app.api import openai_compatible
    from app.api.dependencies import get_async_session

    ollama = OllamaProvider(
        "qwen2.5-coder:14b",
        base_url="http://localhost:11434",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                text=(
                    '{"model":"qwen2.5-coder:14b","message":{"role":"assistant","content":"Ollama "},"done":false}\n'
                    '{"model":"qwen2.5-coder:14b","message":{"role":"assistant","content":"coding answer."},"done":true,"done_reason":"stop","prompt_eval_count":14,"eval_count":2}\n'
                ),
            )
        ),
    )
    monkeypatch.setattr(
        openai_compatible,
        "get_provider_registry",
        lambda settings, session=None: {
            "ollama": ollama,
            "openai": OpenAIProvider("gpt-5.5", api_key="unused"),
        },
    )
    fake_session = FakeSession()
    fake_async_session = FakeAsyncSession(fake_session)
    app.dependency_overrides[get_async_session] = lambda: fake_async_session
    client = TestClient(app)
    with client.stream(
        "POST",
        "/v1/chat/completions",
        headers={"Authorization": "Bearer change-me"},
        json={
            "model": "proxy-auto",
            "stream": True,
            "messages": [{"role": "user", "content": "Review this coding patch."}],
            "metadata": {
                "session_id": "sess_stream",
                "domain_hint": "coding",
                "task_type_hint": "code_review",
            },
        },
    ) as response:
        payload = response.read().decode("utf-8")
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert 'data: {"id":' in payload
    assert '"object": "chat.completion.chunk"' in payload
    assert '"content": "Ollama "' in payload
    assert '"content": "coding answer."' in payload
    assert "data: [DONE]" in payload
    assert fake_session.committed is True
    assert len(fake_session.items) == 5


def test_chat_completions_streams_when_selected_provider_not_in_registry(monkeypatch) -> None:
    from app.api import openai_compatible
    from app.api.dependencies import get_async_session

    class FakeDecision:
        def __init__(self) -> None:
            self.routing_decision_id = "route_missing_provider"
            self.session_id = "sess_missing_provider"
            self.policy_version = "test-policy"
            self.selected_provider = "missing-provider"
            self.selected_provider_family = "Missing"
            self.selected_model = "fallback-model"
            self.selected_mode = "fallback"
            self.decision_rationale = "fallback"
            self.predicted_cost_class = "medium"
            self.predicted_latency_class = "medium"
            self.ranked_alternatives = []
            self.fallback_chain = []

    class FakeRoute:
        def __init__(self) -> None:
            self.provider_key = "openai"
            self.decision = FakeDecision()
            self.shadow_provider_keys = []

    class FakeStreamingProvider:
        supports_streaming = True

    async def fake_stream_with_fallback(settings, provider_registry, selected_route, request):
        yield (
            {
                "model": "fallback-model",
                "delta": "Recovered stream.",
                "finish_reason": "stop",
                "input_tokens": 3,
                "output_tokens": 2,
            },
            selected_route.decision,
        )

    async def fake_resolve_route_and_registry(*args, **kwargs):
        return FakeRoute(), {"openai": FakeStreamingProvider()}

    monkeypatch.setattr(openai_compatible, "_stream_with_fallback", fake_stream_with_fallback)
    monkeypatch.setattr(openai_compatible, "_resolve_route_and_registry", fake_resolve_route_and_registry)

    fake_session = FakeSession()
    fake_async_session = FakeAsyncSession(fake_session)
    app.dependency_overrides[get_async_session] = lambda: fake_async_session
    client = TestClient(app)
    with client.stream(
        "POST",
        "/v1/chat/completions",
        headers={"Authorization": "Bearer change-me"},
        json={
            "model": "proxy-auto",
            "stream": True,
            "messages": [{"role": "user", "content": "Handle fallback safely."}],
            "metadata": {"session_id": "sess_missing_provider", "domain_hint": "general"},
        },
    ) as response:
        payload = response.read().decode("utf-8")
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert '"content": "Recovered stream."' in payload
    assert "data: [DONE]" in payload


def test_invoke_provider_with_retries_recovers_after_transient_failure(monkeypatch) -> None:
    from app.api import openai_compatible
    from app.config import Settings
    from app.services.provider_health import clear_provider_health_state

    clear_provider_health_state()

    class FlakyProvider:
        def __init__(self):
            self.attempts = 0

        async def invoke(self, request):
            self.attempts += 1
            if self.attempts == 1:
                raise RuntimeError("transient")
            return {
                "model": "gpt-5.5",
                "content": "ok",
                "input_tokens": 1,
                "output_tokens": 1,
                "finish_reason": "stop",
                "cost_estimate": 0.1,
                "latency_ms": 1,
                "provider": "openai",
                "provider_family": "OpenAI",
                "raw_response": {},
            }

    from app.schemas.chat import ChatCompletionRequest
    provider = FlakyProvider()

    response = __import__("asyncio").run(
        openai_compatible._invoke_provider_with_retries(
            settings=Settings(llmproxy_provider_max_retries=2, llmproxy_provider_retry_backoff_seconds=0.0),
            provider_key="openai",
            provider=provider,
            request=ChatCompletionRequest.model_validate(
                {
                    "model": "gpt-5.5",
                    "messages": [{"role": "user", "content": "Hello"}],
                    "metadata": {"session_id": "sess_retry"},
                }
            ),
        )
    )

    assert provider.attempts == 2
    assert response["content"] == "ok"


def test_invoke_provider_with_retries_cools_down_after_repeated_failures() -> None:
    from app.api import openai_compatible
    from app.config import Settings
    from app.services.provider_health import clear_provider_health_state, is_provider_cooled_down
    from app.schemas.chat import ChatCompletionRequest

    clear_provider_health_state()

    class FailingProvider:
        def __init__(self):
            self.attempts = 0

        async def invoke(self, request):
            self.attempts += 1
            raise RuntimeError("always failing")

    provider = FailingProvider()
    request = ChatCompletionRequest.model_validate(
        {
            "model": "gpt-5.5",
            "messages": [{"role": "user", "content": "Hello"}],
            "metadata": {"session_id": "sess_cooldown"},
        }
    )

    try:
        __import__("asyncio").run(
            openai_compatible._invoke_provider_with_retries(
                settings=Settings(
                    llmproxy_provider_max_retries=1,
                    llmproxy_provider_retry_backoff_seconds=0.0,
                    llmproxy_provider_allowed_fails=2,
                    llmproxy_provider_cooldown_seconds=60,
                ),
                provider_key="openai",
                provider=provider,
                request=request,
            )
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("Expected provider failure")

    assert provider.attempts == 2
    assert is_provider_cooled_down("openai") is True


def test_chat_completions_rejects_when_request_exceeds_provider_limits(monkeypatch) -> None:
    from app.api import openai_compatible
    from app.api.dependencies import get_async_session

    class LimitedProvider:
        provider_name = "openai"
        provider_family = "OpenAI"
        supports_streaming = False
        capability = type("Capability", (), {"max_context_tokens": 10, "max_output_tokens": 4})()

        async def invoke(self, request):
            raise AssertionError("Provider should not be invoked when limits are exceeded")

    monkeypatch.setattr(
        openai_compatible,
        "get_provider_registry",
        lambda settings, session=None: {"openai": LimitedProvider()},
    )
    fake_session = FakeSession()
    fake_async_session = FakeAsyncSession(fake_session)
    app.dependency_overrides[get_async_session] = lambda: fake_async_session
    client = TestClient(app)
    response = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer change-me"},
        json={
            "model": "gpt-5.5",
            "max_tokens": 8,
            "messages": [{"role": "user", "content": "one two three four five six"}],
            "metadata": {"session_id": "sess_limit"},
        },
    )
    app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "context window" in response.json()["detail"].lower()


def test_chat_completions_uses_response_cache_for_repeated_non_stream_request(monkeypatch) -> None:
    from app.api import openai_compatible
    from app.api.dependencies import get_async_session, get_runtime_settings
    from app.config import Settings
    from app.services.response_cache import clear_response_cache

    clear_response_cache()

    class CountingProvider:
        provider_name = "openai"
        provider_family = "OpenAI"
        supports_streaming = False
        capability = type("Capability", (), {"max_context_tokens": 128000, "max_output_tokens": 8192})()

        def __init__(self):
            self.calls = 0

        async def invoke(self, request):
            self.calls += 1
            return {
                "model": "gpt-5.5",
                "content": "cached answer",
                "input_tokens": 4,
                "output_tokens": 2,
                "finish_reason": "stop",
                "cost_estimate": 0.01,
                "latency_ms": 1,
                "provider": "openai",
                "provider_family": "OpenAI",
                "raw_response": {"calls": self.calls},
            }

    provider = CountingProvider()
    monkeypatch.setattr(
        openai_compatible,
        "get_provider_registry",
        lambda settings, session=None: {"openai": provider},
    )
    app.dependency_overrides[get_runtime_settings] = lambda: Settings(
        llmproxy_response_cache_enabled=True,
        llmproxy_response_cache_ttl_seconds=300,
    )
    fake_session = FakeSession()
    fake_async_session = FakeAsyncSession(fake_session)
    app.dependency_overrides[get_async_session] = lambda: fake_async_session
    client = TestClient(app)
    body = {
        "model": "gpt-5.5",
        "messages": [{"role": "user", "content": "Hello cache"}],
        "metadata": {"session_id": "sess_cache"},
    }
    first = client.post("/v1/chat/completions", headers={"Authorization": "Bearer change-me"}, json=body)
    second = client.post("/v1/chat/completions", headers={"Authorization": "Bearer change-me"}, json=body)
    app.dependency_overrides.clear()

    assert first.status_code == 200
    assert second.status_code == 200
    assert provider.calls == 1
    assert second.json()["choices"][0]["message"]["content"] == "cached answer"


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
