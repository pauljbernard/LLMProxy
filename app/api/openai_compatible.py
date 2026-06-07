"""OpenAI-compatible endpoints."""

import asyncio
import json
from time import time
from time import perf_counter

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.db.session import get_async_session_factory
from app.api.dependencies import get_async_session, get_runtime_settings, get_session, require_api_token, require_operator_token
from app.api.dependencies import (
    AuthPrincipal,
    enforce_budget,
    enforce_model_access,
    enforce_rate_limits,
    record_virtual_key_usage,
    release_rate_limit_token_reservation,
)
from app.api.virtual_keys import (
    VirtualKeyCreateRequest,
    VirtualKeyCreateResponse,
    VirtualKeyRotateResponse,
    VirtualKeyUpdateRequest,
    VirtualKeyView,
    create_virtual_key_record,
    disable_virtual_key_record,
    list_virtual_key_records,
    rotate_virtual_key_record,
    update_virtual_key_record,
    virtual_key_payload,
)
from app.config import Settings
from app.integration.performance import sample_performance
from app.proxy.candidates import capture_training_candidate
from app.proxy.classifier import classify_request
from app.proxy.router import select_route
from app.proxy.recorder import record_model_response, record_request, record_routing_decision
from app.registry.model_registry import get_provider_registry, list_proxy_models, resolve_provider
from app.services.cost import estimate_cost_usd
from app.services.cost import pricing_catalog
from app.services.guardrails import GuardrailContext, run_post_guardrails, run_pre_guardrails
from app.services.observability import log_record
from app.services.mcp_gateway import (
    prepare_mcp_request,
    request_has_mcp_tools,
    request_requires_tools,
)
from app.services.prompt_templates import PromptTemplateError, render_prompt_template
from app.services.provider_health import (
    is_provider_cooled_down,
    record_provider_failure,
    record_provider_success,
)
from app.services.response_cache import cache_key as response_cache_key, get_cached_response, put_cached_response
from app.services.response_cache import (
    get_semantic_cached_response,
    put_semantic_cached_response,
    semantic_namespace,
)
from app.services.telemetry import (
    observe_cache_event,
    observe_provider_attempt,
    observe_request,
    set_span_attributes,
    start_span,
)
from app.schemas.chat import (
    ChatMessage,
    ChatCompletionRequest,
    ChatCompletionResponse,
    CompletionChoice,
    CompletionRequest,
    CompletionResponse,
    EmbeddingRequest,
    EmbeddingResponse,
    EmbeddingUsage,
    EmbeddingVector,
    ImageData,
    ImageGenerationRequest,
    ImageGenerationResponse,
    ModelInfo,
    ModerationCategoryScores,
    ModerationRequest,
    ModerationResponse,
    ModerationResult,
    SpeechRequest,
)

router = APIRouter(tags=["openai-compatible"])


@router.get("/v1/keys", response_model=list[VirtualKeyView])
def list_keys(
    session: Session = Depends(get_session),
    _principal: AuthPrincipal = Depends(require_operator_token),
) -> list[VirtualKeyView]:
    rows = list_virtual_key_records(session)
    return [VirtualKeyView.model_validate(virtual_key_payload(item)) for item in rows]


@router.post("/v1/keys/generate", response_model=VirtualKeyCreateResponse)
def generate_key(
    request: VirtualKeyCreateRequest,
    session: Session = Depends(get_session),
    _principal: AuthPrincipal = Depends(require_operator_token),
) -> VirtualKeyCreateResponse:
    record, raw_token = create_virtual_key_record(session, request)
    payload = virtual_key_payload(record)
    payload["token"] = raw_token
    return VirtualKeyCreateResponse.model_validate(payload)


@router.patch("/v1/keys/{key_id}", response_model=VirtualKeyView)
def update_key(
    key_id: str,
    request: VirtualKeyUpdateRequest,
    session: Session = Depends(get_session),
    _principal: AuthPrincipal = Depends(require_operator_token),
) -> VirtualKeyView:
    record = update_virtual_key_record(session, key_id, request)
    return VirtualKeyView.model_validate(virtual_key_payload(record))


@router.post("/v1/keys/{key_id}/rotate", response_model=VirtualKeyRotateResponse)
def rotate_key(
    key_id: str,
    session: Session = Depends(get_session),
    _principal: AuthPrincipal = Depends(require_operator_token),
) -> VirtualKeyRotateResponse:
    record, raw_token, previous_key_prefix = rotate_virtual_key_record(session, key_id)
    payload = virtual_key_payload(record)
    payload["token"] = raw_token
    payload["previous_key_prefix"] = previous_key_prefix
    return VirtualKeyRotateResponse.model_validate(payload)


@router.delete("/v1/keys/{key_id}", response_model=VirtualKeyView)
def delete_key(
    key_id: str,
    session: Session = Depends(get_session),
    _principal: AuthPrincipal = Depends(require_operator_token),
) -> VirtualKeyView:
    record = disable_virtual_key_record(session, key_id)
    return VirtualKeyView.model_validate(virtual_key_payload(record))


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


def _completion_stream_chunk_bytes(*, response_id: str, model: str, text: str, finish_reason: str | None) -> bytes:
    payload = {
        "id": response_id,
        "object": "text_completion",
        "created": int(time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "text": text,
                "logprobs": None,
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


def _estimate_chat_request_tokens(request: ChatCompletionRequest) -> int:
    return _message_token_estimate(request.messages) + int(request.max_tokens or 0)


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


def _provider_supports_request(request: ChatCompletionRequest, provider) -> bool:
    if request_requires_tools(request) and not getattr(provider, "supports_tools", False):
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


def _cache_control_flags(value: str | None) -> tuple[bool, bool]:
    if not value:
        return (False, False)
    directives = {item.strip().lower() for item in value.split(",") if item.strip()}
    no_cache = "no-cache" in directives
    no_store = "no-store" in directives
    return (no_cache, no_store)


def _apply_prompt_template_to_chat_request(
    session: Session,
    request: ChatCompletionRequest,
) -> tuple[ChatCompletionRequest, dict[str, object] | None]:
    metadata = request.metadata
    if not metadata.prompt_template_name:
        return request, None
    try:
        record, rendered = render_prompt_template(
            session,
            name=metadata.prompt_template_name,
            version=metadata.prompt_template_version,
            variables=metadata.prompt_template_variables,
        )
    except PromptTemplateError as exc:
        status_code = status.HTTP_404_NOT_FOUND if "not found" in str(exc).lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    effective_request = request.model_copy(deep=True)
    effective_request.messages = [ChatMessage(role="system", content=rendered), *effective_request.messages]
    if record.model_override:
        effective_request.model = record.model_override
    return effective_request, {
        "name": record.name,
        "version": record.version,
        "rendered_text": rendered,
        "model_override": record.model_override,
    }


def _chat_request_from_completion(
    request: CompletionRequest,
) -> ChatCompletionRequest:
    messages = []
    if request.prompt_template_name:
        messages.append(ChatMessage(role="user", content=request.prompt or ""))
    else:
        messages.append(ChatMessage(role="user", content=request.prompt))
    return ChatCompletionRequest(
        model=request.model,
        messages=messages,
        stream=request.stream,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        top_p=request.top_p,
        n=request.n,
        stop=request.stop,
        presence_penalty=request.presence_penalty,
        frequency_penalty=request.frequency_penalty,
        seed=request.seed,
        logit_bias=request.logit_bias,
        user=request.user,
        timeout_seconds=request.timeout_seconds,
        metadata={
            "prompt_template_name": request.prompt_template_name,
            "prompt_template_version": request.prompt_template_version,
            "prompt_template_variables": request.prompt_template_variables,
        },
    )


def _request_supports_semantic_cache(request: ChatCompletionRequest) -> bool:
    if request.stream:
        return False
    if request.response_format is not None:
        return False
    if request.tools or request.functions:
        return False
    for message in request.messages:
        if not isinstance(message.content, str):
            return False
    return True


def _semantic_text_for_request(request: ChatCompletionRequest) -> str:
    parts: list[str] = []
    for message in request.messages:
        if isinstance(message.content, str):
            parts.append(f"{message.role}: {message.content}")
    return "\n".join(parts).strip()


async def _semantic_embedding_for_request(
    *,
    settings: Settings,
    provider_registry: dict[str, object],
    request: ChatCompletionRequest,
) -> list[float] | None:
    semantic_text = _semantic_text_for_request(request)
    if not semantic_text:
        return None
    embedding_request = EmbeddingRequest(
        model=settings.llmproxy_semantic_cache_embedding_model,
        input=semantic_text,
    )
    try:
        provider = _select_embedding_provider(
            request=embedding_request,
            settings=settings,
            provider_registry=provider_registry,
        )
        vectors = await provider.embed([semantic_text], model=embedding_request.model)
    except Exception:
        return None
    if not vectors:
        return None
    return [float(value) for value in vectors[0]]


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


def _select_openai_aux_provider(*, settings: Settings, provider_registry: dict[str, object]):
    provider = provider_registry.get("openai")
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="This endpoint currently requires an OpenAI-compatible provider configured as 'openai'.",
        )
    return provider


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
            shadow_result = {
                "model": shadow_provider.model_id,
                "content": aggregated_content,
                "input_tokens": prompt_tokens,
                "output_tokens": completion_tokens or len(aggregated_content.split()),
                "latency_ms": int((perf_counter() - started_at) * 1000),
                "finish_reason": finish_reason,
                "cost_estimate": estimate_cost_usd(
                    provider_name=shadow_provider.provider_name,
                    model_id=shadow_provider.model_id,
                    input_tokens=prompt_tokens,
                    output_tokens=completion_tokens,
                ),
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
    *,
    mcp_context=None,
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
        if not _provider_supports_request(request, provider):
            raise ValueError("tooling_not_supported")
        if not _request_fits_provider(request, provider):
            context_rejected = True
            raise ValueError("context_window_exceeded")
        if mcp_context is None:
            provider_result = await _invoke_provider_with_retries(
                settings=settings,
                provider_key=selected_route.provider_key,
                provider=provider,
                request=request,
            )
        else:
            provider_result = await mcp_context.execute(
                settings,
                lambda invoke_request: _invoke_provider_with_retries(
                    settings=settings,
                    provider_key=selected_route.provider_key,
                    provider=provider,
                    request=invoke_request,
                ),
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
                if not _provider_supports_request(request, provider):
                    continue
                if not _request_fits_provider(request, provider):
                    context_rejected = True
                    continue
                if mcp_context is None:
                    provider_result = await _invoke_provider_with_retries(
                        settings=settings,
                        provider_key=fallback_key,
                        provider=provider,
                        request=request,
                    )
                else:
                    provider_result = await mcp_context.execute(
                        settings,
                        lambda invoke_request: _invoke_provider_with_retries(
                            settings=settings,
                            provider_key=fallback_key,
                            provider=provider,
                            request=invoke_request,
                        ),
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
        if not _provider_supports_request(request, provider):
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
        started_at = perf_counter()
        try:
            with start_span(
                "llmproxy.provider.invoke",
                attributes={
                    "llmproxy.provider": provider_key,
                    "llmproxy.model": getattr(provider, "model_id", request.model),
                    "llmproxy.stream": False,
                    "llmproxy.attempt": attempt + 1,
                },
            ) as span:
                result = await provider.invoke(request)
                set_span_attributes(
                    span,
                    {
                        "llmproxy.input_tokens": int(result.get("input_tokens", 0)),
                        "llmproxy.output_tokens": int(result.get("output_tokens", 0)),
                    },
                )
            record_provider_success(provider_key)
            observe_provider_attempt(
                provider=provider_key,
                stream=False,
                outcome="success",
                latency_seconds=perf_counter() - started_at,
            )
            return result
        except Exception as exc:
            attempt += 1
            cooled_down = record_provider_failure(
                provider_key,
                allowed_fails=settings.llmproxy_provider_allowed_fails,
                cooldown_seconds=settings.llmproxy_provider_cooldown_seconds,
            )
            observe_provider_attempt(
                provider=provider_key,
                stream=False,
                outcome="failure",
                latency_seconds=perf_counter() - started_at,
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
        started_at = perf_counter()
        try:
            with start_span(
                "llmproxy.provider.stream",
                attributes={
                    "llmproxy.provider": provider_key,
                    "llmproxy.model": getattr(provider, "model_id", request.model),
                    "llmproxy.stream": True,
                    "llmproxy.attempt": attempt + 1,
                },
            ):
                async for chunk in provider.stream_chat(request):
                    started = True
                    yield chunk
            record_provider_success(provider_key)
            observe_provider_attempt(
                provider=provider_key,
                stream=True,
                outcome="success",
                latency_seconds=perf_counter() - started_at,
            )
            return
        except Exception:
            cooled_down = record_provider_failure(
                provider_key,
                allowed_fails=settings.llmproxy_provider_allowed_fails,
                cooldown_seconds=settings.llmproxy_provider_cooldown_seconds,
            )
            observe_provider_attempt(
                provider=provider_key,
                stream=True,
                outcome="failure",
                latency_seconds=perf_counter() - started_at,
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
    cache_control: str | None = Header(default=None, alias="Cache-Control"),
    session: AsyncSession = Depends(get_async_session),
    rate_limit_session: Session = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
    principal: AuthPrincipal = Depends(require_api_token),
) -> ChatCompletionResponse | StreamingResponse:
    request_log_id = None
    reserved_tokens = 0
    request_started_at = perf_counter()
    selected_provider_label = "unknown"
    effective_request = request
    with start_span(
        "llmproxy.chat.completions",
        attributes={
            "llmproxy.requested_model": request.model,
            "llmproxy.stream": request.stream,
        },
    ) as request_span:
        effective_request, template_context = _apply_prompt_template_to_chat_request(rate_limit_session, request)
        if template_context is not None:
            set_span_attributes(
                request_span,
                {
                    "llmproxy.prompt_template_name": template_context["name"],
                    "llmproxy.prompt_template_version": template_context["version"],
                },
            )
        enforce_budget(principal)
        enforce_model_access(principal, effective_request.model)
        reserved_tokens = _estimate_chat_request_tokens(effective_request)
        enforce_rate_limits(rate_limit_session, principal, estimated_tokens=reserved_tokens)
        classification = classify_request(effective_request)
        set_span_attributes(
            request_span,
            {
                "llmproxy.domain": classification["domain"],
                "llmproxy.task_type": classification["task_type"],
                "llmproxy.privacy_level": classification["privacy_level"],
                "llmproxy.auth_role": principal.role,
                "llmproxy.effective_model": effective_request.model,
            },
        )
        guardrail_context = GuardrailContext(
            settings=settings,
            request=effective_request,
            classification=classification,
            principal=principal,
        )
        await run_pre_guardrails(guardrail_context)
        mcp_context = await prepare_mcp_request(effective_request, settings)
        effective_request = mcp_context.request if mcp_context is not None else effective_request
        try:
            bypass_cache, suppress_cache_store = _cache_control_flags(cache_control)
            request_log_id, request_created_at = await _record_request_async(
                session,
                request=effective_request,
                classification=classification,
            )
            selected_route, provider_registry = await _resolve_route_and_registry(
                session,
                request_id=request_log_id,
                request=effective_request,
                classification=classification,
                settings=settings,
            )
            selected_provider_label = selected_route.provider_key
            set_span_attributes(
                request_span,
                {
                    "llmproxy.route_provider": selected_route.provider_key,
                    "llmproxy.route_model": selected_route.decision.selected_model,
                    "llmproxy.route_mode": selected_route.decision.selected_mode,
                },
            )
            if request.stream and mcp_context is not None:
                provider_result, resolved_decision = await _invoke_with_fallback(
                    settings,
                    provider_registry,
                    selected_route,
                    effective_request,
                    mcp_context=mcp_context,
                )
                selected_provider_label = str(provider_result.get("provider", selected_provider_label))
                guardrail_context.provider_result = provider_result
                await run_post_guardrails(guardrail_context)
                await _persist_selected_response_async(
                        session,
                        request=effective_request,
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
                record_virtual_key_usage(
                    rate_limit_session,
                    principal,
                    cost_usd=float(provider_result["cost_estimate"]),
                    reserved_tokens=reserved_tokens,
                    actual_tokens=int(provider_result.get("input_tokens", 0)) + int(provider_result.get("output_tokens", 0)),
                )
                await session.commit()
                observe_request(
                    endpoint="/v1/chat/completions",
                    provider=selected_provider_label,
                    stream=True,
                    status="ok",
                    latency_seconds=perf_counter() - request_started_at,
                )
                response_id = request_log_id.replace("req_", "chatcmpl_")

                async def buffered_event_stream():
                    yield _stream_chunk_bytes(
                        response_id=response_id,
                        model=str(provider_result["model"]),
                        delta={"role": "assistant"},
                        finish_reason=None,
                    )
                    content = str(provider_result.get("content", ""))
                    if content:
                        yield _stream_chunk_bytes(
                            response_id=response_id,
                            model=str(provider_result["model"]),
                            delta={"content": content},
                            finish_reason=None,
                        )
                    yield _stream_chunk_bytes(
                        response_id=response_id,
                        model=str(provider_result["model"]),
                        delta={},
                        finish_reason=str(provider_result.get("finish_reason", "stop")),
                    )
                    yield b"data: [DONE]\n\n"

                return StreamingResponse(buffered_event_stream(), media_type="text/event-stream")
            cache_hit_result = None
            cache_key_value = None
            semantic_embedding = None
            semantic_namespace_value = None
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
                        provider_result = {
                            "model": provider_model,
                            "content": aggregated_content,
                            "tool_calls": aggregated_tool_calls or None,
                            "input_tokens": prompt_tokens,
                            "output_tokens": completion_tokens,
                            "latency_ms": int((perf_counter() - started_at) * 1000),
                            "finish_reason": finish_reason,
                            "cost_estimate": estimate_cost_usd(
                                provider_name=provider_name,
                                model_id=provider_model,
                                input_tokens=prompt_tokens,
                                output_tokens=completion_tokens,
                            ),
                            "raw_response": {"streamed": True},
                            "provider": provider_name,
                            "provider_family": resolved_decision.selected_provider_family,
                        }
                        guardrail_context.provider_result = provider_result
                        await run_post_guardrails(guardrail_context)
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
                        record_virtual_key_usage(
                            rate_limit_session,
                            principal,
                            cost_usd=float(provider_result["cost_estimate"]),
                            reserved_tokens=reserved_tokens,
                            actual_tokens=int(provider_result.get("input_tokens", 0)) + int(provider_result.get("output_tokens", 0)),
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
                                    request=effective_request,
                                    request_log_id=request_log_id,
                                    classification=classification,
                                    settings=settings,
                                )
                            )
                        await session.commit()
                        observe_request(
                            endpoint="/v1/chat/completions",
                            provider=str(provider_result["provider"]),
                            stream=True,
                            status="ok",
                            latency_seconds=perf_counter() - request_started_at,
                        )
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
                        release_rate_limit_token_reservation(rate_limit_session, principal, reserved_tokens=reserved_tokens)
                        await session.rollback()
                        observe_request(
                            endpoint="/v1/chat/completions",
                            provider=selected_provider_label,
                            stream=True,
                            status="cancelled",
                            latency_seconds=perf_counter() - request_started_at,
                        )
                        raise
                    except Exception as exc:
                        release_rate_limit_token_reservation(rate_limit_session, principal, reserved_tokens=reserved_tokens)
                        await session.rollback()
                        observe_request(
                            endpoint="/v1/chat/completions",
                            provider=selected_provider_label,
                            stream=True,
                            status="error",
                            latency_seconds=perf_counter() - request_started_at,
                        )
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

            semantic_cache_enabled = settings.llmproxy_semantic_cache_enabled and _request_supports_semantic_cache(request)
            if settings.llmproxy_response_cache_enabled and not suppress_cache_store:
                cache_key_value = response_cache_key(
                    _cache_payload_for_request(
                        effective_request,
                        provider_key=selected_route.provider_key,
                        model_id=str(selected_route.decision.selected_model),
                    )
                )
                if not bypass_cache:
                    cache_hit_result = get_cached_response(cache_key_value)
                    observe_cache_event(cache="exact", outcome="hit" if cache_hit_result is not None else "miss")
                    if cache_hit_result is None and semantic_cache_enabled and not request_has_mcp_tools(request):
                        semantic_embedding = await _semantic_embedding_for_request(
                            settings=settings,
                            provider_registry=provider_registry,
                            request=effective_request,
                        )
                        if semantic_embedding is not None:
                            semantic_namespace_value = semantic_namespace(
                                provider_key=selected_route.provider_key,
                                model_id=str(selected_route.decision.selected_model),
                                requested_model=request.model,
                            )
                            cache_hit_result = get_semantic_cached_response(
                                semantic_namespace_value,
                                semantic_embedding,
                                min_similarity=settings.llmproxy_semantic_cache_similarity_threshold,
                                max_candidates=settings.llmproxy_semantic_cache_max_candidates,
                            )
                            observe_cache_event(cache="semantic", outcome="hit" if cache_hit_result is not None else "miss")
            if cache_hit_result is not None and not request_has_mcp_tools(request):
                provider_result = dict(cache_hit_result)
                resolved_decision = selected_route.decision
            else:
                provider_result, resolved_decision = await _invoke_with_fallback(
                    settings,
                    provider_registry,
                    selected_route,
                    effective_request,
                    mcp_context=mcp_context,
                )
                selected_provider_label = str(provider_result.get("provider", selected_provider_label))
                if (
                    settings.llmproxy_response_cache_enabled
                    and not suppress_cache_store
                    and cache_key_value is not None
                    and not request_has_mcp_tools(request)
                ):
                    put_cached_response(
                        cache_key_value,
                        provider_result,
                        ttl_seconds=settings.llmproxy_response_cache_ttl_seconds,
                    )
                    if semantic_cache_enabled and not request_has_mcp_tools(request):
                        if semantic_embedding is None:
                            semantic_embedding = await _semantic_embedding_for_request(
                                settings=settings,
                                provider_registry=provider_registry,
                                request=effective_request,
                            )
                        if semantic_embedding is not None:
                            if semantic_namespace_value is None:
                                semantic_namespace_value = semantic_namespace(
                                    provider_key=selected_route.provider_key,
                                    model_id=str(selected_route.decision.selected_model),
                                    requested_model=request.model,
                                )
                            put_semantic_cached_response(
                                semantic_namespace_value,
                                semantic_embedding,
                                provider_result,
                                ttl_seconds=settings.llmproxy_response_cache_ttl_seconds,
                            )
                guardrail_context.provider_result = provider_result
                await run_post_guardrails(guardrail_context)
                await _persist_selected_response_async(
                    session,
                    request=effective_request,
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
            record_virtual_key_usage(
                rate_limit_session,
                principal,
                cost_usd=float(provider_result["cost_estimate"]),
                reserved_tokens=reserved_tokens,
                actual_tokens=int(provider_result.get("input_tokens", 0)) + int(provider_result.get("output_tokens", 0)),
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
                        request=effective_request,
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
            response = ChatCompletionResponse.from_request(
                effective_request,
                content=str(provider_result["content"]),
                response_id=request_log_id.replace("req_", "chatcmpl_"),
                resolved_model=str(provider_result["model"]),
                prompt_tokens=int(provider_result.get("input_tokens", 0)),
                completion_tokens=int(provider_result.get("output_tokens", 0)),
                finish_reason=str(provider_result.get("finish_reason", "stop")),
                tool_calls=provider_result.get("tool_calls") if isinstance(provider_result.get("tool_calls"), list) else None,
            )
            observe_request(
                endpoint="/v1/chat/completions",
                provider=str(provider_result.get("provider", selected_provider_label)),
                stream=False,
                status="ok",
                latency_seconds=perf_counter() - request_started_at,
            )
            return Response(
                content=response.model_dump_json(),
                media_type="application/json",
                headers={
                    "X-LLMProxy-Cost-Usd": str(provider_result["cost_estimate"]),
                    "X-LLMProxy-Input-Tokens": str(provider_result.get("input_tokens", 0)),
                    "X-LLMProxy-Output-Tokens": str(provider_result.get("output_tokens", 0)),
                    "X-LLMProxy-Provider": str(provider_result.get("provider", "")),
                    "X-LLMProxy-Model": str(provider_result.get("model", "")),
                },
            )
        except HTTPException as exc:
            release_rate_limit_token_reservation(rate_limit_session, principal, reserved_tokens=reserved_tokens)
            observe_request(
                endpoint="/v1/chat/completions",
                provider=selected_provider_label,
                stream=request.stream,
                status=f"http_{exc.status_code}",
                latency_seconds=perf_counter() - request_started_at,
            )
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
            release_rate_limit_token_reservation(rate_limit_session, principal, reserved_tokens=reserved_tokens)
            await session.rollback()
            observe_request(
                endpoint="/v1/chat/completions",
                provider=selected_provider_label,
                stream=request.stream,
                status="error",
                latency_seconds=perf_counter() - request_started_at,
            )
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


@router.post("/v1/completions", response_model=CompletionResponse)
async def completions(
    request: CompletionRequest,
    session: AsyncSession = Depends(get_async_session),
    rate_limit_session: Session = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
    principal: AuthPrincipal = Depends(require_api_token),
) -> CompletionResponse | StreamingResponse:
    translated_request = _chat_request_from_completion(request)
    response = await chat_completions(
        translated_request,
        session=session,
        rate_limit_session=rate_limit_session,
        settings=settings,
        principal=principal,
    )
    if isinstance(response, StreamingResponse):
        async def completion_event_stream():
            async for chunk_bytes in response.body_iterator:
                if not isinstance(chunk_bytes, (bytes, bytearray)):
                    continue
                text = bytes(chunk_bytes).decode("utf-8")
                for event in text.split("\n\n"):
                    event = event.strip()
                    if not event or not event.startswith("data: "):
                        continue
                    payload_text = event[6:].strip()
                    if payload_text == "[DONE]":
                        yield b"data: [DONE]\n\n"
                        continue
                    try:
                        raw_chunk = json.loads(payload_text)
                    except json.JSONDecodeError:
                        continue
                    chunk_model = str(raw_chunk.get("model", request.model))
                    choice = (raw_chunk.get("choices") or [{}])[0]
                    delta = choice.get("delta") or {}
                    yield _completion_stream_chunk_bytes(
                        response_id=str(raw_chunk.get("id", "cmpl_generated")),
                        model=chunk_model,
                        text=str(delta.get("content", "")),
                        finish_reason=choice.get("finish_reason"),
                    )

        return StreamingResponse(completion_event_stream(), media_type="text/event-stream")
    choice = response.choices[0]
    return CompletionResponse(
        id=response.id,
        created=response.created,
        model=response.model,
        choices=[
            CompletionChoice(
                text=choice.message.content or "",
                index=choice.index,
                finish_reason=choice.finish_reason,
            )
        ],
        usage=response.usage,
    )


@router.get("/v1/models", response_model=list[ModelInfo])
def list_models(
    settings: Settings = Depends(get_runtime_settings),
    principal: AuthPrincipal = Depends(require_api_token),
) -> list[ModelInfo]:
    allowed_models = set(principal.models_allowed) if principal.models_allowed else None
    return [ModelInfo.model_validate(item) for item in list_proxy_models(settings, allowed_models=allowed_models)]


@router.get("/v1/pricing")
def list_pricing(
    _principal: AuthPrincipal = Depends(require_api_token),
) -> list[dict[str, float | str]]:
    return pricing_catalog()


@router.post("/v1/embeddings", response_model=EmbeddingResponse)
async def embeddings(
    request: EmbeddingRequest,
    rate_limit_session: Session = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
    principal: AuthPrincipal = Depends(require_api_token),
) -> EmbeddingResponse:
    enforce_budget(principal)
    enforce_model_access(principal, request.model)
    inputs = _normalize_embedding_inputs(request)
    reserved_tokens = sum(len(text.split()) for text in inputs)
    enforce_rate_limits(rate_limit_session, principal, estimated_tokens=reserved_tokens)
    provider_registry = get_provider_registry(settings)
    provider = _select_embedding_provider(
        request=request,
        settings=settings,
        provider_registry=provider_registry,
    )
    try:
        vectors = await provider.embed(inputs, model=request.model, dimensions=request.dimensions)
    except NotImplementedError as exc:
        release_rate_limit_token_reservation(rate_limit_session, principal, reserved_tokens=reserved_tokens)
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc)) from exc
    except Exception:
        release_rate_limit_token_reservation(rate_limit_session, principal, reserved_tokens=reserved_tokens)
        raise
    data = [
        EmbeddingVector(index=index, embedding=vector)
        for index, vector in enumerate(vectors)
    ]
    prompt_tokens = sum(len(text.split()) for text in inputs)
    record_virtual_key_usage(
        rate_limit_session,
        principal,
        cost_usd=0.0,
        reserved_tokens=reserved_tokens,
        actual_tokens=prompt_tokens,
    )
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


@router.post("/v1/images/generations", response_model=ImageGenerationResponse)
async def image_generations(
    request: ImageGenerationRequest,
    rate_limit_session: Session = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
    principal: AuthPrincipal = Depends(require_api_token),
) -> ImageGenerationResponse:
    resolved_model = request.model or settings.llmproxy_openai_image_model
    enforce_budget(principal)
    enforce_model_access(principal, resolved_model)
    enforce_rate_limits(rate_limit_session, principal, estimated_tokens=0)
    provider = _select_openai_aux_provider(
        settings=settings,
        provider_registry=get_provider_registry(settings),
    )
    try:
        raw_response = await provider.generate_image(
            {
                "model": resolved_model,
                "prompt": request.prompt,
                "n": request.n,
                "size": request.size,
                "response_format": request.response_format,
                "user": request.user,
            }
        )
    except Exception:
        release_rate_limit_token_reservation(rate_limit_session, principal, reserved_tokens=0)
        raise
    record_virtual_key_usage(rate_limit_session, principal, cost_usd=0.0, reserved_tokens=0, actual_tokens=0)
    return ImageGenerationResponse(
        created=int(raw_response.get("created", int(time()))),
        data=[ImageData.model_validate(item) for item in raw_response.get("data", [])],
    )


@router.post("/v1/audio/transcriptions", response_model=dict[str, object])
async def audio_transcriptions(
    file: UploadFile = File(...),
    model: str | None = Form(default=None),
    language: str | None = Form(default=None),
    prompt: str | None = Form(default=None),
    response_format: str | None = Form(default="json"),
    temperature: float | None = Form(default=None),
    rate_limit_session: Session = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
    principal: AuthPrincipal = Depends(require_api_token),
) -> dict[str, object]:
    resolved_model = model or settings.llmproxy_openai_transcription_model
    enforce_budget(principal)
    enforce_model_access(principal, resolved_model)
    enforce_rate_limits(rate_limit_session, principal, estimated_tokens=0)
    provider = _select_openai_aux_provider(
        settings=settings,
        provider_registry=get_provider_registry(settings),
    )
    try:
        result = await provider.transcribe(
            file_bytes=await file.read(),
            filename=file.filename or "audio",
            model=resolved_model,
            language=language,
            prompt=prompt,
            response_format=response_format,
            temperature=temperature,
        )
    except Exception:
        release_rate_limit_token_reservation(rate_limit_session, principal, reserved_tokens=0)
        raise
    record_virtual_key_usage(rate_limit_session, principal, cost_usd=0.0, reserved_tokens=0, actual_tokens=0)
    return result


@router.post("/v1/audio/speech", response_model=None)
async def audio_speech(
    request: SpeechRequest,
    rate_limit_session: Session = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
    principal: AuthPrincipal = Depends(require_api_token),
) -> Response:
    resolved_model = request.model or settings.llmproxy_openai_speech_model
    enforce_budget(principal)
    enforce_model_access(principal, resolved_model)
    enforce_rate_limits(rate_limit_session, principal, estimated_tokens=0)
    provider = _select_openai_aux_provider(
        settings=settings,
        provider_registry=get_provider_registry(settings),
    )
    try:
        content, media_type = await provider.synthesize_speech(
            {
                "model": resolved_model,
                "input": request.input,
                "voice": request.voice,
                "response_format": request.response_format,
                "speed": request.speed,
            }
        )
    except Exception:
        release_rate_limit_token_reservation(rate_limit_session, principal, reserved_tokens=0)
        raise
    record_virtual_key_usage(rate_limit_session, principal, cost_usd=0.0, reserved_tokens=0, actual_tokens=0)
    return Response(content=content, media_type=media_type)


@router.post("/v1/moderations", response_model=ModerationResponse)
async def moderations(
    request: ModerationRequest,
    rate_limit_session: Session = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
    principal: AuthPrincipal = Depends(require_api_token),
) -> ModerationResponse:
    resolved_model = request.model or settings.llmproxy_openai_moderation_model
    enforce_budget(principal)
    enforce_model_access(principal, resolved_model)
    enforce_rate_limits(rate_limit_session, principal, estimated_tokens=0)
    provider = _select_openai_aux_provider(
        settings=settings,
        provider_registry=get_provider_registry(settings),
    )
    try:
        raw_response = await provider.moderate(
            {
                "model": resolved_model,
                "input": request.input,
            }
        )
    except Exception:
        release_rate_limit_token_reservation(rate_limit_session, principal, reserved_tokens=0)
        raise
    record_virtual_key_usage(rate_limit_session, principal, cost_usd=0.0, reserved_tokens=0, actual_tokens=0)
    return ModerationResponse(
        id=str(raw_response.get("id", "mod_generated")),
        model=str(raw_response.get("model", resolved_model)),
        results=[
            ModerationResult(
                flagged=bool(item.get("flagged", False)),
                categories={str(key): bool(value) for key, value in dict(item.get("categories", {})).items()},
                category_scores=ModerationCategoryScores(
                    values={str(key): float(value) for key, value in dict(item.get("category_scores", {})).items()}
                ),
            )
            for item in raw_response.get("results", [])
        ],
    )
