"""Google provider stub."""

from app.providers.openai_provider import OpenAIProvider


class GoogleProvider(OpenAIProvider):
    provider_family = "Google Gemini"
    provider_name = "google"
