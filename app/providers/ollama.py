"""Ollama provider stub."""

from app.providers.openai_provider import OpenAIProvider


class OllamaProvider(OpenAIProvider):
    provider_family = "local runtime"
    provider_name = "ollama"
