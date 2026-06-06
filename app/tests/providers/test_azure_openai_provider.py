import asyncio
import json

import httpx
import pytest

from app.providers.azure_openai_provider import AzureOpenAIProvider
from app.providers.base import ProviderConfigurationError
from app.schemas.chat import ChatCompletionRequest


def _request() -> ChatCompletionRequest:
    return ChatCompletionRequest.model_validate(
        {
            "model": "proxy-auto",
            "messages": [{"role": "user", "content": "Review this prompt strategy."}],
            "metadata": {"session_id": "sess_azure"},
        }
    )


def test_azure_openai_provider_normalizes_chat_completion_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/openai/deployments/gpt-5.5/chat/completions"
        assert request.url.params["api-version"] == "2024-10-21"
        assert request.headers["api-key"] == "test-azure-key"
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["messages"][0]["content"] == "Review this prompt strategy."
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl_azure",
                "model": "gpt-5.5",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "Azure answer."},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 8, "completion_tokens": 3, "total_tokens": 11},
            },
        )

    provider = AzureOpenAIProvider(
        "gpt-5.5",
        api_key="test-azure-key",
        endpoint="https://example-resource.openai.azure.com",
        api_version="2024-10-21",
        transport=httpx.MockTransport(handler),
    )

    result = asyncio.run(provider.invoke(_request()))

    assert result["model"] == "gpt-5.5"
    assert result["content"] == "Azure answer."
    assert result["provider"] == "azure_openai"
    assert result["provider_family"] == "Azure OpenAI"
    assert result["input_tokens"] == 8
    assert result["output_tokens"] == 3


def test_azure_openai_provider_requires_endpoint_and_api_key() -> None:
    provider = AzureOpenAIProvider("gpt-5.5")

    with pytest.raises(ProviderConfigurationError):
        asyncio.run(provider.chat(_request()))


def test_azure_openai_provider_streams_chat_chunks() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["stream"] is True
        return httpx.Response(
            200,
            text=(
                'data: {"id":"chatcmpl_azure","model":"gpt-5.5","choices":[{"delta":{"content":"Azure "},"finish_reason":null}]}\n\n'
                'data: {"id":"chatcmpl_azure","model":"gpt-5.5","choices":[{"delta":{"content":"stream."},"finish_reason":"stop"}],"usage":{"prompt_tokens":8,"completion_tokens":2}}\n\n'
                "data: [DONE]\n\n"
            ),
        )

    provider = AzureOpenAIProvider(
        "gpt-5.5",
        api_key="test-azure-key",
        endpoint="https://example-resource.openai.azure.com",
        api_version="2024-10-21",
        transport=httpx.MockTransport(handler),
    )

    chunks = asyncio.run(_collect(provider.stream_chat(_request())))

    assert [chunk["delta"] for chunk in chunks] == ["Azure ", "stream."]
    assert chunks[-1]["finish_reason"] == "stop"
    assert chunks[-1]["input_tokens"] == 8
    assert chunks[-1]["output_tokens"] == 2


async def _collect(stream) -> list[dict[str, object]]:
    return [chunk async for chunk in stream]
