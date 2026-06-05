"""xAI provider implementation."""

from app.config import Settings
from app.providers.openai_provider import OpenAIProvider


class XAIProvider(OpenAIProvider):
    provider_family = "xAI"
    provider_name = "xai"
    price_per_token = 0.000019

    @classmethod
    def from_settings(cls, settings: Settings, *, transport=None) -> "XAIProvider":
        return cls(
            settings.llmproxy_xai_model,
            api_key=settings.llmproxy_xai_api_key,
            base_url=settings.llmproxy_xai_base_url,
            timeout_seconds=settings.llmproxy_provider_timeout_seconds,
            transport=transport,
        )
