"""OpenAI provider stub."""

from app.providers.base import BaseProvider
from app.schemas.chat import ChatCompletionRequest


class OpenAIProvider(BaseProvider):
    provider_family = "OpenAI"
    provider_name = "openai"

    async def chat(self, request: ChatCompletionRequest) -> dict[str, object]:
        return {"provider": self.provider_name, "model": request.model}
