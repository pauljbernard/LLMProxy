"""Groq provider implementation."""

from app.config import Settings
from app.providers.openai_provider import OpenAIProvider


class GroqProvider(OpenAIProvider):
    provider_family = "Groq"
    provider_name = "groq"
    price_per_token = 0.000003
    supports_embeddings = False
    api_key_config_field = "llmproxy_groq_api_key"

    @classmethod
    def from_settings(cls, settings: Settings, *, transport=None) -> "GroqProvider":
        return cls(
            settings.llmproxy_groq_model,
            api_key=settings.llmproxy_groq_api_key,
            base_url=settings.llmproxy_groq_base_url,
            timeout_seconds=settings.llmproxy_provider_timeout_seconds,
            transport=transport,
        )
