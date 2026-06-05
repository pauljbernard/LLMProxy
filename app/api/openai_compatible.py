"""OpenAI-compatible endpoints."""

from fastapi import APIRouter

from app.schemas.chat import ChatCompletionRequest, ChatCompletionResponse, ModelInfo

router = APIRouter(tags=["openai-compatible"])


@router.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(request: ChatCompletionRequest) -> ChatCompletionResponse:
    content = "llmProxy starter response"
    return ChatCompletionResponse.from_request(request, content=content)


@router.get("/v1/models", response_model=list[ModelInfo])
async def list_models() -> list[ModelInfo]:
    return [ModelInfo(id="proxy-auto"), ModelInfo(id="proxy-local"), ModelInfo(id="proxy-teacher")]


@router.post("/v1/embeddings")
async def embeddings() -> dict[str, str]:
    return {"status": "not_implemented"}
