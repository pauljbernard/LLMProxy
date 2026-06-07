"""Chat request and response schemas."""

from time import time
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class ChatMessage(BaseModel):
    role: str
    content: str | list[dict[str, object]] | None
    tool_calls: list[dict[str, object]] | None = None
    tool_call_id: str | None = None
    name: str | None = None


class ResponseFormatSpec(BaseModel):
    type: str
    json_schema: dict[str, object] | None = None


class ToolFunctionSpec(BaseModel):
    name: str
    description: str | None = None
    parameters: dict[str, object] | None = None
    strict: bool | None = None


class FunctionToolSpec(BaseModel):
    type: Literal["function"] = "function"
    function: ToolFunctionSpec


class MCPToolSpec(BaseModel):
    type: Literal["mcp"] = "mcp"
    server: str
    name: str
    description: str | None = None
    parameters: dict[str, object] | None = None


ChatToolSpec = FunctionToolSpec | MCPToolSpec


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
    session_id: str = Field(default_factory=lambda: f"sess_{uuid4().hex}")
    domain_hint: str | None = None
    task_type_hint: str | None = None
    privacy_hint: bool | None = None
    region_hint: str | None = None
    route_tags: list[str] = Field(default_factory=list)
    prompt_template_name: str | None = None
    prompt_template_version: int | None = None
    prompt_template_variables: dict[str, object] = Field(default_factory=dict)


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
    metadata: RequestMetadata = Field(default_factory=RequestMetadata)

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


class CompletionRequest(BaseModel):
    model: str
    prompt: str
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
    logprobs: int | None = None
    user: str | None = None
    timeout_seconds: float | None = None
    prompt_template_name: str | None = None
    prompt_template_version: int | None = None
    prompt_template_variables: dict[str, object] = Field(default_factory=dict)


class CompletionChoice(BaseModel):
    text: str
    index: int = 0
    logprobs: dict[str, object] | None = None
    finish_reason: str = "stop"


class CompletionResponse(BaseModel):
    id: str
    object: str = "text_completion"
    created: int
    model: str
    choices: list[CompletionChoice]
    usage: UsageInfo


class ImageGenerationRequest(BaseModel):
    prompt: str
    model: str | None = None
    n: int = 1
    size: str = "1024x1024"
    response_format: Literal["url", "b64_json"] = "url"
    user: str | None = None


class ImageData(BaseModel):
    url: str | None = None
    b64_json: str | None = None
    revised_prompt: str | None = None


class ImageGenerationResponse(BaseModel):
    created: int
    data: list[ImageData]


class ModerationRequest(BaseModel):
    input: str | list[str]
    model: str | None = None


class ModerationCategoryScores(BaseModel):
    values: dict[str, float] = Field(default_factory=dict)


class ModerationResult(BaseModel):
    flagged: bool
    categories: dict[str, bool] = Field(default_factory=dict)
    category_scores: ModerationCategoryScores


class ModerationResponse(BaseModel):
    id: str
    model: str
    results: list[ModerationResult]


class SpeechRequest(BaseModel):
    model: str | None = None
    input: str
    voice: str = "alloy"
    response_format: str = "mp3"
    speed: float | None = None
