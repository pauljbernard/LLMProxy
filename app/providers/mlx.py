"""MLX local-runtime provider."""

from app.providers.ollama import OllamaProvider


class MLXProvider(OllamaProvider):
    provider_name = "mlx"
