import asyncio
import io
import json

import pytest

from app.providers.base import ProviderConfigurationError
from app.providers.bedrock_provider import BedrockProvider
from app.schemas.chat import ChatCompletionRequest


class FakeBedrockClient:
    def invoke_model(self, **kwargs):
        assert kwargs["modelId"] == "anthropic.claude-3-5-sonnet"
        payload = json.loads(kwargs["body"].decode("utf-8"))
        assert payload["messages"][0]["content"] == "Design a service boundary."
        return {
            "body": io.BytesIO(
                json.dumps(
                    {
                        "model": "anthropic.claude-3-5-sonnet",
                        "content": [{"type": "text", "text": "Bedrock answer."}],
                        "stop_reason": "end_turn",
                        "usage": {"input_tokens": 16, "output_tokens": 5},
                    }
                ).encode("utf-8")
            )
        }


def _request() -> ChatCompletionRequest:
    return ChatCompletionRequest.model_validate(
        {
            "model": "proxy-teacher",
            "messages": [{"role": "user", "content": "Design a service boundary."}],
            "metadata": {"session_id": "sess_bedrock"},
        }
    )


def test_bedrock_provider_normalizes_invoke_model_response() -> None:
    provider = BedrockProvider(
        "anthropic.claude-3-5-sonnet",
        region="us-east-1",
        access_key_id="test-access-key",
        secret_access_key="test-secret-key",
        client=FakeBedrockClient(),
    )

    result = asyncio.run(provider.invoke(_request()))

    assert result["model"] == "anthropic.claude-3-5-sonnet"
    assert result["content"] == "Bedrock answer."
    assert result["provider"] == "bedrock"
    assert result["provider_family"] == "AWS Bedrock"
    assert result["input_tokens"] == 16
    assert result["output_tokens"] == 5


def test_bedrock_provider_requires_runtime_credentials() -> None:
    provider = BedrockProvider("anthropic.claude-3-5-sonnet")

    with pytest.raises(ProviderConfigurationError):
        asyncio.run(provider.chat(_request()))
