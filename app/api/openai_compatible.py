"""OpenAI-compatible endpoints."""

import asyncio
import json
from time import time
from time import perf_counter

from fastapi import HTTPException, status
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_session_factory
from app.api.dependencies import get_async_session, get_runtime_settings, require_api_token
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


def _stream_chunk_bytes(*, response_id: str, model: str, delta: dict[str, str], finish_reason: str | None) -> bytes:
    payload = {
        "id": response_id,
        "object": "chat.completion.chunk",
        "created": int(time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason,
            }
        ],
    }
    return f"data: {json.dumps(payload)}\n\n".encode("utf-8")


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


def _select_embedding_provider(
    *,
    request: EmbeddingRequest,
    settings: Settings,
    provider_registry: dict[str, object],
):
    provider_precedence = ("openai", "ollama", "azure_openai", "google", "anthropic", "xai", "bedrock")
    if request.model == settings.llmproxy_ollama_model and "ollama" in provider_registry:
        return provider_registry["ollama"]
    if request.model.startswith("text-embedding") and "openai" in provider_registry and settings.llmproxy_openai_api_key:
        return provider_registry["openai"]
    if request.model.startswith("text-embedding"):
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="OpenAI embeddings were requested but no OpenAI embedding provider is configured.",
        )
    for provider_key in provider_precedence:
        provider = provider_registry.get(provider_key)
        if provider is None:
            continue
        capability = getattr(provider, "capability", None)
        if capability is not None and capability.supports_embeddings and capability.model_id == request.model:
            return provider
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="No embedding provider is configured for this request.",
    )


async def _persist_shadow_response(
    *,
    request_log_id: str,
    shadow_result: dict[str, object],
    classification: dict[str, str],
) -> None:
    session = get_async_session_factory()()
    try:
        def _persist(sync_session):
            record_model_response(sync_session, request_log_id, shadow_result, response_role="shadow_response")
            sample_performance(
                sync_session,
                model_alias=str(shadow_result["model"]),
                domain=classification["domain"],
                request_log_id=request_log_id,
                route_type="shadow",
                cost_estimate=float(shadow_result["cost_estimate"]),
                quality_score=None,
                successful=True,
            )

        await session.run_sync(_persist)
        await session.commit()
    except Exception:
        await session.rollback()
    finally:
        await session.close()


async def _run_shadow_request(
    *,
    shadow_provider,
    request: ChatCompletionRequest,
    request_log_id: str,
    classification: dict[str, str],
    settings: Settings,
) -> None:
    try:
        if request.stream and getattr(shadow_provider, "supports_streaming", False):
            aggregated_content = ""
            prompt_tokens = 0
            completion_tokens = 0
            finish_reason = "stop"
            chunk_count = 0
            started_at = perf_counter()
            log_record(
                settings,
                level="INFO",
                component="proxy.shadow",
                category="stream",
                message="Shadow stream started",
                data={"request_id": request_log_id, "provider": shadow_provider.provider_name, "model": shadow_provider.model_id},
            )
            async for chunk in shadow_provider.stream_chat(request):
                chunk_count += 1
                aggregated_content += str(chunk.get("delta", ""))
                prompt_tokens = max(prompt_tokens, int(chunk.get("input_tokens", 0)))
                completion_tokens = max(completion_tokens, int(chunk.get("output_tokens", 0)))
                if chunk.get("finish_reason"):
                    finish_reason = str(chunk["finish_reason"])
            price_per_token = getattr(shadow_provider, "price_per_token", 0.0)
            shadow_result = {
                "model": shadow_provider.model_id,
                "content": aggregated_content,
                "input_tokens": prompt_tokens,
                "output_tokens": completion_tokens or len(aggregated_content.split()),
                "latency_ms": int((perf_counter() - started_at) * 1000),
                "finish_reason": finish_reason,
                "cost_estimate": round((prompt_tokens + completion_tokens) * price_per_token, 6),
                "raw_response": {"streamed": True, "chunk_count": chunk_count},
                "provider": shadow_provider.provider_name,
                "provider_family": shadow_provider.provider_family,
            }
            log_record(
                settings,
                level="INFO",
                component="proxy.shadow",
                category="stream",
                message="Shadow stream completed",
                data={"request_id": request_log_id, "provider": shadow_provider.provider_name, "model": shadow_provider.model_id, "chunk_count": chunk_count},
            )
        else:
            shadow_result = await shadow_provider.invoke(request)
    except Exception:
        log_record(
            settings,
            level="ERROR",
            component="proxy.shadow",
            category="error",
            message="Shadow request failed",
            data={"request_id": request_log_id, "provider": getattr(shadow_provider, "provider_name", "unknown"), "model": getattr(shadow_provider, "model_id", "unknown")},
        )
        return
    await _persist_shadow_response(
        request_log_id=request_log_id,
        shadow_result=shadow_result,
        classification=classification,
    )


async def _record_request_async(
    session: AsyncSession,
    *,
    request: ChatCompletionRequest,
    classification: dict[str, str],
) -> tuple[str, object]:
    def _write(sync_session):
        request_log = record_request(sync_session, request, classification)
        sync_session.flush()
        return request_log.id, request_log.created_at

    return await session.run_sync(_write)


async def _resolve_route_and_registry(
    session: AsyncSession,
    *,
    request_id: str,
    request: ChatCompletionRequest,
    classification: dict[str, str],
    settings: Settings,
):
    def _resolve(sync_session):
        selected_route = select_route(request_id, request, classification, settings, session=sync_session)
        provider_registry = get_provider_registry(settings, session=sync_session)
        return selected_route, provider_registry

    return await session.run_sync(_resolve)


async def _persist_selected_response_async(
    session: AsyncSession,
    *,
    request: ChatCompletionRequest,
    request_id: str,
    request_created_at,
    classification: dict[str, str],
    provider_result: dict[str, object],
    resolved_decision,
) -> None:
    def _persist(sync_session):
        record_routing_decision(sync_session, request_id, resolved_decision)
        sync_session.flush()
        response_record = record_model_response(sync_session, request_id, provider_result, response_role="selected_response")
        sample_performance(
            sync_session,
            model_alias=str(provider_result["model"]),
            domain=classification["domain"],
            request_log_id=request_id,
            route_type=resolved_decision.selected_mode,
            cost_estimate=float(provider_result["cost_estimate"]),
            quality_score=None,
            successful=True,
        )
        if classification["privacy_level"] != "private":
            capture_training_candidate(
                sync_session,
                request_log_id=request_id,
                routing_decision_id=resolved_decision.routing_decision_id,
                session_id=request.metadata.session_id,
                domain=classification["domain"],
                task_type=classification["task_type"],
                quality_score=None,
                selected_response=str(provider_result["content"]),
                messages=[message.model_dump(mode="json") for message in request.messages],
                provenance={
                    "request_id": request_id,
                    "source": resolved_decision.selected_mode,
                    "teacher_models": [provider_result["model"]],
                    "judge_model": None,
                    "created_at": request_created_at.isoformat() if request_created_at else None,
                },
                validation={
                    "validated": True,
                    "validation_type": "rule_based_capture",
                    "tests_passed": None,
                    "static_checks_passed": None,
                    "secrets_detected": False,
                },
                metadata={
                    "selected_provider": provider_result["provider"],
                    "selected_model": provider_result["model"],
                    "selected_response_id": response_record.id,
                    "privacy_level": classification["privacy_level"],
                },
            )

    await session.run_sync(_persist)


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


async def _stream_with_fallback(
    provider_registry: dict[str, object],
    selected_route,
    request: ChatCompletionRequest,
):
    attempted = [selected_route.provider_key]
    candidates = [(selected_route.provider_key, selected_route.decision.selected_model, selected_route.decision)]
    for fallback in selected_route.decision.fallback_chain:
        if fallback.provider in attempted or fallback.provider not in provider_registry:
            continue
        attempted.append(fallback.provider)
        candidates.append((fallback.provider, fallback.model, selected_route.decision))

    for index, (provider_key, selected_model, decision) in enumerate(candidates):
        provider = provider_registry.get(provider_key)
        if provider is None or not getattr(provider, "supports_streaming", False):
            continue
        started = False
        try:
            async for chunk in provider.stream_chat(request):
                if not started and index > 0:
                    decision.selected_provider = provider_key
                    decision.selected_provider_family = getattr(provider, "provider_family", provider_key)
                    decision.selected_model = selected_model
                    decision.selected_mode = "fallback"
                    decision.decision_rationale = (
                        f"{decision.decision_rationale} Fallback engaged after runtime error."
                    )
                started = True
                yield chunk, decision
            return
        except Exception:
            if started:
                raise
            continue

    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="No streaming-capable provider in the selected route or fallback chain succeeded.",
    )


@router.post(
    "/v1/chat/completions",
    response_model=None,
    dependencies=[Depends(require_api_token)],
)
async def chat_completions(
    request: ChatCompletionRequest,
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_runtime_settings),
) -> ChatCompletionResponse | StreamingResponse:
    request_log_id = None
    classification = classify_request(request)
    try:
        request_log_id, request_created_at = await _record_request_async(
            session,
            request=request,
            classification=classification,
        )
        selected_route, provider_registry = await _resolve_route_and_registry(
            session,
            request_id=request_log_id,
            request=request,
            classification=classification,
            settings=settings,
        )
        if request.stream:
            selected_provider = provider_registry.get(selected_route.provider_key)
            if selected_provider is None or not getattr(selected_provider, "supports_streaming", False):
                raise HTTPException(
                    status_code=status.HTTP_501_NOT_IMPLEMENTED,
                    detail="Streaming is not supported for the selected route.",
                )
            response_id = request_log_id.replace("req_", "chatcmpl_")

            async def event_stream():
                started_at = perf_counter()
                aggregated_content = ""
                resolved_decision = selected_route.decision
                provider_model = resolved_decision.selected_model
                prompt_tokens = 0
                completion_tokens = 0
                finish_reason = "stop"
                yield _stream_chunk_bytes(
                    response_id=response_id,
                    model=provider_model,
                    delta={"role": "assistant"},
                    finish_reason=None,
                )
                try:
                    async for chunk, resolved_decision in _stream_with_fallback(provider_registry, selected_route, request):
                        provider_model = str(chunk.get("model", provider_model))
                        delta_text = str(chunk.get("delta", ""))
                        if delta_text:
                            aggregated_content += delta_text
                            yield _stream_chunk_bytes(
                                response_id=response_id,
                                model=provider_model,
                                delta={"content": delta_text},
                                finish_reason=None,
                            )
                        prompt_tokens = max(prompt_tokens, int(chunk.get("input_tokens", 0)))
                        completion_tokens = max(completion_tokens, int(chunk.get("output_tokens", 0)))
                        if chunk.get("finish_reason"):
                            finish_reason = str(chunk["finish_reason"])
                    if prompt_tokens == 0:
                        prompt_tokens = sum(len(message.content.split()) for message in request.messages)
                    if completion_tokens == 0:
                        completion_tokens = len(aggregated_content.split())
                    provider_name = resolved_decision.selected_provider
                    selected_provider = provider_registry.get(provider_name)
                    price_per_token = getattr(selected_provider, "price_per_token", 0.0)
                    provider_result = {
                        "model": provider_model,
                        "content": aggregated_content,
                        "input_tokens": prompt_tokens,
                        "output_tokens": completion_tokens,
                        "latency_ms": int((perf_counter() - started_at) * 1000),
                        "finish_reason": finish_reason,
                        "cost_estimate": round((prompt_tokens + completion_tokens) * price_per_token, 6),
                        "raw_response": {"streamed": True},
                        "provider": provider_name,
                        "provider_family": resolved_decision.selected_provider_family,
                    }
                    await _persist_selected_response_async(
                        session,
                        request=request,
                        request_id=request_log_id,
                        request_created_at=request_created_at,
                        classification=classification,
                        provider_result=provider_result,
                        resolved_decision=resolved_decision,
                    )
                    for shadow_provider_key in selected_route.shadow_provider_keys:
                        shadow_provider = provider_registry.get(shadow_provider_key)
                        if shadow_provider is None:
                            continue
                        asyncio.create_task(
                            _run_shadow_request(
                                shadow_provider=shadow_provider,
                                request=request,
                                request_log_id=request_log_id,
                                classification=classification,
                                settings=settings,
                            )
                        )
                    await session.commit()
                    log_record(
                        settings,
                        level="INFO",
                        component="proxy.chat",
                        category="request",
                        message="Streaming chat completion served",
                        data={
                            "request_id": request_log_id,
                            "session_id": request.metadata.session_id,
                            "domain": classification["domain"],
                            "task_type": classification["task_type"],
                            "selected_provider": provider_result["provider"],
                            "selected_model": provider_result["model"],
                            "selected_mode": resolved_decision.selected_mode,
                            "stream": True,
                        },
                    )
                    yield _stream_chunk_bytes(
                        response_id=response_id,
                        model=provider_model,
                        delta={},
                        finish_reason=finish_reason,
                    )
                except asyncio.CancelledError:
                    await session.rollback()
                    raise
                except Exception as exc:
                    await session.rollback()
                    log_record(
                        settings,
                        level="ERROR",
                        component="proxy.chat",
                        category="error",
                        message="Streaming chat completion failed",
                        data={
                            "request_id": request_log_id,
                            "session_id": request.metadata.session_id,
                            "error": str(exc),
                        },
                    )
                    raise
                yield b"data: [DONE]\n\n"

            return StreamingResponse(event_stream(), media_type="text/event-stream")
        provider_result, resolved_decision = await _invoke_with_fallback(provider_registry, selected_route, request)
        await _persist_selected_response_async(
            session,
            request=request,
            request_id=request_log_id,
            request_created_at=request_created_at,
            classification=classification,
            provider_result=provider_result,
            resolved_decision=resolved_decision,
        )
        for shadow_provider_key in selected_route.shadow_provider_keys:
            shadow_provider = provider_registry.get(shadow_provider_key)
            if shadow_provider is None:
                continue
            asyncio.create_task(
                _run_shadow_request(
                    shadow_provider=shadow_provider,
                    request=request,
                    request_log_id=request_log_id,
                    classification=classification,
                    settings=settings,
                )
            )
        await session.commit()
        log_record(
            settings,
            level="INFO",
            component="proxy.chat",
            category="request",
            message="Chat completion served",
            data={
                "request_id": request_log_id,
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
            response_id=request_log_id.replace("req_", "chatcmpl_"),
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
                "request_id": request_log_id,
                "session_id": request.metadata.session_id,
                "detail": exc.detail,
                "status_code": exc.status_code,
            },
        )
        raise
    except Exception as exc:
        await session.rollback()
        log_record(
            settings,
            level="ERROR",
            component="proxy.chat",
            category="error",
            message="Unexpected chat completion failure",
            data={
                "request_id": request_log_id,
                "session_id": request.metadata.session_id,
                "error": str(exc),
            },
        )
        raise


@router.get("/v1/models", response_model=list[ModelInfo], dependencies=[Depends(require_api_token)])
def list_models(
    settings: Settings = Depends(get_runtime_settings),
) -> list[ModelInfo]:
    return [ModelInfo.model_validate(item) for item in list_proxy_models(settings)]


@router.post("/v1/embeddings", response_model=EmbeddingResponse, dependencies=[Depends(require_api_token)])
async def embeddings(
    request: EmbeddingRequest,
    settings: Settings = Depends(get_runtime_settings),
) -> EmbeddingResponse:
    inputs = _normalize_embedding_inputs(request)
    provider_registry = get_provider_registry(settings)
    provider = _select_embedding_provider(
        request=request,
        settings=settings,
        provider_registry=provider_registry,
    )
    try:
        vectors = await provider.embed(inputs, model=request.model, dimensions=request.dimensions)
    except NotImplementedError as exc:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc)) from exc
    data = [
        EmbeddingVector(index=index, embedding=vector)
        for index, vector in enumerate(vectors)
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
