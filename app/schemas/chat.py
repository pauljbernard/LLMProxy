"""Chat request and response schemas."""

from time import time

from pydantic import BaseModel, Field, field_validator


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

    @field_validator("messages")
    @classmethod
    def validate_messages(cls, value: list[ChatMessage]) -> list[ChatMessage]:
        if not value:
            raise ValueError("messages must contain at least one item")
        return value


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
    def from_request(
        cls,
        request: ChatCompletionRequest,
        content: str,
        response_id: str = "chatcmpl_generated",
        resolved_model: str | None = None,
    ) -> "ChatCompletionResponse":
        prompt_tokens = sum(len(message.content.split()) for message in request.messages)
        completion_tokens = len(content.split())
        return cls(
            id=response_id,
            created=int(time()),
            model=resolved_model or request.model,
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


class EmbeddingRequestInput(BaseModel):
    text: str


class EmbeddingRequest(BaseModel):
    model: str
    input: str | list[str] | list[EmbeddingRequestInput]
    user: str | None = None


class EmbeddingVector(BaseModel):
    object: str = "embedding"
    embedding: list[float]
    index: int


class EmbeddingUsage(BaseModel):
    prompt_tokens: int
    total_tokens: int


class EmbeddingResponse(BaseModel):
    object: str = "list"
    data: list[EmbeddingVector]
    model: str
    usage: EmbeddingUsage
