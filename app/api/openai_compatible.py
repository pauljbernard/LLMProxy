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
from app.api.dependencies import AuthPrincipal, enforce_budget, enforce_model_access, record_virtual_key_usage
from app.config import Settings
from app.integration.performance import sample_performance
from app.proxy.candidates import capture_training_candidate
from app.proxy.classifier import classify_request
from app.proxy.router import select_route
from app.proxy.recorder import record_model_response, record_request, record_routing_decision
from app.registry.model_registry import get_provider_registry, list_proxy_models, resolve_provider
from app.services.observability import log_record
from app.services.provider_health import (
    is_provider_cooled_down,
    record_provider_failure,
    record_provider_success,
)
from app.services.response_cache import cache_key as response_cache_key, get_cached_response, put_cached_response
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


def _stream_chunk_bytes(*, response_id: str, model: str, delta: dict[str, object], finish_reason: str | None) -> bytes:
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


def _merge_tool_calls(
    existing: list[dict[str, object]],
    chunk_tool_calls: list[dict[str, object]] | None,
) -> list[dict[str, object]]:
    if not chunk_tool_calls:
        return existing
    for item in chunk_tool_calls:
        if not isinstance(item, dict):
            continue
        index = item.get("index")
        if isinstance(index, int) and 0 <= index < len(existing):
            current = existing[index]
            current_id = item.get("id")
            if isinstance(current_id, str):
                current["id"] = current_id
            if item.get("type"):
                current["type"] = item["type"]
            function = item.get("function")
            if isinstance(function, dict):
                current_function = current.setdefault("function", {})
                if isinstance(function.get("name"), str):
                    current_function["name"] = function["name"]
                if isinstance(function.get("arguments"), str):
                    current_function["arguments"] = str(current_function.get("arguments", "")) + function["arguments"]
            continue
        copy = dict(item)
        copy.pop("index", None)
        existing.append(copy)
    return existing


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


def _message_token_estimate(messages) -> int:
    total = 0
    for message in messages:
        content = getattr(message, "content", "")
        if isinstance(content, str):
            total += len(content.split())
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    total += len(str(item["text"]).split())
    return total


def _request_fits_provider(request: ChatCompletionRequest, provider) -> bool:
    capability = getattr(provider, "capability", None)
    if capability is None:
        return True
    prompt_tokens = _message_token_estimate(request.messages)
    max_context = int(getattr(capability, "max_context_tokens", 0) or 0)
    max_output = int(getattr(capability, "max_output_tokens", 0) or 0)
    if max_output and request.max_tokens > max_output:
        return False
    if max_context and (prompt_tokens + request.max_tokens) > max_context:
        return False
    return True


def _cache_payload_for_request(request: ChatCompletionRequest, *, provider_key: str, model_id: str) -> dict[str, object]:
    return {
        "requested_model": request.model,
        "provider_key": provider_key,
        "model_id": model_id,
        "messages": [message.model_dump(mode="json") for message in request.messages],
        "temperature": request.temperature,
        "max_tokens": request.max_tokens,
        "top_p": request.top_p,
        "stop": request.stop,
        "presence_penalty": request.presence_penalty,
        "frequency_penalty": request.frequency_penalty,
        "seed": request.seed,
        "response_format": request.response_format.model_dump(mode="json") if request.response_format else None,
        "tool_choice": request.tool_choice,
        "tools": [tool.model_dump(mode="json") for tool in (request.tools or [])],
        "functions": [fn.model_dump(mode="json") for fn in (request.functions or [])],
    }


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
            aggregated_tool_calls: list[dict[str, object]] = []
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


def _provider_for_route(
    *,
    settings: Settings,
    provider_registry: dict[str, object],
    selected_route,
    provider_key: str,
):
    entry_index = getattr(selected_route, "entry_index", {})
    return resolve_provider(
        settings,
        provider_registry,
        provider_key=provider_key,
        entry=entry_index.get(provider_key),
    )


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


async def _record_principal_usage_async(
    session: AsyncSession,
    *,
    principal: AuthPrincipal,
    cost_usd: float,
) -> None:
    def _write(sync_session):
        record_virtual_key_usage(sync_session, principal, cost_usd=cost_usd)

    await session.run_sync(_write)


async def _invoke_with_fallback(
    settings: Settings,
    provider_registry: dict[str, object],
    selected_route,
    request: ChatCompletionRequest,
) -> tuple[dict[str, object], object]:
    attempted = [selected_route.provider_key]
    context_rejected = False
    try:
        provider = _provider_for_route(
            settings=settings,
            provider_registry=provider_registry,
            selected_route=selected_route,
            provider_key=selected_route.provider_key,
        )
        if provider is None:
            raise KeyError(selected_route.provider_key)
        if not _request_fits_provider(request, provider):
            context_rejected = True
            raise ValueError("context_window_exceeded")
        provider_result = await _invoke_provider_with_retries(
            settings=settings,
            provider_key=selected_route.provider_key,
            provider=provider,
            request=request,
        )
        return provider_result, selected_route.decision
    except Exception:
        for fallback in selected_route.decision.fallback_chain:
            fallback_key = fallback.provider
            if fallback_key in attempted:
                continue
            attempted.append(fallback_key)
            if is_provider_cooled_down(fallback_key):
                continue
            try:
                provider = _provider_for_route(
                    settings=settings,
                    provider_registry=provider_registry,
                    selected_route=selected_route,
                    provider_key=fallback_key,
                )
                if provider is None:
                    continue
                if not _request_fits_provider(request, provider):
                    context_rejected = True
                    continue
                provider_result = await _invoke_provider_with_retries(
                    settings=settings,
                    provider_key=fallback_key,
                    provider=provider,
                    request=request,
                )
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
        if context_rejected:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The request exceeds the context window or output limits of all candidate providers.",
            )
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="No provider in the selected route or fallback chain succeeded.",
    )


async def _stream_with_fallback(
    settings: Settings,
    provider_registry: dict[str, object],
    selected_route,
    request: ChatCompletionRequest,
):
    attempted = [selected_route.provider_key]
    context_rejected = False
    candidates = [(selected_route.provider_key, selected_route.decision.selected_model, selected_route.decision)]
    for fallback in selected_route.decision.fallback_chain:
        if fallback.provider in attempted:
            continue
        attempted.append(fallback.provider)
        candidates.append((fallback.provider, fallback.model, selected_route.decision))

    for index, (provider_key, selected_model, decision) in enumerate(candidates):
        if is_provider_cooled_down(provider_key):
            continue
        provider = _provider_for_route(
            settings=settings,
            provider_registry=provider_registry,
            selected_route=selected_route,
            provider_key=provider_key,
        )
        if provider is None or not getattr(provider, "supports_streaming", False):
            continue
        if not _request_fits_provider(request, provider):
            context_rejected = True
            continue
        started = False
        try:
            async for chunk in _stream_provider_with_retries(
                settings=settings,
                provider_key=provider_key,
                provider=provider,
                request=request,
            ):
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
            continue

    if context_rejected:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The request exceeds the context window or output limits of all candidate providers.",
        )

    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="No streaming-capable provider in the selected route or fallback chain succeeded.",
    )


async def _invoke_provider_with_retries(*, settings: Settings, provider_key: str, provider, request: ChatCompletionRequest):
    attempt = 0
    while True:
        try:
            result = await provider.invoke(request)
            record_provider_success(provider_key)
            return result
        except Exception:
            attempt += 1
            cooled_down = record_provider_failure(
                provider_key,
                allowed_fails=settings.llmproxy_provider_allowed_fails,
                cooldown_seconds=settings.llmproxy_provider_cooldown_seconds,
            )
            if attempt > settings.llmproxy_provider_max_retries:
                raise
            if cooled_down:
                raise
            await asyncio.sleep(settings.llmproxy_provider_retry_backoff_seconds * (2 ** (attempt - 1)))


async def _stream_provider_with_retries(*, settings: Settings, provider_key: str, provider, request: ChatCompletionRequest):
    attempt = 0
    while True:
        started = False
        try:
            async for chunk in provider.stream_chat(request):
                started = True
                yield chunk
            record_provider_success(provider_key)
            return
        except Exception:
            cooled_down = record_provider_failure(
                provider_key,
                allowed_fails=settings.llmproxy_provider_allowed_fails,
                cooldown_seconds=settings.llmproxy_provider_cooldown_seconds,
            )
            if started:
                raise
            attempt += 1
            if attempt > settings.llmproxy_provider_max_retries:
                raise
            if cooled_down:
                raise
            await asyncio.sleep(settings.llmproxy_provider_retry_backoff_seconds * (2 ** (attempt - 1)))


@router.post(
    "/v1/chat/completions",
    response_model=None,
)
async def chat_completions(
    request: ChatCompletionRequest,
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_runtime_settings),
    principal: AuthPrincipal = Depends(require_api_token),
) -> ChatCompletionResponse | StreamingResponse:
    request_log_id = None
    enforce_budget(principal)
    enforce_model_access(principal, request.model)
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
        cache_hit_result = None
        cache_key_value = None
        if request.stream:
            selected_provider = _provider_for_route(
                settings=settings,
                provider_registry=provider_registry,
                selected_route=selected_route,
                provider_key=selected_route.provider_key,
            )
            if selected_provider is None or not getattr(selected_provider, "supports_streaming", False):
                raise HTTPException(
                    status_code=status.HTTP_501_NOT_IMPLEMENTED,
                    detail="Streaming is not supported for the selected route.",
                )
            response_id = request_log_id.replace("req_", "chatcmpl_")

            async def event_stream():
                started_at = perf_counter()
                aggregated_content = ""
                aggregated_tool_calls: list[dict[str, object]] = []
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
                    async for chunk, resolved_decision in _stream_with_fallback(settings, provider_registry, selected_route, request):
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
                        chunk_tool_calls = chunk.get("tool_calls")
                        if isinstance(chunk_tool_calls, list) and chunk_tool_calls:
                            aggregated_tool_calls = _merge_tool_calls(aggregated_tool_calls, chunk_tool_calls)
                            yield _stream_chunk_bytes(
                                response_id=response_id,
                                model=provider_model,
                                delta={"tool_calls": chunk_tool_calls},
                                finish_reason=None,
                            )
                        prompt_tokens = max(prompt_tokens, int(chunk.get("input_tokens", 0)))
                        completion_tokens = max(completion_tokens, int(chunk.get("output_tokens", 0)))
                        if chunk.get("finish_reason"):
                            finish_reason = str(chunk["finish_reason"])
                    provider_name = resolved_decision.selected_provider
                    selected_provider = _provider_for_route(
                        settings=settings,
                        provider_registry=provider_registry,
                        selected_route=selected_route,
                        provider_key=provider_name,
                    )
                    price_per_token = getattr(selected_provider, "price_per_token", 0.0)
                    provider_result = {
                        "model": provider_model,
                        "content": aggregated_content,
                        "tool_calls": aggregated_tool_calls or None,
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
                    await _record_principal_usage_async(
                        session,
                        principal=principal,
                        cost_usd=float(provider_result["cost_estimate"]),
                    )
                    for shadow_provider_key in selected_route.shadow_provider_keys:
                        shadow_provider = _provider_for_route(
                            settings=settings,
                            provider_registry=provider_registry,
                            selected_route=selected_route,
                            provider_key=shadow_provider_key,
                        )
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
        if settings.llmproxy_response_cache_enabled:
            cache_key_value = response_cache_key(
                _cache_payload_for_request(
                    request,
                    provider_key=selected_route.provider_key,
                    model_id=str(selected_route.decision.selected_model),
                )
            )
            cache_hit_result = get_cached_response(cache_key_value)
        if cache_hit_result is not None:
            provider_result = dict(cache_hit_result)
            resolved_decision = selected_route.decision
        else:
            provider_result, resolved_decision = await _invoke_with_fallback(settings, provider_registry, selected_route, request)
            if settings.llmproxy_response_cache_enabled and cache_key_value is not None:
                put_cached_response(
                    cache_key_value,
                    provider_result,
                    ttl_seconds=settings.llmproxy_response_cache_ttl_seconds,
                )
        await _persist_selected_response_async(
            session,
            request=request,
            request_id=request_log_id,
            request_created_at=request_created_at,
            classification=classification,
            provider_result=provider_result,
            resolved_decision=resolved_decision,
        )
        await _record_principal_usage_async(
            session,
            principal=principal,
            cost_usd=float(provider_result["cost_estimate"]),
        )
        for shadow_provider_key in selected_route.shadow_provider_keys:
            shadow_provider = _provider_for_route(
                settings=settings,
                provider_registry=provider_registry,
                selected_route=selected_route,
                provider_key=shadow_provider_key,
            )
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
            prompt_tokens=int(provider_result.get("input_tokens", 0)),
            completion_tokens=int(provider_result.get("output_tokens", 0)),
            finish_reason=str(provider_result.get("finish_reason", "stop")),
            tool_calls=provider_result.get("tool_calls") if isinstance(provider_result.get("tool_calls"), list) else None,
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


@router.get("/v1/models", response_model=list[ModelInfo])
def list_models(
    settings: Settings = Depends(get_runtime_settings),
    principal: AuthPrincipal = Depends(require_api_token),
) -> list[ModelInfo]:
    allowed_models = set(principal.models_allowed) if principal.models_allowed else None
    return [ModelInfo.model_validate(item) for item in list_proxy_models(settings, allowed_models=allowed_models)]


@router.post("/v1/embeddings", response_model=EmbeddingResponse)
async def embeddings(
    request: EmbeddingRequest,
    settings: Settings = Depends(get_runtime_settings),
    principal: AuthPrincipal = Depends(require_api_token),
) -> EmbeddingResponse:
    enforce_budget(principal)
    enforce_model_access(principal, request.model)
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
