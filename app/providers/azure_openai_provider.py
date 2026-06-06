"""Azure OpenAI provider implementation."""

from collections.abc import AsyncIterator, Sequence
import json

from app.config import Settings
from app.providers.base import BaseProvider
from app.schemas.chat import ChatCompletionRequest


class AzureOpenAIProvider(BaseProvider):
    provider_family = "Azure OpenAI"
    provider_name = "azure_openai"
    price_per_token = 0.000021
    supports_streaming = True

    def __init__(
        self,
        model_id: str,
        *,
        api_key: str | None = None,
        endpoint: str | None = None,
        api_version: str = "2024-10-21",
        timeout_seconds: float = 60.0,
        transport=None,
    ) -> None:
        super().__init__(model_id, timeout_seconds=timeout_seconds, transport=transport)
        self.api_key = api_key
        self.endpoint = endpoint
        self.api_version = api_version

    @classmethod
    def from_settings(cls, settings: Settings, *, transport=None) -> "AzureOpenAIProvider":
        return cls(
            settings.llmproxy_azure_openai_model,
            api_key=settings.llmproxy_azure_openai_api_key,
            endpoint=settings.llmproxy_azure_openai_endpoint,
            api_version=settings.llmproxy_azure_openai_api_version,
            timeout_seconds=settings.llmproxy_provider_timeout_seconds,
            transport=transport,
        )

    @staticmethod
    def _request_messages(messages: Sequence[object]) -> list[dict[str, str]]:
        payload: list[dict[str, str]] = []
        for message in messages:
            payload.append(
                {
                    "role": str(getattr(message, "role", "user")),
                    "content": str(getattr(message, "content", "")),
                }
            )
        return payload

    async def chat(self, request: ChatCompletionRequest) -> dict[str, object]:
        api_key = self._require_config(self.api_key, field_name="llmproxy_azure_openai_api_key")
        endpoint = self._require_config(self.endpoint, field_name="llmproxy_azure_openai_endpoint")
        payload = {
            "messages": self._request_messages(request.messages),
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": False,
        }
        headers = {
            "api-key": api_key,
            "Content-Type": "application/json",
        }
        async with self._client(base_url=endpoint, headers=headers) as client:
            response = await client.post(
                f"/openai/deployments/{self.model_id}/chat/completions",
                params={"api-version": self.api_version},
                json=payload,
            )
            response.raise_for_status()
            raw_response = response.json()

        choice = raw_response.get("choices", [{}])[0]
        message = choice.get("message", {})
        usage = raw_response.get("usage", {})
        prompt_tokens = int(usage.get("prompt_tokens", 0))
        completion_tokens = int(usage.get("completion_tokens", 0))
        cost_estimate = round((prompt_tokens + completion_tokens) * self.price_per_token, 6)
        return {
            "model": str(raw_response.get("model", self.model_id)),
            "content": str(message.get("content", "")),
            "input_tokens": prompt_tokens,
            "output_tokens": completion_tokens,
            "finish_reason": str(choice.get("finish_reason", "stop")),
            "cost_estimate": cost_estimate,
            "raw_response": raw_response,
        }

    async def stream_chat(self, request: ChatCompletionRequest) -> AsyncIterator[dict[str, object]]:
        api_key = self._require_config(self.api_key, field_name="llmproxy_azure_openai_api_key")
        endpoint = self._require_config(self.endpoint, field_name="llmproxy_azure_openai_endpoint")
        payload = {
            "messages": self._request_messages(request.messages),
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        headers = {
            "api-key": api_key,
            "Content-Type": "application/json",
        }
        async with self._client(base_url=endpoint, headers=headers) as client:
            async with client.stream(
                "POST",
                f"/openai/deployments/{self.model_id}/chat/completions",
                params={"api-version": self.api_version},
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    payload_text = line[6:].strip()
                    if payload_text == "[DONE]":
                        break
                    raw_chunk = json.loads(payload_text)
                    choice = (raw_chunk.get("choices") or [{}])[0]
                    delta = choice.get("delta") or {}
                    usage = raw_chunk.get("usage") or {}
                    yield {
                        "model": str(raw_chunk.get("model", self.model_id)),
                        "delta": str(delta.get("content", "")),
                        "finish_reason": choice.get("finish_reason"),
                        "input_tokens": int(usage.get("prompt_tokens", 0)),
                        "output_tokens": int(usage.get("completion_tokens", 0)),
                        "raw_chunk": raw_chunk,
                    }
