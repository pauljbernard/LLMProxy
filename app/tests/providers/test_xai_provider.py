import asyncio
import json

import httpx
import pytest

from app.providers.base import ProviderConfigurationError
from app.providers.xai_provider import XAIProvider
from app.schemas.chat import ChatCompletionRequest


def _request() -> ChatCompletionRequest:
    return ChatCompletionRequest.model_validate(
        {
            "model": "proxy-auto",
            "messages": [{"role": "user", "content": "Explain this systems tradeoff."}],
            "metadata": {"session_id": "sess_xai"},
        }
    )


def test_xai_provider_normalizes_chat_completion_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test-xai-key"
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["model"] == "grok-3-mini"
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl_xai",
                "model": "grok-3-mini",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "xAI answer."},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
            },
        )

    provider = XAIProvider(
        "grok-3-mini",
        api_key="test-xai-key",
        base_url="https://api.x.ai/v1",
        transport=httpx.MockTransport(handler),
    )

    result = asyncio.run(provider.invoke(_request()))

    assert result["model"] == "grok-3-mini"
    assert result["content"] == "xAI answer."
    assert result["provider"] == "xai"
    assert result["provider_family"] == "xAI"
    assert result["input_tokens"] == 10
    assert result["output_tokens"] == 2


def test_xai_provider_requires_api_key() -> None:
    provider = XAIProvider("grok-3-mini")

    with pytest.raises(ProviderConfigurationError):
        asyncio.run(provider.chat(_request()))
