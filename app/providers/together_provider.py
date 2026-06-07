"""Together AI provider implementation."""

from app.config import Settings
from app.providers.openai_provider import OpenAIProvider


class TogetherProvider(OpenAIProvider):
    provider_family = "Together"
    provider_name = "together"
    price_per_token = 0.000004
    api_key_config_field = "llmproxy_together_api_key"

    @classmethod
    def from_settings(cls, settings: Settings, *, transport=None) -> "TogetherProvider":
        return cls(
            settings.llmproxy_together_model,
            api_key=settings.llmproxy_together_api_key,
            base_url=settings.llmproxy_together_base_url,
            timeout_seconds=settings.llmproxy_provider_timeout_seconds,
            transport=transport,
        )
