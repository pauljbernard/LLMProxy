"""Chat request and response schemas."""

from time import time
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ChatMessage(BaseModel):
    role: str
    content: str | list[dict[str, object]] | None


class ResponseFormatSpec(BaseModel):
    type: str
    json_schema: dict[str, object] | None = None


class ToolFunctionSpec(BaseModel):
    name: str
    description: str | None = None
    parameters: dict[str, object] | None = None
    strict: bool | None = None


class ChatToolSpec(BaseModel):
    type: Literal["function"] = "function"
    function: ToolFunctionSpec


class LegacyFunctionSpec(BaseModel):
    name: str
    description: str | None = None
    parameters: dict[str, object] | None = None


class ToolCallFunction(BaseModel):
    name: str
    arguments: str


class ToolCall(BaseModel):
    id: str
    type: Literal["function"] = "function"
    function: ToolCallFunction


class RequestMetadata(BaseModel):
    session_id: str
    domain_hint: str | None = None
    task_type_hint: str | None = None
    privacy_hint: bool | None = None


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    stream: bool = False
    temperature: float = 0.2
    max_tokens: int = 1024
    top_p: float | None = None
    n: int | None = None
    stop: str | list[str] | None = None
    presence_penalty: float | None = None
    frequency_penalty: float | None = None
    seed: int | None = None
    logit_bias: dict[str, float] | None = None
    logprobs: bool | None = None
    top_logprobs: int | None = None
    user: str | None = None
    response_format: ResponseFormatSpec | None = None
    tools: list[ChatToolSpec] | None = None
    tool_choice: str | dict[str, object] | None = None
    parallel_tool_calls: bool | None = None
    functions: list[LegacyFunctionSpec] | None = None
    timeout_seconds: float | None = None
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
    content: str | None
    tool_calls: list[ToolCall] | None = None


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
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        finish_reason: str = "stop",
        tool_calls: list[dict[str, object]] | None = None,
    ) -> "ChatCompletionResponse":
        if prompt_tokens is None:
            prompt_tokens = 0
        if completion_tokens is None:
            completion_tokens = 0
        return cls(
            id=response_id,
            created=int(time()),
            model=resolved_model or request.model,
            choices=[
                Choice(
                    message=ChoiceMessage(
                        content=content,
                        tool_calls=[ToolCall.model_validate(item) for item in (tool_calls or [])] or None,
                    ),
                    finish_reason=finish_reason,
                )
            ],
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
    dimensions: int | None = None


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
