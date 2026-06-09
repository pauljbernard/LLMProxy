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
        assert payload["messages"][0]["content"][0]["text"] == "Design a bounded context."
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
    assert result["finish_reason"] == "stop"
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
    assert chunks[-1]["finish_reason"] == "stop"
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


def test_anthropic_provider_omits_temperature_for_claude_fable_models() -> None:
    request = ChatCompletionRequest.model_validate(
        {
            "model": "claude-fable-5",
            "messages": [{"role": "user", "content": "Ping"}],
            "temperature": 0.2,
        }
    )

    def handler(request_http: httpx.Request) -> httpx.Response:
        payload = json.loads(request_http.content.decode("utf-8"))
        assert "temperature" not in payload
        return httpx.Response(
            200,
            json={
                "id": "msg_fable",
                "model": "claude-fable-5",
                "content": [{"type": "text", "text": "Accepted."}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 5, "output_tokens": 1},
            },
        )

    provider = AnthropicProvider(
        "claude-fable-5",
        api_key="test-anthropic-key",
        base_url="https://api.anthropic.com/v1",
        transport=httpx.MockTransport(handler),
    )

    result = asyncio.run(provider.invoke(request))
    assert result["content"] == "Accepted."


async def _collect(stream) -> list[dict[str, object]]:
    return [chunk async for chunk in stream]


def test_anthropic_provider_healthcheck_uses_messages_endpoint() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/messages"
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["max_tokens"] == 1
        assert payload["messages"][0]["content"] == "ping"
        return httpx.Response(200, json={"id": "msg_ping"})

    provider = AnthropicProvider(
        "claude-3-5-sonnet",
        api_key="test-anthropic-key",
        base_url="https://api.anthropic.com/v1",
        transport=httpx.MockTransport(handler),
    )

    result = asyncio.run(provider.healthcheck())
    assert result["ok"] is True


def test_anthropic_provider_healthcheck_marks_missing_model_unhealthy() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={
                "type": "error",
                "error": {
                    "type": "not_found_error",
                    "message": "model: claude-3-5-sonnet",
                },
            },
        )

    provider = AnthropicProvider(
        "claude-3-5-sonnet",
        api_key="test-anthropic-key",
        base_url="https://api.anthropic.com/v1",
        transport=httpx.MockTransport(handler),
    )

    result = asyncio.run(provider.healthcheck())
    assert result["ok"] is False
    assert result["status_code"] == 404
    assert result["detail"] == "model: claude-3-5-sonnet"


def test_anthropic_provider_healthcheck_omits_temperature_for_claude_fable_models() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["model"] == "claude-fable-5"
        assert "temperature" not in payload
        return httpx.Response(200, json={"id": "msg_ping"})

    provider = AnthropicProvider(
        "claude-fable-5",
        api_key="test-anthropic-key",
        base_url="https://api.anthropic.com/v1",
        transport=httpx.MockTransport(handler),
    )

    result = asyncio.run(provider.healthcheck())
    assert result["ok"] is True


def test_anthropic_provider_healthcheck_omits_temperature_for_claude_opus_4_8_models() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["model"] == "claude-opus-4-8"
        assert "temperature" not in payload
        return httpx.Response(200, json={"id": "msg_ping"})

    provider = AnthropicProvider(
        "claude-opus-4-8",
        api_key="test-anthropic-key",
        base_url="https://api.anthropic.com/v1",
        transport=httpx.MockTransport(handler),
    )

    result = asyncio.run(provider.healthcheck())
    assert result["ok"] is True


def test_anthropic_provider_lists_available_models_with_pagination() -> None:
    calls: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.params.get("after_id"))
        assert request.url.path == "/v1/models"
        if request.url.params.get("after_id") == "claude-sonnet-4-6":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "claude-fable-5",
                            "max_tokens": 64000,
                            "type": "model",
                        }
                    ],
                    "has_more": False,
                    "last_id": "claude-fable-5",
                },
            )
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "claude-sonnet-4-6",
                        "max_tokens": 128000,
                        "type": "model",
                    }
                ],
                "has_more": True,
                "last_id": "claude-sonnet-4-6",
            },
        )

    provider = AnthropicProvider(
        "claude-sonnet-4-6",
        api_key="test-anthropic-key",
        base_url="https://api.anthropic.com/v1",
        transport=httpx.MockTransport(handler),
    )

    result = asyncio.run(provider.list_models())

    assert [item.model_id for item in result] == ["claude-sonnet-4-6", "claude-fable-5"]
    by_model_id = {item.model_id: item for item in result}
    assert by_model_id["claude-sonnet-4-6"].request_shape.accepts_temperature is True
    assert by_model_id["claude-fable-5"].request_shape.accepts_temperature is False
    assert calls == [None, "claude-sonnet-4-6"]


def test_anthropic_provider_maps_tool_calls_and_results() -> None:
    request = ChatCompletionRequest.model_validate(
        {
            "model": "claude-3-5-sonnet",
            "messages": [
                {"role": "system", "content": "Use tools when helpful."},
                {"role": "user", "content": "Look up record 1."},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_lookup",
                            "type": "function",
                            "function": {"name": "lookup", "arguments": "{\"id\":1}"},
                        }
                    ],
                },
                {"role": "tool", "tool_call_id": "call_lookup", "content": "Record 1 is active."},
            ],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "lookup",
                        "description": "Find a record.",
                        "parameters": {"type": "object"},
                    },
                }
            ],
            "tool_choice": {"type": "function", "function": {"name": "lookup"}},
            "metadata": {"session_id": "sess_tools"},
        }
    )

    def handler(request_http: httpx.Request) -> httpx.Response:
        payload = json.loads(request_http.content.decode("utf-8"))
        assert payload["system"] == "Use tools when helpful."
        assert payload["tools"][0]["name"] == "lookup"
        assert payload["tool_choice"] == {"type": "tool", "name": "lookup"}
        assert payload["messages"][1]["content"][0]["type"] == "tool_use"
        assert payload["messages"][2]["content"][0]["type"] == "tool_result"
        return httpx.Response(
            200,
            json={
                "id": "msg_tools",
                "model": "claude-3-5-sonnet",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_lookup",
                        "name": "lookup",
                        "input": {"id": 1},
                    }
                ],
                "stop_reason": "tool_use",
                "usage": {"input_tokens": 18, "output_tokens": 3},
            },
        )

    provider = AnthropicProvider(
        "claude-3-5-sonnet",
        api_key="test-anthropic-key",
        base_url="https://api.anthropic.com/v1",
        transport=httpx.MockTransport(handler),
    )

    result = asyncio.run(provider.invoke(request))
    assert result["finish_reason"] == "tool_calls"
    assert result["tool_calls"][0]["function"]["name"] == "lookup"


def test_anthropic_provider_streams_tool_use_chunks() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["stream"] is True
        return httpx.Response(
            200,
            text=(
                'event: content_block_start\n'
                'data: {"type":"content_block_start","index":0,"content_block":{"type":"tool_use","id":"toolu_1","name":"lookup","input":{}}}\n\n'
                'event: content_block_delta\n'
                'data: {"type":"content_block_delta","index":0,"delta":{"type":"input_json_delta","partial_json":"{\\"id\\":1}"}}\n\n'
                'event: message_delta\n'
                'data: {"type":"message_delta","delta":{"stop_reason":"tool_use"},"usage":{"input_tokens":12,"output_tokens":2}}\n\n'
            ),
        )

    provider = AnthropicProvider(
        "claude-3-5-sonnet",
        api_key="test-anthropic-key",
        base_url="https://api.anthropic.com/v1",
        transport=httpx.MockTransport(handler),
    )

    chunks = asyncio.run(_collect(provider.stream_chat(_request())))

    assert chunks[0]["tool_calls"][0]["function"]["name"] == "lookup"
    assert chunks[1]["tool_calls"][0]["function"]["arguments"] == '{"id":1}'
    assert chunks[-1]["finish_reason"] == "tool_calls"
