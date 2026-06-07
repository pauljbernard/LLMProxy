"""Base provider adapter."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence
from time import perf_counter

import httpx

from app.services.cost import estimate_cost_usd
from app.schemas.chat import ChatCompletionRequest
from app.schemas.provider import ProviderCapability


class ProviderConfigurationError(RuntimeError):
    """Raised when a provider adapter is missing required runtime configuration."""


class BaseProvider(ABC):
    provider_family: str
    provider_name: str
    model_id: str
    supports_streaming: bool = False
    supports_embeddings: bool = False
    supports_tools: bool = False

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
            supports_streaming=self.supports_streaming,
            supports_embeddings=self.supports_embeddings,
            supports_tools=self.supports_tools,
            max_context_tokens=128_000,
            max_output_tokens=8_192,
        )

    @staticmethod
    def _join_messages(messages: Sequence[object]) -> str:
        parts: list[str] = []
        for message in messages:
            content = getattr(message, "content", "")
            if isinstance(content, str):
                parts.append(content)
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and isinstance(item.get("text"), str):
                        parts.append(item["text"])
        return " ".join(parts).strip()

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
            "cost_estimate": estimate_cost_usd(
                provider_name=self.provider_name,
                model_id=self.model_id,
                input_tokens=prompt_tokens,
                output_tokens=completion_tokens,
            ),
            "raw_response": {
                "provider": self.provider_name,
                "provider_family": self.provider_family,
                "model": self.model_id,
                "content": content,
                "stubbed": True,
            },
        }

    def _client(
        self,
        *,
        base_url: str,
        headers: dict[str, str] | None = None,
        timeout_seconds: float | None = None,
    ) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers=headers,
            timeout=timeout_seconds if timeout_seconds is not None else self.timeout_seconds,
            transport=self._transport,
        )

    def _timeout_for_request(self, request: ChatCompletionRequest) -> float:
        if request.timeout_seconds is None:
            return self.timeout_seconds
        return float(request.timeout_seconds)

    def _require_config(self, value: str | None, *, field_name: str) -> str:
        if value:
            return value
        raise ProviderConfigurationError(
            f"{self.provider_name} provider is missing required configuration: {field_name}"
        )

    @abstractmethod
    async def chat(self, request: ChatCompletionRequest) -> dict[str, object]:
        raise NotImplementedError

    async def stream_chat(self, request: ChatCompletionRequest) -> AsyncIterator[dict[str, object]]:
        raise NotImplementedError(f"{self.provider_name} does not support streaming chat.")

    async def embed(
        self,
        texts: Sequence[str],
        *,
        model: str | None = None,
        dimensions: int | None = None,
    ) -> list[list[float]]:
        raise NotImplementedError(f"{self.provider_name} does not support embeddings.")

    async def healthcheck(self) -> dict[str, object]:
        return {
            "ok": None,
            "provider": self.provider_name,
            "model": self.model_id,
            "detail": "health check not implemented",
        }

    async def invoke(self, request: ChatCompletionRequest) -> dict[str, object]:
        started_at = perf_counter()
        response = await self.chat(request)
        response["latency_ms"] = int((perf_counter() - started_at) * 1000)
        response["provider"] = self.provider_name
        response["provider_family"] = self.provider_family
        return response
