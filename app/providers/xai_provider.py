"""xAI provider stub."""

from app.providers.openai_provider import OpenAIProvider


class XAIProvider(OpenAIProvider):
    provider_family = "xAI"
    provider_name = "xai"
