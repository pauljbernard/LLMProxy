"""Azure OpenAI provider stub."""

from app.providers.openai_provider import OpenAIProvider


class AzureOpenAIProvider(OpenAIProvider):
    provider_family = "Azure OpenAI"
    provider_name = "azure_openai"
