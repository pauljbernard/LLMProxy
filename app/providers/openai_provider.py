"""OpenAI provider implementation."""

from collections.abc import AsyncIterator, Sequence
import json

from app.config import Settings
from app.providers.base import BaseProvider
from app.schemas.chat import ChatCompletionRequest


class OpenAIProvider(BaseProvider):
    provider_family = "OpenAI"
    provider_name = "openai"
    price_per_token = 0.00002
    supports_streaming = True
    supports_embeddings = True
    supports_tools = True

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
            payload.append(
                {
                    "role": str(getattr(message, "role", "user")),
                    "content": content,
                }
            )
        return payload

    @staticmethod
    def _request_payload(request: ChatCompletionRequest, *, model_id: str, stream: bool) -> dict[str, object]:
        payload: dict[str, object] = {
            "model": model_id,
            "messages": OpenAIProvider._request_messages(request.messages),
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": stream,
        }
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
            self._require_config(self.api_key, field_name="llmproxy_openai_api_key")
        return headers

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
        cost_estimate = round((prompt_tokens + completion_tokens) * self.price_per_token, 6)
        return {
            "model": str(raw_response.get("model", self.model_id)),
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
