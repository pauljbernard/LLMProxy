"""Google Gemini provider implementation."""

from collections.abc import AsyncIterator, Sequence
import json
from time import time

from app.config import Settings
from app.providers.base import BaseProvider
from app.services.cost import estimate_cost_usd
from app.schemas.chat import ChatCompletionRequest


class GoogleProvider(BaseProvider):
    provider_family = "Google Gemini"
    provider_name = "google"
    price_per_token = 0.000018
    supports_streaming = True

    @staticmethod
    def _request_parts(content: object) -> list[dict[str, object]]:
        if isinstance(content, str):
            return [{"text": content}]
        if isinstance(content, list):
            parts: list[dict[str, object]] = []
            for item in content:
                if isinstance(item, dict):
                    parts.append(item)
            return parts
        return [{"text": ""}]

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
                    "parts": GoogleProvider._request_parts(getattr(message, "content", "")),
                }
            )
        return payload

    @staticmethod
    def _generation_config(request: ChatCompletionRequest) -> dict[str, object]:
        config: dict[str, object] = {
            "temperature": request.temperature,
            "maxOutputTokens": request.max_tokens,
        }
        if request.top_p is not None:
            config["topP"] = request.top_p
        if request.n is not None:
            config["candidateCount"] = request.n
        if request.seed is not None:
            config["seed"] = request.seed
        if request.stop is not None:
            config["stopSequences"] = [request.stop] if isinstance(request.stop, str) else request.stop
        if request.response_format is not None and request.response_format.type == "json_object":
            config["responseMimeType"] = "application/json"
        return config

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
            "generationConfig": self._generation_config(request),
        }
        async with self._client(base_url=self.base_url, timeout_seconds=self._timeout_for_request(request)) as client:
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
        model_name = str(raw_response.get("modelVersion", self.model_id))
        cost_estimate = estimate_cost_usd(
            provider_name=self.provider_name,
            model_id=model_name,
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
        )
        return {
            "model": model_name,
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
            "generationConfig": self._generation_config(request),
        }
        async with self._client(base_url=self.base_url, timeout_seconds=self._timeout_for_request(request)) as client:
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

    async def healthcheck(self) -> dict[str, object]:
        api_key = self._require_config(self.api_key, field_name="llmproxy_google_api_key")
        payload = {
            "contents": [{"role": "user", "parts": [{"text": "ping"}]}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": 1},
        }
        started_at = time()
        try:
            async with self._client(base_url=self.base_url, timeout_seconds=3.0) as client:
                response = await client.post(
                    f"/models/{self.model_id}:generateContent",
                    params={"key": api_key},
                    json=payload,
                )
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
