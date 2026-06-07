"""Fireworks provider implementation."""

from app.config import Settings
from app.providers.openai_provider import OpenAIProvider


class FireworksProvider(OpenAIProvider):
    provider_family = "Fireworks"
    provider_name = "fireworks"
    price_per_token = 0.000003
    supports_embeddings = False
    api_key_config_field = "llmproxy_fireworks_api_key"

    @classmethod
    def from_settings(cls, settings: Settings, *, transport=None) -> "FireworksProvider":
        return cls(
            settings.llmproxy_fireworks_model,
            api_key=settings.llmproxy_fireworks_api_key,
            base_url=settings.llmproxy_fireworks_base_url,
            timeout_seconds=settings.llmproxy_provider_timeout_seconds,
            transport=transport,
        )
