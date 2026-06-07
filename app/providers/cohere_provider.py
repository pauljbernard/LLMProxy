"""Cohere Compatibility API provider implementation."""

from app.config import Settings
from app.providers.openai_provider import OpenAIProvider
from app.schemas.chat import ChatCompletionRequest


class CohereProvider(OpenAIProvider):
    provider_family = "Cohere"
    provider_name = "cohere"
    price_per_token = 0.000015
    api_key_config_field = "llmproxy_cohere_api_key"

    @classmethod
    def from_settings(cls, settings: Settings, *, transport=None) -> "CohereProvider":
        return cls(
            settings.llmproxy_cohere_model,
            api_key=settings.llmproxy_cohere_api_key,
            base_url=settings.llmproxy_cohere_base_url,
            timeout_seconds=settings.llmproxy_provider_timeout_seconds,
            transport=transport,
        )

    @staticmethod
    def _request_payload(request: ChatCompletionRequest, *, model_id: str, stream: bool) -> dict[str, object]:
        payload = OpenAIProvider._request_payload(request, model_id=model_id, stream=stream)
        for field_name in ("logit_bias", "top_logprobs", "n", "parallel_tool_calls"):
            payload.pop(field_name, None)
        return payload
