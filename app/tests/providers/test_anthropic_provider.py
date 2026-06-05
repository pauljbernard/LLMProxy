import asyncio
import json

import httpx
import pytest

from app.providers.anthropic_provider import AnthropicProvider
from app.providers.base import ProviderConfigurationError
from app.schemas.chat import ChatCompletionRequest


def _request() -> ChatCompletionRequest:
    return ChatCompletionRequest.model_validate(
        {
            "model": "proxy-teacher",
            "messages": [{"role": "user", "content": "Design a bounded context."}],
            "metadata": {"session_id": "sess_anthropic"},
        }
    )


def test_anthropic_provider_normalizes_messages_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/messages"
        assert request.headers["x-api-key"] == "test-anthropic-key"
        assert request.headers["anthropic-version"] == "2023-06-01"
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["model"] == "claude-3-5-sonnet"
        assert payload["messages"][0]["content"] == "Design a bounded context."
        return httpx.Response(
            200,
            json={
                "id": "msg_123",
                "model": "claude-3-5-sonnet",
                "content": [{"type": "text", "text": "Anthropic architecture answer."}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 15, "output_tokens": 4},
            },
        )

    provider = AnthropicProvider(
        "claude-3-5-sonnet",
        api_key="test-anthropic-key",
        base_url="https://api.anthropic.com/v1",
        transport=httpx.MockTransport(handler),
    )

    result = asyncio.run(provider.invoke(_request()))

    assert result["model"] == "claude-3-5-sonnet"
    assert result["content"] == "Anthropic architecture answer."
    assert result["input_tokens"] == 15
    assert result["output_tokens"] == 4
    assert result["finish_reason"] == "end_turn"
    assert result["provider"] == "anthropic"
    assert result["provider_family"] == "Anthropic"
    assert result["raw_response"]["id"] == "msg_123"


def test_anthropic_provider_requires_api_key() -> None:
    provider = AnthropicProvider("claude-3-5-sonnet")

    with pytest.raises(ProviderConfigurationError):
        asyncio.run(provider.chat(_request()))
