"""Anthropic provider stub."""

from app.providers.openai_provider import OpenAIProvider


class AnthropicProvider(OpenAIProvider):
    provider_family = "Anthropic"
    provider_name = "anthropic"
