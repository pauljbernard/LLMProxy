"""llama.cpp local-runtime provider."""

from app.providers.ollama import OllamaProvider


class LlamaCppProvider(OllamaProvider):
    provider_name = "llama_cpp"
