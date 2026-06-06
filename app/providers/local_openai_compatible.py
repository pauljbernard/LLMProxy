"""Local OpenAI-compatible provider implementation."""

from app.providers.openai_provider import OpenAIProvider


class LocalOpenAICompatibleProvider(OpenAIProvider):
    provider_family = "local runtime"
    price_per_token = 0.0

    def __init__(
        self,
        model_id: str,
        *,
        runtime_name: str,
        base_url: str,
        timeout_seconds: float = 60.0,
        transport=None,
    ) -> None:
        super().__init__(
            model_id,
            api_key=None,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            transport=transport,
            require_api_key=False,
        )
        self.provider_name = runtime_name
