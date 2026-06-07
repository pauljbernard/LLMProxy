"""Mistral provider implementation."""

from app.config import Settings
from app.providers.openai_provider import OpenAIProvider


class MistralProvider(OpenAIProvider):
    provider_family = "Mistral"
    provider_name = "mistral"
    price_per_token = 0.000008
    api_key_config_field = "llmproxy_mistral_api_key"

    @classmethod
    def from_settings(cls, settings: Settings, *, transport=None) -> "MistralProvider":
        return cls(
            settings.llmproxy_mistral_model,
            api_key=settings.llmproxy_mistral_api_key,
            base_url=settings.llmproxy_mistral_base_url,
            timeout_seconds=settings.llmproxy_provider_timeout_seconds,
            transport=transport,
        )
