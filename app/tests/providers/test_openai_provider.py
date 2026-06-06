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
