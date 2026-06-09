"""OpenAI provider implementation."""

from collections.abc import AsyncIterator, Sequence
import json
from time import time

from app.config import Settings
from app.providers.base import BaseProvider
from app.services.cost import estimate_cost_usd
from app.schemas.chat import ChatCompletionRequest
from app.schemas.provider import ProviderCapability


class OpenAIProvider(BaseProvider):
    provider_family = "OpenAI"
    provider_name = "openai"
    price_per_token = 0.00002
    supports_streaming = True
    supports_embeddings = True
    supports_tools = True
    api_key_config_field = "llmproxy_openai_api_key"

    def __init__(
        self,
        model_id: str,
        *,
        api_key: str | None = None,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 60.0,
        transport=None,
        require_api_key: bool = True,
    ) -> None:
        super().__init__(model_id, timeout_seconds=timeout_seconds, transport=transport)
        self.api_key = api_key
        self.base_url = base_url
        self.require_api_key = require_api_key

    @classmethod
    def from_settings(cls, settings: Settings, *, transport=None) -> "OpenAIProvider":
        return cls(
            settings.llmproxy_openai_model,
            api_key=settings.llmproxy_openai_api_key,
            base_url=settings.llmproxy_openai_base_url,
            timeout_seconds=settings.llmproxy_provider_timeout_seconds,
            transport=transport,
        )

    @staticmethod
    def _request_messages(messages: Sequence[object]) -> list[dict[str, object]]:
        payload: list[dict[str, object]] = []
        for message in messages:
            content = getattr(message, "content", "")
            item: dict[str, object] = {
                "role": str(getattr(message, "role", "user")),
                "content": content,
            }
            tool_calls = getattr(message, "tool_calls", None)
            if isinstance(tool_calls, list) and tool_calls:
                item["tool_calls"] = tool_calls
            tool_call_id = getattr(message, "tool_call_id", None)
            if isinstance(tool_call_id, str) and tool_call_id:
                item["tool_call_id"] = tool_call_id
            name = getattr(message, "name", None)
            if isinstance(name, str) and name:
                item["name"] = name
            payload.append(item)
        return payload

    @staticmethod
    def _uses_max_completion_tokens(model_id: str) -> bool:
        lower_model_id = str(model_id or "").strip().lower()
        return lower_model_id.startswith("gpt-5")

    @staticmethod
    def _supports_temperature_override(model_id: str) -> bool:
        lower_model_id = str(model_id or "").strip().lower()
        return not lower_model_id.startswith("gpt-5")

    @staticmethod
    def _request_payload(request: ChatCompletionRequest, *, model_id: str, stream: bool) -> dict[str, object]:
        payload: dict[str, object] = {
            "model": model_id,
            "messages": OpenAIProvider._request_messages(request.messages),
            "stream": stream,
        }
        if OpenAIProvider._uses_max_completion_tokens(model_id):
            payload["max_completion_tokens"] = request.max_tokens
        else:
            payload["max_tokens"] = request.max_tokens
        if request.temperature is not None and (
            OpenAIProvider._supports_temperature_override(model_id) or float(request.temperature) == 1.0
        ):
            payload["temperature"] = request.temperature
        passthrough_fields = (
            "top_p",
            "n",
            "stop",
            "presence_penalty",
            "frequency_penalty",
            "seed",
            "logit_bias",
            "logprobs",
            "top_logprobs",
            "user",
            "tool_choice",
            "parallel_tool_calls",
            "functions",
        )
        for field_name in passthrough_fields:
            value = getattr(request, field_name)
            if value is not None:
                if field_name == "functions":
                    payload[field_name] = [item.model_dump(mode="json") for item in value]
                    continue
                payload[field_name] = value
        if request.response_format is not None:
            payload["response_format"] = request.response_format.model_dump(mode="json")
        if request.tools is not None:
            payload["tools"] = [tool.model_dump(mode="json") for tool in request.tools]
        if request.metadata.forwarded_by_proxy:
            payload["metadata"] = request.metadata.model_dump(mode="json")
        if stream:
            payload["stream_options"] = {"include_usage": True}
        return payload

    @staticmethod
    def _extract_tool_calls(choice_message: object) -> list[dict[str, object]] | None:
        if not isinstance(choice_message, dict):
            return None
        tool_calls = choice_message.get("tool_calls")
        if isinstance(tool_calls, list):
            return [item for item in tool_calls if isinstance(item, dict)] or None
        return None

    @staticmethod
    def _extract_content(choice_message: object) -> str:
        if isinstance(choice_message, dict):
            content = choice_message.get("content", "")
        else:
            content = ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    if isinstance(item.get("text"), str):
                        parts.append(item["text"])
                    elif item.get("type") == "output_text" and isinstance(item.get("text"), str):
                        parts.append(item["text"])
            return "".join(parts)
        return ""

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            return headers
        if self.require_api_key:
            self._require_config(self.api_key, field_name=self.api_key_config_field)
        return headers

    @classmethod
    def _capability_for_model(cls, model_id: str) -> ProviderCapability:
        lower_model_id = model_id.lower()
        is_embedding = lower_model_id.startswith("text-embedding-") or lower_model_id.endswith("-embedding")
        is_moderation = "moderation" in lower_model_id
        is_transcription = "transcribe" in lower_model_id or lower_model_id.startswith("whisper")
        is_tts = lower_model_id.startswith("tts-") or lower_model_id.endswith("-tts") or lower_model_id.endswith("-speech")
        is_image = "image" in lower_model_id or "dall-e" in lower_model_id
        is_realtime = "realtime" in lower_model_id
        supports_embeddings = is_embedding
        supports_streaming = not any((is_embedding, is_moderation, is_transcription, is_tts, is_image, is_realtime))
        supports_tools = supports_streaming
        return ProviderCapability(
            provider_family=cls.provider_family,
            provider_name=cls.provider_name,
            model_id=model_id,
            supports_streaming=supports_streaming,
            supports_embeddings=supports_embeddings,
            supports_tools=supports_tools,
            max_context_tokens=128_000,
            max_output_tokens=8_192,
        )

    async def list_models(self) -> list[ProviderCapability]:
        headers = self._headers()
        async with self._client(
            base_url=self.base_url,
            headers=headers,
            timeout_seconds=min(self.timeout_seconds, 10.0),
        ) as client:
            response = await client.get("/models")
            response.raise_for_status()
            raw_response = response.json()
        capabilities: list[ProviderCapability] = []
        for item in raw_response.get("data", []):
            if not isinstance(item, dict):
                continue
            model_id = str(item.get("id") or "").strip()
            if not model_id:
                continue
            capabilities.append(self._capability_for_model(model_id))
        return capabilities or [self.capability]

    async def chat(self, request: ChatCompletionRequest) -> dict[str, object]:
        payload = self._request_payload(request, model_id=self.model_id, stream=False)
        headers = self._headers()
        async with self._client(
            base_url=self.base_url,
            headers=headers,
            timeout_seconds=self._timeout_for_request(request),
        ) as client:
            response = await client.post("/chat/completions", json=payload)
            response.raise_for_status()
            raw_response = response.json()

        choice = raw_response.get("choices", [{}])[0]
        message = choice.get("message", {})
        content = self._extract_content(message)
        usage = raw_response.get("usage", {})
        prompt_tokens = int(usage.get("prompt_tokens", 0))
        completion_tokens = int(usage.get("completion_tokens", 0))
        model_name = str(raw_response.get("model", self.model_id))
        cost_estimate = estimate_cost_usd(
            provider_name=self.provider_name,
            model_id=model_name,
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
        )
        return {
            "model": model_name,
            "content": content,
            "tool_calls": self._extract_tool_calls(message),
            "input_tokens": prompt_tokens,
            "output_tokens": completion_tokens,
            "finish_reason": str(choice.get("finish_reason", "stop")),
            "cost_estimate": cost_estimate,
            "raw_response": raw_response,
        }

    async def stream_chat(self, request: ChatCompletionRequest) -> AsyncIterator[dict[str, object]]:
        payload = self._request_payload(request, model_id=self.model_id, stream=True)
        headers = self._headers()
        async with self._client(
            base_url=self.base_url,
            headers=headers,
            timeout_seconds=self._timeout_for_request(request),
        ) as client:
            async with client.stream("POST", "/chat/completions", json=payload) as response:
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
                        "delta": self._extract_content(delta),
                        "tool_calls": self._extract_tool_calls(delta),
                        "finish_reason": choice.get("finish_reason"),
                        "input_tokens": int(usage.get("prompt_tokens", 0)),
                        "output_tokens": int(usage.get("completion_tokens", 0)),
                        "raw_chunk": raw_chunk,
                    }

    async def embed(
        self,
        texts: Sequence[str],
        *,
        model: str | None = None,
        dimensions: int | None = None,
    ) -> list[list[float]]:
        payload: dict[str, object] = {
            "model": model or self.model_id,
            "input": list(texts),
        }
        if dimensions is not None:
            payload["dimensions"] = dimensions
        headers = self._headers()
        async with self._client(base_url=self.base_url, headers=headers) as client:
            response = await client.post("/embeddings", json=payload)
            response.raise_for_status()
            raw_response = response.json()
        return [
            [float(value) for value in item.get("embedding", [])]
            for item in raw_response.get("data", [])
        ]

    async def complete(self, payload: dict[str, object]) -> dict[str, object]:
        headers = self._headers()
        async with self._client(base_url=self.base_url, headers=headers) as client:
            response = await client.post("/completions", json=payload)
            response.raise_for_status()
            return response.json()

    async def generate_image(self, payload: dict[str, object]) -> dict[str, object]:
        headers = self._headers()
        async with self._client(base_url=self.base_url, headers=headers) as client:
            response = await client.post("/images/generations", json=payload)
            response.raise_for_status()
            return response.json()

    async def moderate(self, payload: dict[str, object]) -> dict[str, object]:
        headers = self._headers()
        async with self._client(base_url=self.base_url, headers=headers) as client:
            response = await client.post("/moderations", json=payload)
            response.raise_for_status()
            return response.json()

    async def transcribe(
        self,
        *,
        file_bytes: bytes,
        filename: str,
        model: str,
        language: str | None = None,
        prompt: str | None = None,
        response_format: str | None = None,
        temperature: float | None = None,
    ) -> dict[str, object]:
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        elif self.require_api_key:
            self._require_config(self.api_key, field_name=self.api_key_config_field)
        data: dict[str, object] = {"model": model}
        if language is not None:
            data["language"] = language
        if prompt is not None:
            data["prompt"] = prompt
        if response_format is not None:
            data["response_format"] = response_format
        if temperature is not None:
            data["temperature"] = str(temperature)
        files = {"file": (filename, file_bytes)}
        async with self._client(base_url=self.base_url, headers=headers) as client:
            response = await client.post("/audio/transcriptions", data=data, files=files)
            response.raise_for_status()
            return response.json()

    async def synthesize_speech(self, payload: dict[str, object]) -> tuple[bytes, str]:
        headers = self._headers()
        async with self._client(base_url=self.base_url, headers=headers) as client:
            response = await client.post("/audio/speech", json=payload)
            response.raise_for_status()
            return response.content, response.headers.get("content-type", "audio/mpeg")

    async def healthcheck(self) -> dict[str, object]:
        headers = self._headers()
        started_at = time()
        try:
            async with self._client(base_url=self.base_url, headers=headers, timeout_seconds=3.0) as client:
                response = await client.get("/models")
            ok = response.status_code < 500
            return {
                "ok": ok,
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
