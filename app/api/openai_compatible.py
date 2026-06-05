"""OpenAI-compatible endpoints."""

from hashlib import sha256
from math import fmod

from fastapi import HTTPException, status
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_runtime_settings, get_session, require_api_token
from app.config import Settings
from app.integration.performance import sample_performance
from app.proxy.candidates import capture_training_candidate
from app.proxy.classifier import classify_request
from app.proxy.router import select_route
from app.proxy.recorder import record_model_response, record_request, record_routing_decision
from app.registry.model_registry import get_provider_registry, list_proxy_models
from app.services.observability import log_record
from app.schemas.chat import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    EmbeddingRequest,
    EmbeddingResponse,
    EmbeddingUsage,
    EmbeddingVector,
    ModelInfo,
)

router = APIRouter(tags=["openai-compatible"])


def _normalize_embedding_inputs(request: EmbeddingRequest) -> list[str]:
    if isinstance(request.input, str):
        return [request.input]
    values: list[str] = []
    for item in request.input:
        if isinstance(item, str):
            values.append(item)
        else:
            values.append(item.text)
    return values


def _embedding_for_text(text: str, *, dimensions: int = 16) -> list[float]:
    digest = sha256(text.encode("utf-8")).digest()
    values: list[float] = []
    for index in range(dimensions):
        byte_value = digest[index % len(digest)]
        values.append(round(fmod(byte_value / 255.0, 1.0), 6))
    return values


def _sample_quality_score(*, provider: str, route_type: str) -> float:
    if provider != "ollama":
        return 0.88
    if route_type in {"local_production", "local_canary", "shadow"}:
        return 0.89
    return 0.84


async def _invoke_with_fallback(
    provider_registry: dict[str, object],
    selected_route,
    request: ChatCompletionRequest,
) -> tuple[dict[str, object], object]:
    attempted = [selected_route.provider_key]
    try:
        provider_result = await provider_registry[selected_route.provider_key].invoke(request)
        return provider_result, selected_route.decision
    except Exception:
        for fallback in selected_route.decision.fallback_chain:
            fallback_key = fallback.provider
            if fallback_key in attempted or fallback_key not in provider_registry:
                continue
            attempted.append(fallback_key)
            try:
                provider_result = await provider_registry[fallback_key].invoke(request)
            except Exception:
                continue
            selected_route.decision.selected_provider = fallback.provider
            selected_route.decision.selected_provider_family = provider_result["provider_family"]
            selected_route.decision.selected_model = fallback.model
            selected_route.decision.selected_mode = "fallback"
            selected_route.decision.decision_rationale = (
                f"{selected_route.decision.decision_rationale} Fallback engaged after runtime error."
            )
            return provider_result, selected_route.decision
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="No provider in the selected route or fallback chain succeeded.",
    )


@router.post("/v1/chat/completions", response_model=ChatCompletionResponse, dependencies=[Depends(require_api_token)])
async def chat_completions(
    request: ChatCompletionRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
) -> ChatCompletionResponse:
    request_log = None
    classification = classify_request(request)
    try:
        request_log = record_request(session, request, classification)
        session.flush()
        selected_route = select_route(request_log.id, request, classification, settings, session=session)

        provider_registry = get_provider_registry(settings, session=session)
        provider_result, resolved_decision = await _invoke_with_fallback(provider_registry, selected_route, request)
        record_routing_decision(session, request_log.id, resolved_decision)
        session.flush()
        response_record = record_model_response(session, request_log.id, provider_result, response_role="selected_response")
        sample_performance(
            session,
            model_alias=str(provider_result["model"]),
            domain=classification["domain"],
            request_log_id=request_log.id,
            route_type=resolved_decision.selected_mode,
            cost_estimate=float(provider_result["cost_estimate"]),
            quality_score=_sample_quality_score(
                provider=str(provider_result["provider"]),
                route_type=resolved_decision.selected_mode,
            ),
            successful=True,
        )
        for shadow_provider_key in selected_route.shadow_provider_keys:
            shadow_provider = provider_registry.get(shadow_provider_key)
            if shadow_provider is None:
                continue
            try:
                shadow_result = await shadow_provider.invoke(request)
            except Exception:
                continue
            record_model_response(session, request_log.id, shadow_result, response_role="shadow_response")
            sample_performance(
                session,
                model_alias=str(shadow_result["model"]),
                domain=classification["domain"],
                request_log_id=request_log.id,
                route_type="shadow",
                cost_estimate=float(shadow_result["cost_estimate"]),
                quality_score=_sample_quality_score(provider=str(shadow_result["provider"]), route_type="shadow"),
                successful=True,
            )
        capture_training_candidate(
            session,
            request_log_id=request_log.id,
            routing_decision_id=resolved_decision.routing_decision_id,
            session_id=request.metadata.session_id,
            domain=classification["domain"],
            task_type=classification["task_type"],
            quality_score=0.82 if provider_result["provider"] == "ollama" else 0.86,
            selected_response=str(provider_result["content"]),
            messages=[message.model_dump(mode="json") for message in request.messages],
            provenance={
                "request_id": request_log.id,
                "source": resolved_decision.selected_mode,
                "teacher_models": [provider_result["model"]],
                "judge_model": None,
                "created_at": request_log.created_at.isoformat() if request_log.created_at else None,
            },
            validation={
                "validated": True,
                "validation_type": "rule_based_capture",
                "tests_passed": None,
                "static_checks_passed": None,
                "secrets_detected": classification["privacy_level"] == "private",
            },
            metadata={
                "selected_provider": provider_result["provider"],
                "selected_model": provider_result["model"],
                "selected_response_id": response_record.id,
                "privacy_level": classification["privacy_level"],
            },
        )
        session.commit()
        log_record(
            settings,
            level="INFO",
            component="proxy.chat",
            category="request",
            message="Chat completion served",
            data={
                "request_id": request_log.id,
                "session_id": request.metadata.session_id,
                "domain": classification["domain"],
                "task_type": classification["task_type"],
                "selected_provider": provider_result["provider"],
                "selected_model": provider_result["model"],
                "selected_mode": resolved_decision.selected_mode,
            },
        )
        return ChatCompletionResponse.from_request(
            request,
            content=str(provider_result["content"]),
            response_id=request_log.id.replace("req_", "chatcmpl_"),
            resolved_model=str(provider_result["model"]),
        )
    except HTTPException as exc:
        log_record(
            settings,
            level="ERROR",
            component="proxy.chat",
            category="error",
            message="Chat completion failed",
            data={
                "request_id": request_log.id if request_log is not None else None,
                "session_id": request.metadata.session_id,
                "detail": exc.detail,
                "status_code": exc.status_code,
            },
        )
        raise
    except Exception as exc:
        log_record(
            settings,
            level="ERROR",
            component="proxy.chat",
            category="error",
            message="Unexpected chat completion failure",
            data={
                "request_id": request_log.id if request_log is not None else None,
                "session_id": request.metadata.session_id,
                "error": str(exc),
            },
        )
        raise


@router.get("/v1/models", response_model=list[ModelInfo], dependencies=[Depends(require_api_token)])
async def list_models(
    settings: Settings = Depends(get_runtime_settings),
) -> list[ModelInfo]:
    return [ModelInfo.model_validate(item) for item in list_proxy_models(settings)]


@router.post("/v1/embeddings", response_model=EmbeddingResponse, dependencies=[Depends(require_api_token)])
async def embeddings(request: EmbeddingRequest) -> EmbeddingResponse:
    inputs = _normalize_embedding_inputs(request)
    data = [
        EmbeddingVector(index=index, embedding=_embedding_for_text(text))
        for index, text in enumerate(inputs)
    ]
    prompt_tokens = sum(len(text.split()) for text in inputs)
    response = EmbeddingResponse(
        data=data,
        model=request.model,
        usage=EmbeddingUsage(prompt_tokens=prompt_tokens, total_tokens=prompt_tokens),
    )
    log_record(
        get_runtime_settings(),
        level="INFO",
        component="proxy.embeddings",
        category="request",
        message="Embedding request served",
        data={"model": request.model, "input_count": len(inputs), "prompt_tokens": prompt_tokens},
    )
    return response
