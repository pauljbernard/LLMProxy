"""vLLM local-runtime provider."""

from app.providers.ollama import OllamaProvider


class VLLMProvider(OllamaProvider):
    provider_name = "vllm"
