"""Anthropic provider implementation."""

from collections.abc import AsyncIterator, Sequence
import json
from time import time

from app.config import Settings
from app.providers.base import BaseProvider
from app.services.cost import estimate_cost_usd
from app.schemas.chat import ChatCompletionRequest


class AnthropicProvider(BaseProvider):
    provider_family = "Anthropic"
    provider_name = "anthropic"
    price_per_token = 0.000024
    anthropic_version = "2023-06-01"
    supports_streaming = True

    def __init__(
        self,
        model_id: str,
        *,
        api_key: str | None = None,
        base_url: str = "https://api.anthropic.com/v1",
        timeout_seconds: float = 60.0,
        transport=None,
    ) -> None:
        super().__init__(model_id, timeout_seconds=timeout_seconds, transport=transport)
        self.api_key = api_key
        self.base_url = base_url

    @classmethod
    def from_settings(cls, settings: Settings, *, transport=None) -> "AnthropicProvider":
        return cls(
            settings.llmproxy_anthropic_model,
            api_key=settings.llmproxy_anthropic_api_key,
            base_url=settings.llmproxy_anthropic_base_url,
            timeout_seconds=settings.llmproxy_provider_timeout_seconds,
            transport=transport,
        )

    @staticmethod
    def _request_messages(messages: Sequence[object]) -> list[dict[str, object]]:
        payload: list[dict[str, object]] = []
        for message in messages:
            role = str(getattr(message, "role", "user"))
            if role == "system":
                role = "user"
            payload.append(
                {
                    "role": role,
                    "content": getattr(message, "content", ""),
                }
            )
        return payload

    @staticmethod
    def _request_payload(request: ChatCompletionRequest, *, model_id: str, stream: bool) -> dict[str, object]:
        payload: dict[str, object] = {
            "model": model_id,
            "messages": AnthropicProvider._request_messages(request.messages),
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.top_p is not None:
            payload["top_p"] = request.top_p
        if request.stop is not None:
            payload["stop_sequences"] = [request.stop] if isinstance(request.stop, str) else request.stop
        if request.user:
            payload["metadata"] = {"user_id": request.user}
        if stream:
            payload["stream"] = True
        return payload

    @staticmethod
    def _extract_content(content_blocks: object) -> str:
        if not isinstance(content_blocks, list):
            return ""
        parts: list[str] = []
        for block in content_blocks:
            if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "".join(parts)

    async def chat(self, request: ChatCompletionRequest) -> dict[str, object]:
        api_key = self._require_config(self.api_key, field_name="llmproxy_anthropic_api_key")
        payload = self._request_payload(request, model_id=self.model_id, stream=False)
        headers = {
            "x-api-key": api_key,
            "anthropic-version": self.anthropic_version,
            "content-type": "application/json",
        }
        async with self._client(
            base_url=self.base_url,
            headers=headers,
            timeout_seconds=self._timeout_for_request(request),
        ) as client:
            response = await client.post("/messages", json=payload)
            response.raise_for_status()
            raw_response = response.json()

        usage = raw_response.get("usage", {})
        prompt_tokens = int(usage.get("input_tokens", 0))
        completion_tokens = int(usage.get("output_tokens", 0))
        model_name = str(raw_response.get("model", self.model_id))
        cost_estimate = estimate_cost_usd(
            provider_name=self.provider_name,
            model_id=model_name,
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
        )
        return {
            "model": model_name,
            "content": self._extract_content(raw_response.get("content")),
            "input_tokens": prompt_tokens,
            "output_tokens": completion_tokens,
            "finish_reason": str(raw_response.get("stop_reason", "stop")),
            "cost_estimate": cost_estimate,
            "raw_response": raw_response,
        }

    async def stream_chat(self, request: ChatCompletionRequest) -> AsyncIterator[dict[str, object]]:
        api_key = self._require_config(self.api_key, field_name="llmproxy_anthropic_api_key")
        payload = self._request_payload(request, model_id=self.model_id, stream=True)
        headers = {
            "x-api-key": api_key,
            "anthropic-version": self.anthropic_version,
            "content-type": "application/json",
        }
        async with self._client(
            base_url=self.base_url,
            headers=headers,
            timeout_seconds=self._timeout_for_request(request),
        ) as client:
            async with client.stream("POST", "/messages", json=payload) as response:
                response.raise_for_status()
                event_name: str | None = None
                async for line in response.aiter_lines():
                    if not line:
                        event_name = None
                        continue
                    if line.startswith("event: "):
                        event_name = line[7:].strip()
                        continue
                    if not line.startswith("data: "):
                        continue
                    raw_chunk = json.loads(line[6:].strip())
                    chunk_type = event_name or raw_chunk.get("type")
                    delta = ""
                    finish_reason = None
                    usage = raw_chunk.get("usage") or {}
                    if chunk_type == "content_block_delta":
                        delta_obj = raw_chunk.get("delta") or {}
                        if delta_obj.get("type") == "text_delta":
                            delta = str(delta_obj.get("text", ""))
                    elif chunk_type == "message_delta":
                        delta_obj = raw_chunk.get("delta") or {}
                        finish_reason = delta_obj.get("stop_reason")
                    elif chunk_type == "message_stop":
                        finish_reason = "stop"
                    yield {
                        "model": str(raw_chunk.get("model", self.model_id)),
                        "delta": delta,
                        "finish_reason": finish_reason,
                        "input_tokens": int(usage.get("input_tokens", 0)),
                        "output_tokens": int(usage.get("output_tokens", 0)),
                        "raw_chunk": raw_chunk,
                    }

    async def healthcheck(self) -> dict[str, object]:
        api_key = self._require_config(self.api_key, field_name="llmproxy_anthropic_api_key")
        headers = {
            "x-api-key": api_key,
            "anthropic-version": self.anthropic_version,
            "content-type": "application/json",
        }
        payload = {
            "model": self.model_id,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 1,
            "temperature": 0,
        }
        started_at = time()
        try:
            async with self._client(base_url=self.base_url, headers=headers, timeout_seconds=3.0) as client:
                response = await client.post("/messages", json=payload)
            return {
                "ok": response.status_code < 500,
                "provider": self.provider_name,
                "model": self.model_id,
                "status_code": response.status_code,
                "latency_ms": int((time() - started_at) * 1000),
            }
        except Exception as exc:
            return {
                "ok": False,
                "provider": self.provider_name,
                "model": self.model_id,
                "error": str(exc),
                "latency_ms": int((time() - started_at) * 1000),
            }
