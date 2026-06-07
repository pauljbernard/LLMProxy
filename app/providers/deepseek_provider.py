"""DeepSeek provider implementation."""

from app.config import Settings
from app.providers.openai_provider import OpenAIProvider


class DeepSeekProvider(OpenAIProvider):
    provider_family = "DeepSeek"
    provider_name = "deepseek"
    price_per_token = 0.000002
    supports_embeddings = False
    api_key_config_field = "llmproxy_deepseek_api_key"

    @classmethod
    def from_settings(cls, settings: Settings, *, transport=None) -> "DeepSeekProvider":
        return cls(
            settings.llmproxy_deepseek_model,
            api_key=settings.llmproxy_deepseek_api_key,
            base_url=settings.llmproxy_deepseek_base_url,
            timeout_seconds=settings.llmproxy_provider_timeout_seconds,
            transport=transport,
        )
