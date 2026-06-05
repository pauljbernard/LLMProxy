"""Base provider adapter."""

from abc import ABC, abstractmethod

from app.schemas.chat import ChatCompletionRequest


class BaseProvider(ABC):
    provider_family: str
    provider_name: str

    @abstractmethod
    async def chat(self, request: ChatCompletionRequest) -> dict[str, object]:
        raise NotImplementedError
