"""Google Gemini provider implementation."""

from collections.abc import AsyncIterator, Sequence
import json

from app.config import Settings
from app.providers.base import BaseProvider
from app.schemas.chat import ChatCompletionRequest


class GoogleProvider(BaseProvider):
    provider_family = "Google Gemini"
    provider_name = "google"
    price_per_token = 0.000018
    supports_streaming = True

    def __init__(
        self,
        model_id: str,
        *,
        api_key: str | None = None,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        timeout_seconds: float = 60.0,
        transport=None,
    ) -> None:
        super().__init__(model_id, timeout_seconds=timeout_seconds, transport=transport)
        self.api_key = api_key
        self.base_url = base_url

    @classmethod
    def from_settings(cls, settings: Settings, *, transport=None) -> "GoogleProvider":
        return cls(
            settings.llmproxy_google_model,
            api_key=settings.llmproxy_google_api_key,
            base_url=settings.llmproxy_google_base_url,
            timeout_seconds=settings.llmproxy_provider_timeout_seconds,
            transport=transport,
        )

    @staticmethod
    def _request_contents(messages: Sequence[object]) -> list[dict[str, object]]:
        payload: list[dict[str, object]] = []
        for message in messages:
            role = str(getattr(message, "role", "user"))
            mapped_role = "model" if role == "assistant" else "user"
            payload.append(
                {
                    "role": mapped_role,
                    "parts": [{"text": str(getattr(message, "content", ""))}],
                }
            )
        return payload

    @staticmethod
    def _extract_content(candidate: object) -> str:
        if not isinstance(candidate, dict):
            return ""
        content = candidate.get("content", {})
        if not isinstance(content, dict):
            return ""
        parts = content.get("parts", [])
        if not isinstance(parts, list):
            return ""
        result: list[str] = []
        for item in parts:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                result.append(item["text"])
        return "".join(result)

    async def chat(self, request: ChatCompletionRequest) -> dict[str, object]:
        api_key = self._require_config(self.api_key, field_name="llmproxy_google_api_key")
        payload = {
            "contents": self._request_contents(request.messages),
            "generationConfig": {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_tokens,
            },
        }
        async with self._client(base_url=self.base_url) as client:
            response = await client.post(
                f"/models/{self.model_id}:generateContent",
                params={"key": api_key},
                json=payload,
            )
            response.raise_for_status()
            raw_response = response.json()

        candidate = raw_response.get("candidates", [{}])[0]
        usage = raw_response.get("usageMetadata", {})
        prompt_tokens = int(usage.get("promptTokenCount", 0))
        completion_tokens = int(usage.get("candidatesTokenCount", 0))
        cost_estimate = round((prompt_tokens + completion_tokens) * self.price_per_token, 6)
        return {
            "model": str(raw_response.get("modelVersion", self.model_id)),
            "content": self._extract_content(candidate),
            "input_tokens": prompt_tokens,
            "output_tokens": completion_tokens,
            "finish_reason": str(candidate.get("finishReason", "STOP")).lower(),
            "cost_estimate": cost_estimate,
            "raw_response": raw_response,
        }

    async def stream_chat(self, request: ChatCompletionRequest) -> AsyncIterator[dict[str, object]]:
        api_key = self._require_config(self.api_key, field_name="llmproxy_google_api_key")
        payload = {
            "contents": self._request_contents(request.messages),
            "generationConfig": {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_tokens,
            },
        }
        async with self._client(base_url=self.base_url) as client:
            async with client.stream(
                "POST",
                f"/models/{self.model_id}:streamGenerateContent",
                params={"key": api_key, "alt": "sse"},
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    raw_chunk = json.loads(line[6:].strip())
                    candidate = (raw_chunk.get("candidates") or [{}])[0]
                    usage = raw_chunk.get("usageMetadata") or {}
                    yield {
                        "model": str(raw_chunk.get("modelVersion", self.model_id)),
                        "delta": self._extract_content(candidate),
                        "finish_reason": str(candidate.get("finishReason")).lower() if candidate.get("finishReason") else None,
                        "input_tokens": int(usage.get("promptTokenCount", 0)),
                        "output_tokens": int(usage.get("candidatesTokenCount", 0)),
                        "raw_chunk": raw_chunk,
                    }
