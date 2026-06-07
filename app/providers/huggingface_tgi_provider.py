"""HuggingFace TGI provider implementation."""

from app.config import Settings
from app.providers.openai_provider import OpenAIProvider


class HuggingFaceTGIProvider(OpenAIProvider):
    provider_family = "HuggingFace TGI"
    provider_name = "huggingface_tgi"
    price_per_token = 0.0

    @classmethod
    def from_settings(cls, settings: Settings, *, transport=None) -> "HuggingFaceTGIProvider":
        return cls(
            settings.llmproxy_huggingface_tgi_model,
            api_key=settings.llmproxy_huggingface_tgi_api_key,
            base_url=settings.llmproxy_huggingface_tgi_base_url,
            timeout_seconds=settings.llmproxy_provider_timeout_seconds,
            transport=transport,
            require_api_key=False,
        )
