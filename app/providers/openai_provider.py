"""OpenAI provider implementation."""

from collections.abc import Sequence

from app.config import Settings
from app.providers.base import BaseProvider
from app.schemas.chat import ChatCompletionRequest


class OpenAIProvider(BaseProvider):
    provider_family = "OpenAI"
    provider_name = "openai"
    price_per_token = 0.00002
    supports_embeddings = True

    def __init__(
        self,
        model_id: str,
        *,
        api_key: str | None = None,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 60.0,
        transport=None,
    ) -> None:
        super().__init__(model_id, timeout_seconds=timeout_seconds, transport=transport)
        self.api_key = api_key
        self.base_url = base_url

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

    async def chat(self, request: ChatCompletionRequest) -> dict[str, object]:
        api_key = self._require_config(self.api_key, field_name="llmproxy_openai_api_key")
        payload = {
            "model": self.model_id,
            "messages": self._request_messages(request.messages),
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        async with self._client(base_url=self.base_url, headers=headers) as client:
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
            "input_tokens": prompt_tokens,
            "output_tokens": completion_tokens,
            "finish_reason": str(choice.get("finish_reason", "stop")),
            "cost_estimate": cost_estimate,
            "raw_response": raw_response,
        }

    async def embed(
        self,
        texts: Sequence[str],
        *,
        model: str | None = None,
        dimensions: int | None = None,
    ) -> list[list[float]]:
        api_key = self._require_config(self.api_key, field_name="llmproxy_openai_api_key")
        payload: dict[str, object] = {
            "model": model or self.model_id,
            "input": list(texts),
        }
        if dimensions is not None:
            payload["dimensions"] = dimensions
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        async with self._client(base_url=self.base_url, headers=headers) as client:
            response = await client.post("/embeddings", json=payload)
            response.raise_for_status()
            raw_response = response.json()
        return [
            [float(value) for value in item.get("embedding", [])]
            for item in raw_response.get("data", [])
        ]
