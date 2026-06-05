"""AWS Bedrock provider stub."""

from app.providers.openai_provider import OpenAIProvider


class BedrockProvider(OpenAIProvider):
    provider_family = "AWS Bedrock"
    provider_name = "bedrock"
