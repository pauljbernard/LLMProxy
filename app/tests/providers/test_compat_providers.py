import asyncio
import json

import httpx
import pytest

from app.config import Settings
from app.providers.cohere_provider import CohereProvider
from app.providers.cloudflare_workers_ai_provider import CloudflareWorkersAIProvider
from app.providers.deepseek_provider import DeepSeekProvider
from app.providers.fireworks_provider import FireworksProvider
from app.providers.groq_provider import GroqProvider
from app.providers.huggingface_tgi_provider import HuggingFaceTGIProvider
from app.providers.mistral_provider import MistralProvider
from app.providers.perplexity_provider import PerplexityProvider
from app.providers.together_provider import TogetherProvider
from app.providers.vertex_ai_provider import VertexAIProvider
from app.providers.base import ProviderConfigurationError
from app.schemas.chat import ChatCompletionRequest


def _request(**overrides) -> ChatCompletionRequest:
    payload = {
        "model": "proxy-auto",
        "messages": [{"role": "user", "content": "Hello there"}],
        "metadata": {"session_id": "sess_provider"},
    }
    payload.update(overrides)
    return ChatCompletionRequest.model_validate(payload)


@pytest.mark.parametrize(
    ("provider_cls", "provider_name", "base_url", "model_id", "api_key"),
    [
        (GroqProvider, "groq", "https://api.groq.com/openai/v1", "llama-3.3-70b-versatile", "test-groq-key"),
        (MistralProvider, "mistral", "https://api.mistral.ai/v1", "mistral-large-latest", "test-mistral-key"),
        (DeepSeekProvider, "deepseek", "https://api.deepseek.com", "deepseek-v4-flash", "test-deepseek-key"),
        (TogetherProvider, "together", "https://api.together.ai/v1", "openai/gpt-oss-20b", "test-together-key"),
        (FireworksProvider, "fireworks", "https://api.fireworks.ai/inference/v1", "accounts/fireworks/models/llama-v3p1-8b-instruct", "test-fireworks-key"),
        (PerplexityProvider, "perplexity", "https://api.perplexity.ai/v1", "sonar-pro", "test-perplexity-key"),
        (VertexAIProvider, "vertex_ai", "https://aiplatform.googleapis.com/v1/projects/demo/locations/global/endpoints/openapi", "google/gemini-2.5-pro", "test-vertex-token"),
        (HuggingFaceTGIProvider, "huggingface_tgi", "http://localhost:3000/v1", "tgi", "test-hf-key"),
    ],
)
def test_openai_compatible_frontier_providers_normalize_chat_response(
    provider_cls,
    provider_name: str,
    base_url: str,
    model_id: str,
    api_key: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/chat/completions" or request.url.path.endswith("/chat/completions")
        assert request.headers["authorization"] == f"Bearer {api_key}"
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["model"] == model_id
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl_provider",
                "model": model_id,
                "choices": [
                    {
                        "message": {"role": "assistant", "content": f"{provider_name} answer"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
            },
        )

    provider = provider_cls(
        model_id,
        api_key=api_key,
        base_url=base_url,
        transport=httpx.MockTransport(handler),
    )

    result = asyncio.run(provider.invoke(_request()))

    assert result["provider"] == provider_name
    assert result["model"] == model_id
    assert result["content"] == f"{provider_name} answer"
    assert result["input_tokens"] == 5
    assert result["output_tokens"] == 2


def test_cohere_provider_omits_unsupported_openai_compatibility_fields() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        assert "logit_bias" not in payload
        assert "top_logprobs" not in payload
        assert "n" not in payload
        assert "parallel_tool_calls" not in payload
        assert payload["tool_choice"] == {"type": "function", "function": {"name": "lookup"}}
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl_cohere",
                "model": "command-a-plus-05-2026",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "cohere answer"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
            },
        )

    provider = CohereProvider(
        "command-a-plus-05-2026",
        api_key="test-cohere-key",
        base_url="https://api.cohere.ai/compatibility/v1",
        transport=httpx.MockTransport(handler),
    )
    request = _request(
        n=2,
        logit_bias={"42": -5},
        top_logprobs=2,
        parallel_tool_calls=False,
        tool_choice={"type": "function", "function": {"name": "lookup"}},
    )

    result = asyncio.run(provider.invoke(request))

    assert result["provider"] == "cohere"
    assert result["content"] == "cohere answer"


def test_cloudflare_workers_ai_provider_normalizes_native_run_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/accounts/test-account/ai/run/@cf/moonshotai/kimi-k2.5")
        assert request.headers["authorization"] == "Bearer test-cloudflare-token"
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["messages"][0]["content"] == "Hello there"
        return httpx.Response(
            200,
            json={
                "success": True,
                "result": {
                    "response": "cloudflare answer",
                    "usage": {"prompt_tokens": 6, "completion_tokens": 2, "total_tokens": 8},
                },
            },
        )

    provider = CloudflareWorkersAIProvider(
        "@cf/moonshotai/kimi-k2.5",
        account_id="test-account",
        api_token="test-cloudflare-token",
        transport=httpx.MockTransport(handler),
    )

    result = asyncio.run(provider.invoke(_request()))

    assert result["provider"] == "cloudflare_workers_ai"
    assert result["content"] == "cloudflare answer"
    assert result["input_tokens"] == 6
    assert result["output_tokens"] == 2


def test_cloudflare_workers_ai_provider_healthcheck_uses_native_run_endpoint() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/accounts/test-account/ai/run/@cf/moonshotai/kimi-k2.5")
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["max_tokens"] == 1
        assert payload["messages"][0]["content"] == "ping"
        return httpx.Response(200, json={"success": True, "result": {"response": "pong"}})

    provider = CloudflareWorkersAIProvider(
        "@cf/moonshotai/kimi-k2.5",
        account_id="test-account",
        api_token="test-cloudflare-token",
        transport=httpx.MockTransport(handler),
    )

    result = asyncio.run(provider.healthcheck())
    assert result["ok"] is True


def test_vertex_ai_provider_builds_base_url_from_settings() -> None:
    settings = Settings(
        llmproxy_vertex_ai_access_token="vertex-token",
        llmproxy_vertex_ai_project_id="demo-project",
        llmproxy_vertex_ai_location="us-central1",
    )

    provider = VertexAIProvider.from_settings(settings)

    assert provider.base_url == (
        "https://aiplatform.googleapis.com/v1/projects/demo-project/"
        "locations/us-central1/endpoints/openapi"
    )


@pytest.mark.parametrize(
    ("provider", "expected_field"),
    [
        (GroqProvider("llama-3.3-70b-versatile"), "llmproxy_groq_api_key"),
        (MistralProvider("mistral-large-latest"), "llmproxy_mistral_api_key"),
        (DeepSeekProvider("deepseek-v4-flash"), "llmproxy_deepseek_api_key"),
        (PerplexityProvider("sonar-pro"), "llmproxy_perplexity_api_key"),
        (VertexAIProvider("google/gemini-2.5-pro"), "llmproxy_vertex_ai_access_token"),
    ],
)
def test_openai_compatible_subclasses_report_provider_specific_missing_api_key(provider, expected_field: str) -> None:
    with pytest.raises(ProviderConfigurationError) as exc_info:
        asyncio.run(provider.healthcheck())
    assert expected_field in str(exc_info.value)
