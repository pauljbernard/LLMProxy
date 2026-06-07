"""Perplexity Sonar provider implementation."""

from app.config import Settings
from app.providers.openai_provider import OpenAIProvider


class PerplexityProvider(OpenAIProvider):
    provider_family = "Perplexity"
    provider_name = "perplexity"
    price_per_token = 0.00001
    supports_embeddings = False
    api_key_config_field = "llmproxy_perplexity_api_key"

    @classmethod
    def from_settings(cls, settings: Settings, *, transport=None) -> "PerplexityProvider":
        return cls(
            settings.llmproxy_perplexity_model,
            api_key=settings.llmproxy_perplexity_api_key,
            base_url=settings.llmproxy_perplexity_base_url,
            timeout_seconds=settings.llmproxy_provider_timeout_seconds,
            transport=transport,
        )
