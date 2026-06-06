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


def test_anthropic_provider_streams_message_chunks() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["stream"] is True
        return httpx.Response(
            200,
            text=(
                'event: content_block_delta\n'
                'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Anthropic "}}\n\n'
                'event: content_block_delta\n'
                'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"stream."}}\n\n'
                'event: message_delta\n'
                'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"input_tokens":15,"output_tokens":2}}\n\n'
            ),
        )

    provider = AnthropicProvider(
        "claude-3-5-sonnet",
        api_key="test-anthropic-key",
        base_url="https://api.anthropic.com/v1",
        transport=httpx.MockTransport(handler),
    )

    chunks = asyncio.run(_collect(provider.stream_chat(_request())))

    assert [chunk["delta"] for chunk in chunks if chunk["delta"]] == ["Anthropic ", "stream."]
    assert chunks[-1]["finish_reason"] == "end_turn"
    assert chunks[-1]["input_tokens"] == 15
    assert chunks[-1]["output_tokens"] == 2


def test_anthropic_provider_maps_supported_request_parameters() -> None:
    request = ChatCompletionRequest.model_validate(
        {
            "model": "proxy-teacher",
            "messages": [{"role": "user", "content": "Design a bounded context."}],
            "top_p": 0.7,
            "stop": ["END"],
            "user": "user-42",
            "metadata": {"session_id": "sess_anthropic"},
        }
    )

    def handler(request_http: httpx.Request) -> httpx.Response:
        payload = json.loads(request_http.content.decode("utf-8"))
        assert payload["top_p"] == 0.7
        assert payload["stop_sequences"] == ["END"]
        assert payload["metadata"] == {"user_id": "user-42"}
        return httpx.Response(
            200,
            json={
                "id": "msg_456",
                "model": "claude-3-5-sonnet",
                "content": [{"type": "text", "text": "Mapped."}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 5, "output_tokens": 1},
            },
        )

    provider = AnthropicProvider(
        "claude-3-5-sonnet",
        api_key="test-anthropic-key",
        base_url="https://api.anthropic.com/v1",
        transport=httpx.MockTransport(handler),
    )

    result = asyncio.run(provider.invoke(request))
    assert result["content"] == "Mapped."


async def _collect(stream) -> list[dict[str, object]]:
    return [chunk async for chunk in stream]
