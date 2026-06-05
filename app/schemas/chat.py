"""Chat request and response schemas."""

from time import time

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str
    content: str


class RequestMetadata(BaseModel):
    session_id: str
    domain_hint: str | None = None
    task_type_hint: str | None = None


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    stream: bool = False
    temperature: float = 0.2
    max_tokens: int = 1024
    metadata: RequestMetadata


class UsageInfo(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChoiceMessage(BaseModel):
    role: str = "assistant"
    content: str


class Choice(BaseModel):
    index: int = 0
    message: ChoiceMessage
    finish_reason: str = "stop"


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[Choice]
    usage: UsageInfo

    @classmethod
    def from_request(cls, request: ChatCompletionRequest, content: str) -> "ChatCompletionResponse":
        prompt_tokens = sum(len(message.content.split()) for message in request.messages)
        completion_tokens = len(content.split())
        return cls(
            id="chatcmpl_starter",
            created=int(time()),
            model=request.model,
            choices=[Choice(message=ChoiceMessage(content=content))],
            usage=UsageInfo(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
        )


class ModelInfo(BaseModel):
    id: str = Field(..., alias="id")
    object: str = "model"
