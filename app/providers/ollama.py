"""Ollama provider implementation."""

from collections.abc import AsyncIterator, Sequence
import json

from app.config import Settings
from app.providers.base import BaseProvider
from app.schemas.chat import ChatCompletionRequest


class OllamaProvider(BaseProvider):
    provider_family = "local runtime"
    provider_name = "ollama"
    supports_streaming = True
    supports_embeddings = True

    def __init__(
        self,
        model_id: str,
        *,
        base_url: str = "http://localhost:11434",
        timeout_seconds: float = 60.0,
        transport=None,
    ) -> None:
        super().__init__(model_id, timeout_seconds=timeout_seconds, transport=transport)
        self.base_url = base_url

    @classmethod
    def from_settings(cls, settings: Settings, *, model_id: str | None = None, transport=None) -> "OllamaProvider":
        return cls(
            model_id or settings.llmproxy_ollama_model,
            base_url=settings.llmproxy_ollama_base_url,
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
        payload = {
            "model": self.model_id,
            "messages": self._request_messages(request.messages),
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
        }
        async with self._client(base_url=self.base_url) as client:
            response = await client.post("/api/chat", json=payload)
            response.raise_for_status()
            raw_response = response.json()

        message = raw_response.get("message", {})
        prompt_tokens = int(raw_response.get("prompt_eval_count", 0))
        completion_tokens = int(raw_response.get("eval_count", 0))
        return {
            "model": str(raw_response.get("model", self.model_id)),
            "content": str(message.get("content", "")),
            "input_tokens": prompt_tokens,
            "output_tokens": completion_tokens,
            "finish_reason": str(raw_response.get("done_reason", "stop")),
            "cost_estimate": 0.0,
            "raw_response": raw_response,
        }

    async def stream_chat(self, request: ChatCompletionRequest) -> AsyncIterator[dict[str, object]]:
        payload = {
            "model": self.model_id,
            "messages": self._request_messages(request.messages),
            "stream": True,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
        }
        async with self._client(base_url=self.base_url) as client:
            async with client.stream("POST", "/api/chat", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    raw_chunk = json.loads(line)
                    message = raw_chunk.get("message") or {}
                    yield {
                        "model": str(raw_chunk.get("model", self.model_id)),
                        "delta": str(message.get("content", "")),
                        "finish_reason": raw_chunk.get("done_reason") if raw_chunk.get("done") else None,
                        "input_tokens": int(raw_chunk.get("prompt_eval_count", 0)),
                        "output_tokens": int(raw_chunk.get("eval_count", 0)),
                        "raw_chunk": raw_chunk,
                    }

    async def embed(
        self,
        texts: Sequence[str],
        *,
        model: str | None = None,
        dimensions: int | None = None,
    ) -> list[list[float]]:
        del dimensions
        resolved_model = model or self.model_id
        async with self._client(base_url=self.base_url) as client:
            response = await client.post(
                "/api/embed",
                json={"model": resolved_model, "input": list(texts)},
            )
            response.raise_for_status()
            raw_response = response.json()
        values = raw_response.get("embeddings") or raw_response.get("embedding") or []
        if values and isinstance(values[0], list):
            return [[float(value) for value in vector] for vector in values]
        if values:
            return [[float(value) for value in values]]
        return [[] for _ in texts]
