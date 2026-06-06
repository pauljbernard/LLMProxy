import asyncio
import json

import httpx
import pytest

from app.providers.base import ProviderConfigurationError
from app.providers.google_provider import GoogleProvider
from app.schemas.chat import ChatCompletionRequest


def _request() -> ChatCompletionRequest:
    return ChatCompletionRequest.model_validate(
        {
            "model": "proxy-auto",
            "messages": [{"role": "user", "content": "Research vector database tradeoffs."}],
            "metadata": {"session_id": "sess_google"},
        }
    )


def test_google_provider_normalizes_generate_content_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1beta/models/gemini-2.5-pro:generateContent"
        assert request.url.params["key"] == "test-google-key"
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["contents"][0]["role"] == "user"
        assert payload["contents"][0]["parts"][0]["text"] == "Research vector database tradeoffs."
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {"parts": [{"text": "Google research answer."}]},
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 12,
                    "candidatesTokenCount": 3,
                    "totalTokenCount": 15,
                },
                "modelVersion": "gemini-2.5-pro",
                "responseId": "resp_123",
            },
        )

    provider = GoogleProvider(
        "gemini-2.5-pro",
        api_key="test-google-key",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        transport=httpx.MockTransport(handler),
    )

    result = asyncio.run(provider.invoke(_request()))

    assert result["model"] == "gemini-2.5-pro"
    assert result["content"] == "Google research answer."
    assert result["input_tokens"] == 12
    assert result["output_tokens"] == 3
    assert result["finish_reason"] == "stop"
    assert result["provider"] == "google"
    assert result["provider_family"] == "Google Gemini"
    assert result["raw_response"]["responseId"] == "resp_123"


def test_google_provider_requires_api_key() -> None:
    provider = GoogleProvider("gemini-2.5-pro")

    with pytest.raises(ProviderConfigurationError):
        asyncio.run(provider.chat(_request()))


def test_google_provider_streams_generate_content_chunks() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1beta/models/gemini-2.5-pro:streamGenerateContent"
        assert request.url.params["alt"] == "sse"
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["generationConfig"]["maxOutputTokens"] == 1024
        return httpx.Response(
            200,
            text=(
                'data: {"candidates":[{"content":{"parts":[{"text":"Google "}]},"finishReason":null}],"modelVersion":"gemini-2.5-pro"}\n\n'
                'data: {"candidates":[{"content":{"parts":[{"text":"stream."}]},"finishReason":"STOP"}],"usageMetadata":{"promptTokenCount":12,"candidatesTokenCount":2},"modelVersion":"gemini-2.5-pro"}\n\n'
            ),
        )

    provider = GoogleProvider(
        "gemini-2.5-pro",
        api_key="test-google-key",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        transport=httpx.MockTransport(handler),
    )

    chunks = asyncio.run(_collect(provider.stream_chat(_request())))

    assert [chunk["delta"] for chunk in chunks] == ["Google ", "stream."]
    assert chunks[-1]["finish_reason"] == "stop"
    assert chunks[-1]["input_tokens"] == 12
    assert chunks[-1]["output_tokens"] == 2


async def _collect(stream) -> list[dict[str, object]]:
    return [chunk async for chunk in stream]
