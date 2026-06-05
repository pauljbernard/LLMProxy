"""Base provider adapter."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from time import perf_counter

import httpx

from app.schemas.chat import ChatCompletionRequest
from app.schemas.provider import ProviderCapability


class ProviderConfigurationError(RuntimeError):
    """Raised when a provider adapter is missing required runtime configuration."""


class BaseProvider(ABC):
    provider_family: str
    provider_name: str
    model_id: str

    def __init__(
        self,
        model_id: str,
        *,
        timeout_seconds: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.model_id = model_id
        self.timeout_seconds = timeout_seconds
        self._transport = transport

    @property
    def capability(self) -> ProviderCapability:
        return ProviderCapability(
            provider_family=self.provider_family,
            provider_name=self.provider_name,
            model_id=self.model_id,
            supports_streaming=True,
            supports_embeddings=False,
            supports_tools=False,
            max_context_tokens=128_000,
            max_output_tokens=8_192,
        )

    @staticmethod
    def _join_messages(messages: Sequence[object]) -> str:
        return " ".join(getattr(message, "content", "") for message in messages).strip()

    @staticmethod
    def _usage(content: str, completion: str) -> tuple[int, int]:
        return len(content.split()), len(completion.split())

    def _stub_chat_response(self, request: ChatCompletionRequest, *, price_per_token: float = 0.0) -> dict[str, object]:
        prompt = self._join_messages(request.messages)
        content = f"[{self.provider_name}:{self.model_id}] {prompt or 'empty request'}"
        prompt_tokens, completion_tokens = self._usage(prompt, content)
        return {
            "model": self.model_id,
            "content": content,
            "input_tokens": prompt_tokens,
            "output_tokens": completion_tokens,
            "finish_reason": "stop",
            "cost_estimate": round((prompt_tokens + completion_tokens) * price_per_token, 6),
            "raw_response": {
                "provider": self.provider_name,
                "provider_family": self.provider_family,
                "model": self.model_id,
                "content": content,
                "stubbed": True,
            },
        }

    def _client(self, *, base_url: str, headers: dict[str, str] | None = None) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers=headers,
            timeout=self.timeout_seconds,
            transport=self._transport,
        )

    def _require_config(self, value: str | None, *, field_name: str) -> str:
        if value:
            return value
        raise ProviderConfigurationError(
            f"{self.provider_name} provider is missing required configuration: {field_name}"
        )

    @abstractmethod
    async def chat(self, request: ChatCompletionRequest) -> dict[str, object]:
        raise NotImplementedError

    async def invoke(self, request: ChatCompletionRequest) -> dict[str, object]:
        started_at = perf_counter()
        response = await self.chat(request)
        response["latency_ms"] = int((perf_counter() - started_at) * 1000)
        response["provider"] = self.provider_name
        response["provider_family"] = self.provider_family
        return response
