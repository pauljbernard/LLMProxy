import asyncio
import json

import httpx
import pytest

from app.providers.base import ProviderConfigurationError
from app.providers.openai_provider import OpenAIProvider
from app.schemas.chat import ChatCompletionRequest


def _request() -> ChatCompletionRequest:
    return ChatCompletionRequest.model_validate(
        {
            "model": "proxy-auto",
            "messages": [{"role": "user", "content": "Summarize this patch."}],
            "metadata": {"session_id": "sess_provider"},
        }
    )


def test_openai_provider_normalizes_chat_completion_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test-openai-key"
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["model"] == "gpt-5.5"
        assert payload["messages"][0]["role"] == "user"
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl_123",
                "model": "gpt-5.5",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "Patch summary."},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 11,
                    "completion_tokens": 2,
                    "total_tokens": 13,
                },
            },
        )

    provider = OpenAIProvider(
        "gpt-5.5",
        api_key="test-openai-key",
        base_url="https://api.openai.com/v1",
        transport=httpx.MockTransport(handler),
    )

    result = asyncio.run(provider.invoke(_request()))

    assert result["model"] == "gpt-5.5"
    assert result["content"] == "Patch summary."
    assert result["input_tokens"] == 11
    assert result["output_tokens"] == 2
    assert result["finish_reason"] == "stop"
    assert result["provider"] == "openai"
    assert result["provider_family"] == "OpenAI"
    assert result["latency_ms"] >= 0
    assert result["raw_response"]["id"] == "chatcmpl_123"


def test_openai_provider_passes_through_modern_chat_parameters() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["top_p"] == 0.9
        assert payload["n"] == 2
        assert payload["stop"] == ["END"]
        assert payload["presence_penalty"] == 0.3
        assert payload["frequency_penalty"] == 0.1
        assert payload["seed"] == 7
        assert payload["logit_bias"] == {"42": -5}
        assert payload["logprobs"] is True
        assert payload["top_logprobs"] == 2
        assert payload["user"] == "user-123"
        assert payload["response_format"] == {"type": "json_object", "json_schema": None}
        assert payload["parallel_tool_calls"] is False
        assert payload["tool_choice"] == {"type": "function", "function": {"name": "lookup"}}
        assert payload["tools"][0]["function"]["name"] == "lookup"
        assert payload["functions"][0]["name"] == "legacy_lookup"
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl_456",
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
                "usage": {"prompt_tokens": 9, "completion_tokens": 3, "total_tokens": 12},
            },
        )

    provider = OpenAIProvider(
        "gpt-5.5",
        api_key="test-openai-key",
        base_url="https://api.openai.com/v1",
        transport=httpx.MockTransport(handler),
    )
    request = ChatCompletionRequest.model_validate(
        {
            "model": "proxy-auto",
            "messages": [{"role": "user", "content": "Find this record."}],
            "top_p": 0.9,
            "n": 2,
            "stop": ["END"],
            "presence_penalty": 0.3,
            "frequency_penalty": 0.1,
            "seed": 7,
            "logit_bias": {"42": -5},
            "logprobs": True,
            "top_logprobs": 2,
            "user": "user-123",
            "response_format": {"type": "json_object"},
            "parallel_tool_calls": False,
            "tool_choice": {"type": "function", "function": {"name": "lookup"}},
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "lookup",
                        "description": "Lookup a record",
                        "parameters": {"type": "object"},
                    },
                }
            ],
            "functions": [{"name": "legacy_lookup", "parameters": {"type": "object"}}],
            "metadata": {"session_id": "sess_provider"},
        }
    )

    result = asyncio.run(provider.invoke(request))

    assert result["finish_reason"] == "tool_calls"
    assert result["tool_calls"][0]["function"]["name"] == "lookup"


def test_openai_provider_uses_request_timeout_override(monkeypatch) -> None:
    provider = OpenAIProvider(
        "gpt-5.5",
        api_key="test-openai-key",
        base_url="https://api.openai.com/v1",
    )
    request = ChatCompletionRequest.model_validate(
        {
            "model": "proxy-auto",
            "messages": [{"role": "user", "content": "Hello"}],
            "timeout_seconds": 5.5,
            "metadata": {"session_id": "sess_provider"},
        }
    )
    captured: dict[str, float] = {}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, path: str, json: dict[str, object]):
            return httpx.Response(
                200,
                request=httpx.Request("POST", f"https://api.openai.com/v1{path}"),
                json={
                    "id": "chatcmpl_timeout",
                    "model": "gpt-5.5",
                    "choices": [{"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                },
            )

    def fake_client(*, base_url: str, headers=None, timeout_seconds=None):
        captured["timeout_seconds"] = timeout_seconds
        return _Client()

    monkeypatch.setattr(provider, "_client", fake_client)

    result = asyncio.run(provider.chat(request))

    assert captured["timeout_seconds"] == 5.5
    assert result["content"] == "ok"


def test_openai_provider_requires_api_key() -> None:
    provider = OpenAIProvider("gpt-5.5")

    with pytest.raises(ProviderConfigurationError):
        asyncio.run(provider.chat(_request()))


def test_openai_provider_streams_chat_chunks() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["stream"] is True
        return httpx.Response(
            200,
            text=(
                'data: {"id":"chatcmpl_123","model":"gpt-5.5","choices":[{"delta":{"content":"Patch "},"finish_reason":null}]}\n\n'
                'data: {"id":"chatcmpl_123","model":"gpt-5.5","choices":[{"delta":{"content":"summary."},"finish_reason":"stop"}],"usage":{"prompt_tokens":11,"completion_tokens":2}}\n\n'
                "data: [DONE]\n\n"
            ),
        )

    provider = OpenAIProvider(
        "gpt-5.5",
        api_key="test-openai-key",
        base_url="https://api.openai.com/v1",
        transport=httpx.MockTransport(handler),
    )

    chunks = asyncio.run(_collect(provider.stream_chat(_request())))

    assert [chunk["delta"] for chunk in chunks] == ["Patch ", "summary."]
    assert chunks[-1]["finish_reason"] == "stop"
    assert chunks[-1]["input_tokens"] == 11
    assert chunks[-1]["output_tokens"] == 2


async def _collect(stream) -> list[dict[str, object]]:
    return [chunk async for chunk in stream]
