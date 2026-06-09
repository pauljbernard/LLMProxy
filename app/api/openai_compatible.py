"""OpenAI-compatible endpoints."""

import asyncio
import hashlib
import json
from time import time
from time import perf_counter

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.db.session import get_async_session_factory
from app.api.dependencies import get_async_session, get_runtime_settings, get_session, require_api_token, require_operator_token, require_platform_listener, require_proxy_listener
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
from app.proxy.router import RESERVED_ROUTE_MODELS, select_route
from app.proxy.recorder import record_model_response, record_request, record_routing_decision
from app.registry.model_registry import get_provider_registry, list_provider_capabilities_async, list_proxy_models_async, resolve_provider
from app.services.cost import estimate_cost_breakdown_usd, estimate_cost_usd
from app.services.cost import pricing_catalog
from app.services.guardrails import GuardrailContext, run_post_guardrails, run_pre_guardrails
from app.services.learning_pipeline import enrich_request_for_principal
from app.services.interaction_traces import build_llm_interaction_trace, extract_mcp_interaction_traces
from app.services.observability import log_record
from app.services.mcp_gateway import (
    prepare_mcp_request,
    request_has_mcp_tools,
    request_requires_tools,
)
from app.services.prompt_templates import (
    PromptTemplateError,
    render_template_text,
    resolve_runtime_prompt_template,
)
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
    AnthropicCountTokensResponse,
    AnthropicMessagesRequest,
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
    _listener: dict[str, object] = Depends(require_platform_listener),
    _principal: AuthPrincipal = Depends(require_operator_token),
) -> list[VirtualKeyView]:
    rows = list_virtual_key_records(session)
    return [VirtualKeyView.model_validate(virtual_key_payload(item)) for item in rows]


@router.post("/v1/keys/generate", response_model=VirtualKeyCreateResponse)
def generate_key(
    request: VirtualKeyCreateRequest,
    session: Session = Depends(get_session),
    _listener: dict[str, object] = Depends(require_platform_listener),
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
    _listener: dict[str, object] = Depends(require_platform_listener),
    _principal: AuthPrincipal = Depends(require_operator_token),
) -> VirtualKeyView:
    record = update_virtual_key_record(session, key_id, request)
    return VirtualKeyView.model_validate(virtual_key_payload(record))


@router.post("/v1/keys/{key_id}/rotate", response_model=VirtualKeyRotateResponse)
def rotate_key(
    key_id: str,
    session: Session = Depends(get_session),
    _listener: dict[str, object] = Depends(require_platform_listener),
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
    _listener: dict[str, object] = Depends(require_platform_listener),
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


def _stream_error_bytes(*, message: str, status_code: int | None = None, error_type: str = "stream_error") -> bytes:
    payload: dict[str, object] = {
        "error": {
            "message": message,
            "type": error_type,
        }
    }
    if status_code is not None:
        payload["error"]["status_code"] = status_code
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


def _anthropic_text_from_content(content: object) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            parts.append(item["text"])
    return "".join(parts)


def _anthropic_tool_result_content(content: object) -> str:
    if isinstance(content, str):
        return content
    text = _anthropic_text_from_content(content)
    if text:
        return text
    return json.dumps(content if content is not None else "")


def _anthropic_tool_choice_to_openai(choice: object) -> str | dict[str, object] | None:
    if not isinstance(choice, dict):
        return None
    choice_type = str(choice.get("type", "")).strip()
    if choice_type == "auto":
        return "auto"
    if choice_type == "none":
        return "none"
    if choice_type == "any":
        return "required"
    if choice_type == "tool" and isinstance(choice.get("name"), str):
        return {"type": "function", "function": {"name": choice["name"]}}
    return None


def _chat_request_from_anthropic_messages(request: AnthropicMessagesRequest) -> ChatCompletionRequest:
    messages: list[dict[str, object]] = []
    if request.system is not None:
        messages.append({"role": "system", "content": request.system})
    for item in request.messages:
        blocks = item.content if isinstance(item.content, list) else [{"type": "text", "text": item.content}]
        text_parts: list[str] = []
        tool_calls: list[dict[str, object]] = []
        tool_results: list[dict[str, str]] = []
        for block in blocks:
            if not isinstance(block, dict):
                continue
            block_type = str(block.get("type", ""))
            if block_type == "text" and isinstance(block.get("text"), str):
                text_parts.append(block["text"])
                continue
            if item.role == "assistant" and block_type == "tool_use":
                tool_calls.append(
                    {
                        "id": str(block.get("id") or f"toolu_{len(tool_calls)}"),
                        "type": "function",
                        "function": {
                            "name": str(block.get("name") or "tool"),
                            "arguments": json.dumps(block.get("input") or {}),
                        },
                    }
                )
                continue
            if item.role == "user" and block_type == "tool_result":
                tool_results.append(
                    {
                        "tool_call_id": str(block.get("tool_use_id") or ""),
                        "content": _anthropic_tool_result_content(block.get("content")),
                    }
                )
                continue
            if isinstance(block.get("text"), str):
                text_parts.append(block["text"])
        content_value: str | None = "".join(text_parts) if text_parts else None
        if content_value is not None or tool_calls or not tool_results:
            messages.append(
                {
                    "role": item.role,
                    "content": content_value,
                    "tool_calls": tool_calls or None,
                }
            )
        for tool_result in tool_results:
            if tool_result["tool_call_id"]:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_result["tool_call_id"],
                        "content": tool_result["content"],
                    }
                )
    payload: dict[str, object] = {
        "model": request.model,
        "messages": messages,
        "stream": request.stream,
        "temperature": 0.2 if request.temperature is None else request.temperature,
        "max_tokens": request.max_tokens,
    }
    if request.top_p is not None:
        payload["top_p"] = request.top_p
    if request.stop_sequences is not None:
        payload["stop"] = request.stop_sequences
    if request.metadata and request.metadata.user_id:
        payload["user"] = request.metadata.user_id
    metadata_payload: dict[str, object] = {}
    if request.prompt_template_name:
        metadata_payload["prompt_template_name"] = request.prompt_template_name
        metadata_payload["prompt_template_variables"] = request.prompt_template_variables or {}
        if request.prompt_template_version is not None:
            metadata_payload["prompt_template_version"] = request.prompt_template_version
    if metadata_payload:
        payload["metadata"] = metadata_payload
    if request.tools is not None:
        payload["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema or {"type": "object"},
                },
            }
            for tool in request.tools
        ]
    tool_choice = _anthropic_tool_choice_to_openai(request.tool_choice)
    if tool_choice is not None:
        payload["tool_choice"] = tool_choice
    return ChatCompletionRequest.model_validate(payload)


def _anthropic_stop_reason_from_finish_reason(finish_reason: object) -> str:
    value = str(finish_reason or "stop")
    return {
        "stop": "end_turn",
        "length": "max_tokens",
        "tool_calls": "tool_use",
    }.get(value, value)


def _anthropic_content_blocks_from_openai_payload(message: dict[str, object]) -> list[dict[str, object]]:
    blocks: list[dict[str, object]] = []
    content = message.get("content")
    if isinstance(content, str) and content:
        blocks.append({"type": "text", "text": content})
    tool_calls = message.get("tool_calls")
    if isinstance(tool_calls, list):
        for index, item in enumerate(tool_calls):
            if not isinstance(item, dict):
                continue
            function = item.get("function")
            if not isinstance(function, dict):
                continue
            raw_arguments = function.get("arguments")
            if isinstance(raw_arguments, str) and raw_arguments.strip():
                try:
                    arguments = json.loads(raw_arguments)
                except json.JSONDecodeError:
                    arguments = {"raw": raw_arguments}
            elif isinstance(raw_arguments, dict):
                arguments = raw_arguments
            else:
                arguments = {}
            if not isinstance(arguments, dict):
                arguments = {"value": arguments}
            blocks.append(
                {
                    "type": "tool_use",
                    "id": str(item.get("id") or f"toolu_{index}"),
                    "name": str(function.get("name") or "tool"),
                    "input": arguments,
                }
            )
    return blocks or [{"type": "text", "text": ""}]


def _anthropic_message_id(response_id: str) -> str:
    return response_id.replace("chatcmpl_", "msg_")


def _anthropic_messages_response_from_openai_payload(payload: dict[str, object]) -> dict[str, object]:
    choice = (payload.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    usage = payload.get("usage") or {}
    return {
        "id": _anthropic_message_id(str(payload.get("id", "msg_generated"))),
        "type": "message",
        "role": "assistant",
        "model": str(payload.get("model", "")),
        "content": _anthropic_content_blocks_from_openai_payload(message),
        "stop_reason": _anthropic_stop_reason_from_finish_reason(choice.get("finish_reason")),
        "stop_sequence": None,
        "usage": {
            "input_tokens": int(usage.get("prompt_tokens", 0)),
            "output_tokens": int(usage.get("completion_tokens", 0)),
        },
    }


def _anthropic_stream_event_bytes(event_type: str, payload: dict[str, object]) -> bytes:
    return f"event: {event_type}\ndata: {json.dumps(payload)}\n\n".encode("utf-8")


async def _anthropic_stream_from_openai_stream(body_iterator):
    message_started = False
    message_id = "msg_generated"
    model = ""
    next_block_index = 0
    text_block_index: int | None = None
    open_blocks: list[int] = []
    tool_blocks: dict[int, dict[str, object]] = {}
    prompt_tokens = 0
    completion_tokens = 0
    stop_reason = "end_turn"

    async for chunk_bytes in body_iterator:
        if not isinstance(chunk_bytes, (bytes, bytearray)):
            continue
        text = bytes(chunk_bytes).decode("utf-8")
        for event in text.split("\n\n"):
            event = event.strip()
            if not event or not event.startswith("data: "):
                continue
            payload_text = event[6:].strip()
            if payload_text == "[DONE]":
                continue
            try:
                raw_chunk = json.loads(payload_text)
            except json.JSONDecodeError:
                continue
            if isinstance(raw_chunk.get("error"), dict):
                yield _anthropic_stream_event_bytes("error", {"type": "error", "error": raw_chunk["error"]})
                continue
            if not message_started:
                message_id = _anthropic_message_id(str(raw_chunk.get("id", message_id)))
                model = str(raw_chunk.get("model", model))
                yield _anthropic_stream_event_bytes(
                    "message_start",
                    {
                        "type": "message_start",
                        "message": {
                            "id": message_id,
                            "type": "message",
                            "role": "assistant",
                            "model": model,
                            "content": [],
                            "stop_reason": None,
                            "stop_sequence": None,
                            "usage": {"input_tokens": 0, "output_tokens": 0},
                        },
                    },
                )
                message_started = True
            choice = (raw_chunk.get("choices") or [{}])[0]
            delta = choice.get("delta") or {}
            if isinstance(delta.get("content"), str) and delta["content"]:
                if text_block_index is None:
                    text_block_index = next_block_index
                    next_block_index += 1
                    open_blocks.append(text_block_index)
                    yield _anthropic_stream_event_bytes(
                        "content_block_start",
                        {
                            "type": "content_block_start",
                            "index": text_block_index,
                            "content_block": {"type": "text", "text": ""},
                        },
                    )
                yield _anthropic_stream_event_bytes(
                    "content_block_delta",
                    {
                        "type": "content_block_delta",
                        "index": text_block_index,
                        "delta": {"type": "text_delta", "text": delta["content"]},
                    },
                )
            chunk_tool_calls = delta.get("tool_calls")
            if isinstance(chunk_tool_calls, list):
                for position, item in enumerate(chunk_tool_calls):
                    if not isinstance(item, dict):
                        continue
                    tool_index = item.get("index", position)
                    try:
                        tool_index = int(tool_index)
                    except (TypeError, ValueError):
                        tool_index = position
                    block = tool_blocks.get(tool_index)
                    function = item.get("function") if isinstance(item.get("function"), dict) else {}
                    if block is None:
                        block_index = next_block_index
                        next_block_index += 1
                        block = {
                            "block_index": block_index,
                            "id": str(item.get("id") or f"toolu_{tool_index}"),
                            "name": str(function.get("name") or item.get("name") or "tool"),
                            "started": False,
                        }
                        tool_blocks[tool_index] = block
                    if item.get("id"):
                        block["id"] = str(item["id"])
                    if function.get("name"):
                        block["name"] = str(function["name"])
                    if not block["started"]:
                        block["started"] = True
                        open_blocks.append(int(block["block_index"]))
                        yield _anthropic_stream_event_bytes(
                            "content_block_start",
                            {
                                "type": "content_block_start",
                                "index": int(block["block_index"]),
                                "content_block": {
                                    "type": "tool_use",
                                    "id": str(block["id"]),
                                    "name": str(block["name"]),
                                    "input": {},
                                },
                            },
                        )
                    raw_arguments = function.get("arguments")
                    if isinstance(raw_arguments, str) and raw_arguments:
                        yield _anthropic_stream_event_bytes(
                            "content_block_delta",
                            {
                                "type": "content_block_delta",
                                "index": int(block["block_index"]),
                                "delta": {"type": "input_json_delta", "partial_json": raw_arguments},
                            },
                        )
            usage = raw_chunk.get("usage") or {}
            prompt_tokens = max(prompt_tokens, int(usage.get("prompt_tokens", 0)))
            completion_tokens = max(completion_tokens, int(usage.get("completion_tokens", 0)))
            if choice.get("finish_reason"):
                stop_reason = _anthropic_stop_reason_from_finish_reason(choice.get("finish_reason"))
    for block_index in open_blocks:
        yield _anthropic_stream_event_bytes(
            "content_block_stop",
            {
                "type": "content_block_stop",
                "index": block_index,
            },
        )
    if message_started:
        yield _anthropic_stream_event_bytes(
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                "usage": {"input_tokens": prompt_tokens, "output_tokens": completion_tokens},
            },
        )
        yield _anthropic_stream_event_bytes("message_stop", {"type": "message_stop"})


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


def _estimate_anthropic_input_tokens(session: Session, request: AnthropicMessagesRequest) -> int:
    translated = _chat_request_from_anthropic_messages(request)
    effective_request, _ = _apply_prompt_template_to_chat_request(session, translated)
    total = _message_token_estimate(effective_request.messages)
    if request.tools:
        for tool in request.tools:
            total += len(json.dumps(tool.model_dump(mode="json")).split())
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


def _apply_inbound_listener_metadata(
    request: ChatCompletionRequest,
    *,
    http_request: Request,
    settings: Settings,
) -> ChatCompletionRequest:
    enriched = request.model_copy(deep=True)
    observed_host = http_request.url.hostname or ""
    observed_port = http_request.url.port or (443 if http_request.url.scheme == "https" else 80)
    listener = settings.resolve_inbound_listener(
        listener_id=enriched.metadata.listener_id,
        host=observed_host,
        port=observed_port,
    )
    enriched.metadata.listener_id = str(listener.get("listener_id") or "") or None
    enriched.metadata.listener_host = str(listener.get("published_host") or observed_host or "") or None
    try:
        enriched.metadata.listener_port = int(listener.get("published_port") or listener.get("port") or observed_port)
    except (TypeError, ValueError):
        enriched.metadata.listener_port = observed_port
    return enriched


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
        resolution = resolve_runtime_prompt_template(
            session,
            name=metadata.prompt_template_name,
            version=metadata.prompt_template_version,
            selection_key=metadata.root_request_id or metadata.session_id or request.model,
        )
        record = resolution.record
        rendered = render_template_text(record.template_text, metadata.prompt_template_variables)
    except PromptTemplateError as exc:
        status_code = status.HTTP_404_NOT_FOUND if "not found" in str(exc).lower() else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    effective_request = request.model_copy(deep=True)
    effective_request.messages = [ChatMessage(role="system", content=rendered), *effective_request.messages]
    effective_request = effective_request.model_copy(
        update={
            "metadata": effective_request.metadata.model_copy(
                update={
                    "prompt_template_name": record.name,
                    "prompt_template_version": int(record.version),
                    "prompt_template_render_hash": hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
                    "prompt_template_model_override": record.model_override,
                    "prompt_template_selection_mode": resolution.selection_mode,
                    "prompt_template_rollout_percentage": resolution.rollout_percentage,
                }
            )
        }
    )
    if record.model_override:
        effective_request.model = record.model_override
    return effective_request, {
        "name": record.name,
        "version": record.version,
        "rendered_text": rendered,
        "render_hash": effective_request.metadata.prompt_template_render_hash,
        "model_override": record.model_override,
        "selection_mode": resolution.selection_mode,
        "rollout_percentage": resolution.rollout_percentage,
        "active_version": resolution.active_version,
        "challenger_version": resolution.challenger_version,
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
    effective_request: ChatCompletionRequest | None = None,
    classification: dict[str, str],
) -> tuple[str, object]:
    def _write(sync_session):
        request_log = record_request(sync_session, request, classification, effective_request=effective_request)
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
    requested_model_provider_key = None
    normalized_model = str(request.model or "").strip()
    if normalized_model and normalized_model not in RESERVED_ROUTE_MODELS:
        capabilities = await list_provider_capabilities_async(
            settings,
            session=None,
            allowed_models={normalized_model},
        )
        provider_matches = sorted(
            {
                str(capability.provider_name or "").strip()
                for capability in capabilities
                if str(capability.model_id or "").strip() == normalized_model
                and str(capability.provider_name or "").strip()
            }
        )
        if len(provider_matches) == 1:
            requested_model_provider_key = provider_matches[0]

    def _resolve(sync_session):
        selected_route = select_route(
            request_id,
            request,
            classification,
            settings,
            session=sync_session,
            requested_model_provider_key=requested_model_provider_key,
        )
        provider_registry = get_provider_registry(settings, session=sync_session)
        return selected_route, provider_registry

    return await session.run_sync(_resolve)


def _provider_for_route(
    *,
    settings: Settings,
    provider_registry: dict[str, object],
    selected_route,
    provider_key: str,
    entry_override: dict[str, object] | None = None,
):
    entry_index = getattr(selected_route, "entry_index", {})
    selected_entry = getattr(selected_route, "selected_entry", None)
    entry = entry_override
    if entry is None:
        entry = selected_entry if provider_key == selected_route.provider_key and selected_entry is not None else entry_index.get(provider_key)
    provider = provider_registry.get(provider_key)
    if provider is not None and isinstance(entry, dict):
        # Preserve the already-built provider object unless the route explicitly
        # overrides the network/runtime target for this hop.
        if not any(entry.get(field_name) for field_name in ("endpoint_url", "base_url", "runtime")):
            return provider
    if provider is not None and entry is None:
        return provider
    return resolve_provider(
        settings,
        provider_registry,
        provider_key=provider_key,
        entry=entry,
    )


def _request_for_provider_target(
    *,
    request_id: str,
    request: ChatCompletionRequest,
    selected_route,
    provider_key: str,
    settings: Settings,
    entry_override: dict[str, object] | None = None,
) -> ChatCompletionRequest:
    selected_entry = getattr(selected_route, "selected_entry", None)
    entry_index = getattr(selected_route, "entry_index", {})
    entry = entry_override
    if entry is None:
        entry = selected_entry if provider_key == selected_route.provider_key and selected_entry is not None else entry_index.get(provider_key)
    if not isinstance(entry, dict) or not bool(entry.get("forward_request_metadata")):
        return request
    forwarded = request.model_copy(deep=True)
    forwarded.metadata.root_request_id = forwarded.metadata.root_request_id or request_id
    forwarded.metadata.parent_request_id = request_id
    forwarded.metadata.upstream_node_id = settings.llmproxy_node_id
    forwarded.metadata.topology_path = [*forwarded.metadata.topology_path, settings.llmproxy_node_id]
    forwarded.metadata.routed_pool_id = str(entry.get("pool_id") or "") or None
    forwarded.metadata.routed_node_id = str(entry.get("node_id") or "") or None
    forwarded.metadata.forwarded_by_proxy = True
    return forwarded


def _route_entries(selected_route) -> list[dict[str, object]]:
    entry_index = getattr(selected_route, "entry_index", {})
    seen: set[str] = set()
    entries: list[dict[str, object]] = []
    for value in entry_index.values():
        if not isinstance(value, dict):
            continue
        entry_id = str(value.get("entry_id") or "")
        key = entry_id or str(id(value))
        if key in seen:
            continue
        seen.add(key)
        entries.append(value)
    selected_entry = getattr(selected_route, "selected_entry", None)
    if isinstance(selected_entry, dict):
        entry_id = str(selected_entry.get("entry_id") or "")
        key = entry_id or str(id(selected_entry))
        if key not in seen:
            entries.append(selected_entry)
    return entries


def _resolve_fallback_entry(selected_route, fallback) -> dict[str, object] | None:
    entry_index = getattr(selected_route, "entry_index", {})
    if getattr(fallback, "entry_id", None):
        entry = entry_index.get(f"entry:{fallback.entry_id}")
        if isinstance(entry, dict):
            return entry
    candidates: list[dict[str, object]] = []
    for entry in _route_entries(selected_route):
        if str(entry.get("provider_key", "")) != str(fallback.provider):
            continue
        model_id = str(entry.get("model_alias", entry.get("model_id", "")))
        if model_id != str(fallback.model):
            continue
        if getattr(fallback, "pool_id", None) and str(entry.get("pool_id") or "") != str(fallback.pool_id):
            continue
        if getattr(fallback, "node_id", None) and str(entry.get("node_id") or "") != str(fallback.node_id):
            continue
        candidates.append(entry)
    return candidates[0] if candidates else None


def _fallback_attempt_key(fallback) -> str:
    entry_id = getattr(fallback, "entry_id", None)
    if entry_id:
        return f"entry:{entry_id}"
    return ":".join(
        [
            str(fallback.provider),
            str(fallback.model),
            str(getattr(fallback, "pool_id", "") or ""),
            str(getattr(fallback, "node_id", "") or ""),
        ]
    )


def _update_decision_for_fallback(selected_route, decision, fallback, provider_result, entry_override) -> None:
    decision.selected_provider = fallback.provider
    decision.selected_provider_family = str(
        getattr(fallback, "provider_family", None) or provider_result.get("provider_family") or fallback.provider
    )
    decision.selected_model = fallback.model
    decision.selected_mode = "fallback"
    decision.decision_rationale = f"{decision.decision_rationale} Fallback engaged after runtime error."
    if isinstance(entry_override, dict):
        pool_id = str(entry_override.get("pool_id") or "") or None
        decision.selected_entry_id = str(entry_override.get("entry_id") or "") or None
        decision.selected_pool_id = pool_id
        decision.selected_node_id = str(entry_override.get("node_id") or "") or None
        decision.selected_node_role = str(entry_override.get("node_role") or "") or None
        decision.selected_node_labels = [str(item) for item in entry_override.get("node_labels", []) if str(item).strip()]
        decision.selected_capacity_class = str(entry_override.get("capacity_class") or "") or None
        decision.selected_balancing_strategy = (
            str(entry_override.get("balancing_strategy") or "session_affinity") if pool_id else None
        )
        decision.selected_affinity_key = str(entry_override.get("affinity_key") or "session_id") if pool_id else None
        selected_route.selected_entry = entry_override
    else:
        decision.selected_entry_id = None
        decision.selected_pool_id = None
        decision.selected_node_id = None
        decision.selected_node_role = None
        decision.selected_node_labels = []
        decision.selected_capacity_class = None
        decision.selected_balancing_strategy = None
        decision.selected_affinity_key = None


async def _persist_selected_response_async(
    session: AsyncSession,
    *,
    raw_request: ChatCompletionRequest,
    effective_request: ChatCompletionRequest,
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
            llm_trace = build_llm_interaction_trace(
                request=effective_request.model_dump(mode="json"),
                response=provider_result,
                routing=resolved_decision.model_dump(mode="json"),
                request_id=request_id,
                response_id=response_record.id,
                output_content=str(provider_result["content"]),
            )
            capture_training_candidate(
                sync_session,
                request_log_id=request_id,
                routing_decision_id=resolved_decision.routing_decision_id,
                session_id=effective_request.metadata.session_id,
                domain=classification["domain"],
                task_type=classification["task_type"],
                quality_score=None,
                selected_response=str(provider_result["content"]),
                messages=[message.model_dump(mode="json") for message in effective_request.messages],
                provenance={
                    "request_id": request_id,
                    "source": resolved_decision.selected_mode,
                    "teacher_models": [provider_result["model"]],
                    "judge_model": None,
                    "created_at": request_created_at.isoformat() if request_created_at else None,
                    "interaction_traces": [
                        llm_trace,
                        *extract_mcp_interaction_traces(
                            request=effective_request.model_dump(mode="json"),
                            response=provider_result,
                            parent_trace_id=str(llm_trace["trace_id"]),
                            request_id=request_id,
                        ),
                    ],
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
                    "requested_model": raw_request.model,
                    "effective_model": effective_request.model,
                    "prompt_template_name": effective_request.metadata.prompt_template_name or raw_request.metadata.prompt_template_name,
                    "prompt_template_version": effective_request.metadata.prompt_template_version or raw_request.metadata.prompt_template_version,
                    "prompt_template_variables": raw_request.metadata.prompt_template_variables,
                    "prompt_template_render_hash": effective_request.metadata.prompt_template_render_hash,
                    "prompt_template_model_override": effective_request.metadata.prompt_template_model_override,
                    "prompt_template_selection_mode": effective_request.metadata.prompt_template_selection_mode,
                    "prompt_template_rollout_percentage": effective_request.metadata.prompt_template_rollout_percentage,
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
    attempted = [f"primary:{selected_route.provider_key}:{selected_route.decision.selected_entry_id or ''}"]
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
        provider_request = _request_for_provider_target(
            request_id=selected_route.decision.request_id,
            request=request,
            selected_route=selected_route,
            provider_key=selected_route.provider_key,
            settings=settings,
        )
        if not _provider_supports_request(provider_request, provider):
            raise ValueError("tooling_not_supported")
        if not _request_fits_provider(provider_request, provider):
            context_rejected = True
            raise ValueError("context_window_exceeded")
        if mcp_context is None:
            provider_result = await _invoke_provider_with_retries(
                settings=settings,
                provider_key=selected_route.provider_key,
                provider=provider,
                request=provider_request,
            )
        else:
            provider_result = await mcp_context.execute(
                settings,
                lambda invoke_request: _invoke_provider_with_retries(
                    settings=settings,
                    provider_key=selected_route.provider_key,
                    provider=provider,
                    request=_request_for_provider_target(
                        request_id=selected_route.decision.request_id,
                        request=invoke_request,
                        selected_route=selected_route,
                        provider_key=selected_route.provider_key,
                        settings=settings,
                    ),
                ),
            )
        return provider_result, selected_route.decision
    except Exception:
        for fallback in selected_route.decision.fallback_chain:
            fallback_key = fallback.provider
            attempt_key = _fallback_attempt_key(fallback)
            if attempt_key in attempted:
                continue
            attempted.append(attempt_key)
            if is_provider_cooled_down(fallback_key):
                continue
            entry_override = _resolve_fallback_entry(selected_route, fallback)
            try:
                provider = _provider_for_route(
                    settings=settings,
                    provider_registry=provider_registry,
                    selected_route=selected_route,
                    provider_key=fallback_key,
                    entry_override=entry_override,
                )
                if provider is None:
                    continue
                provider_request = _request_for_provider_target(
                    request_id=selected_route.decision.request_id,
                    request=request,
                    selected_route=selected_route,
                    provider_key=fallback_key,
                    settings=settings,
                    entry_override=entry_override,
                )
                if not _provider_supports_request(provider_request, provider):
                    continue
                if not _request_fits_provider(provider_request, provider):
                    context_rejected = True
                    continue
                if mcp_context is None:
                    provider_result = await _invoke_provider_with_retries(
                        settings=settings,
                        provider_key=fallback_key,
                        provider=provider,
                        request=provider_request,
                    )
                else:
                    provider_result = await mcp_context.execute(
                        settings,
                        lambda invoke_request: _invoke_provider_with_retries(
                            settings=settings,
                            provider_key=fallback_key,
                            provider=provider,
                            request=_request_for_provider_target(
                                request_id=selected_route.decision.request_id,
                                request=invoke_request,
                                selected_route=selected_route,
                                provider_key=fallback_key,
                                settings=settings,
                                entry_override=entry_override,
                            ),
                        ),
                    )
            except Exception:
                continue
            _update_decision_for_fallback(
                selected_route,
                selected_route.decision,
                fallback,
                provider_result,
                entry_override,
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
    attempted = [f"primary:{selected_route.provider_key}:{selected_route.decision.selected_entry_id or ''}"]
    context_rejected = False
    candidates = [(selected_route.provider_key, selected_route.decision.selected_model, selected_route.decision, None, None)]
    for fallback in selected_route.decision.fallback_chain:
        attempt_key = _fallback_attempt_key(fallback)
        if attempt_key in attempted:
            continue
        attempted.append(attempt_key)
        candidates.append((fallback.provider, fallback.model, selected_route.decision, fallback, _resolve_fallback_entry(selected_route, fallback)))

    for index, (provider_key, selected_model, decision, fallback, entry_override) in enumerate(candidates):
        if is_provider_cooled_down(provider_key):
            continue
        provider = _provider_for_route(
            settings=settings,
            provider_registry=provider_registry,
            selected_route=selected_route,
            provider_key=provider_key,
            entry_override=entry_override,
        )
        if provider is None or not getattr(provider, "supports_streaming", False):
            continue
        provider_request = _request_for_provider_target(
            request_id=selected_route.decision.request_id,
            request=request,
            selected_route=selected_route,
            provider_key=provider_key,
            settings=settings,
            entry_override=entry_override,
        )
        if not _provider_supports_request(provider_request, provider):
            continue
        if not _request_fits_provider(provider_request, provider):
            context_rejected = True
            continue
        started = False
        try:
            async for chunk in _stream_provider_with_retries(
                settings=settings,
                provider_key=provider_key,
                provider=provider,
                request=provider_request,
            ):
                if not started and index > 0:
                    _update_decision_for_fallback(
                        selected_route,
                        decision,
                        fallback,
                        {
                            "provider_family": getattr(provider, "provider_family", provider_key),
                        },
                        entry_override,
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


def _mark_provider_result_first_response_latency(
    provider_result: dict[str, object],
    *,
    first_response_latency_ms: int | None,
    streamed: bool,
) -> dict[str, object]:
    raw_response = provider_result.get("raw_response")
    if not isinstance(raw_response, dict):
        raw_response = {}
    else:
        raw_response = dict(raw_response)
    raw_response["streamed"] = bool(streamed)
    if first_response_latency_ms is not None:
        raw_response["first_response_latency_ms"] = max(0, int(first_response_latency_ms))
    provider_result["raw_response"] = raw_response
    return provider_result


def _infer_provider_key_for_requested_model(model_id: str) -> str | None:
    normalized = str(model_id or "").strip().lower()
    if not normalized or normalized in RESERVED_ROUTE_MODELS:
        return None
    if normalized.startswith(("gpt-", "o1", "o3", "omni-", "text-embedding-", "whisper-", "tts-", "gpt-image")):
        return "openai"
    if normalized.startswith("claude-"):
        return "anthropic"
    if normalized.startswith("gemini-"):
        return "google"
    if normalized.startswith("grok-"):
        return "xai"
    if normalized.startswith("llama-"):
        return "groq"
    return None


def _annotate_provider_result_cache(
    provider_result: dict[str, object],
    *,
    outcome: str,
    layer: str | None = None,
) -> dict[str, object]:
    raw_response = provider_result.get("raw_response")
    if not isinstance(raw_response, dict):
        raw_response = {}
    else:
        raw_response = dict(raw_response)
    raw_response["cache"] = {
        "outcome": str(outcome or "unknown"),
        "layer": str(layer or "none"),
    }
    provider_result["raw_response"] = raw_response
    return provider_result


def _annotate_provider_result_cost_breakdown(provider_result: dict[str, object]) -> dict[str, object]:
    provider_name = str(provider_result.get("provider") or "")
    model_id = str(provider_result.get("model") or "")
    input_tokens = int(provider_result.get("input_tokens", 0) or 0)
    output_tokens = int(provider_result.get("output_tokens", 0) or 0)
    breakdown = estimate_cost_breakdown_usd(
        provider_name=provider_name,
        model_id=model_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    raw_response = provider_result.get("raw_response")
    if not isinstance(raw_response, dict):
        raw_response = {}
    else:
        raw_response = dict(raw_response)
    raw_response.update(breakdown)
    provider_result["raw_response"] = raw_response
    provider_result.setdefault("input_cost_estimate", breakdown["input_cost_estimate"])
    provider_result.setdefault("output_cost_estimate", breakdown["output_cost_estimate"])
    return provider_result


def _log_llm_cache_event(
    settings: Settings,
    *,
    request_id: str,
    session_id: str,
    provider_key: str,
    model_id: str,
    outcome: str,
    layer: str,
) -> None:
    log_record(
        settings,
        level="INFO",
        component="proxy.chat",
        category="cache",
        message="Response cache evaluated",
        data={
            "request_id": request_id,
            "session_id": session_id,
            "provider_key": provider_key,
            "model_id": model_id,
            "cache_outcome": outcome,
            "cache_layer": layer,
        },
    )


def _log_stream_lifecycle_event(
    settings: Settings,
    *,
    message: str,
    request_id: str,
    session_id: str,
    provider_key: str,
    model_id: str,
    selected_mode: str | None,
    chunk_count: int | None = None,
    first_response_latency_ms: int | None = None,
    error: str | None = None,
    stream_abort_phase: str | None = None,
) -> None:
    payload = {
        "request_id": request_id,
        "session_id": session_id,
        "provider_key": provider_key,
        "model_id": model_id,
        "selected_mode": selected_mode,
    }
    if chunk_count is not None:
        payload["chunk_count"] = chunk_count
    if first_response_latency_ms is not None:
        payload["first_response_latency_ms"] = first_response_latency_ms
    if error:
        payload["error"] = error
    if stream_abort_phase:
        payload["stream_abort_phase"] = stream_abort_phase
    log_record(
        settings,
        level="INFO" if not error else "ERROR",
        component="proxy.chat",
        category="stream",
        message=message,
        data=payload,
    )


def _log_rate_limit_event(
    settings: Settings,
    *,
    request: ChatCompletionRequest,
    principal: AuthPrincipal,
    endpoint: str,
    detail: str,
    estimated_tokens: int,
) -> None:
    metadata = request.metadata
    log_record(
        settings,
        level="WARN",
        component="proxy.chat",
        category="rate_limit",
        message="Rate limit denied request",
        data={
            "session_id": metadata.session_id,
            "listener_id": metadata.listener_id,
            "requested_model": request.model,
            "provider_key": _infer_provider_key_for_requested_model(request.model),
            "endpoint": endpoint,
            "estimated_tokens": estimated_tokens,
            "principal_role": principal.role,
            "owner_id": principal.owner_id,
            "detail": detail,
        },
    )


def _classify_provider_limit(error: object) -> dict[str, object] | None:
    status_code = getattr(error, "status_code", None)
    detail = getattr(error, "detail", None)
    message_parts = [str(error or "")]
    if isinstance(detail, str) and detail:
        message_parts.append(detail)
    combined = " ".join(message_parts).lower()
    if status_code == 429 or "429" in combined or "rate limit" in combined or "too many requests" in combined:
        return {
            "status_code": int(status_code) if isinstance(status_code, int) else 429,
            "detail": str(detail or error or "provider rate limited request"),
        }
    return None


def _stream_abort_phase(*, chunk_count: int, first_response_latency_ms: int | None) -> str:
    if int(chunk_count or 0) > 0 or first_response_latency_ms is not None:
        return "partial_abort"
    return "prelude_failure"


def _log_provider_limit_event(
    settings: Settings,
    *,
    request_id: str | None,
    session_id: str | None,
    provider_key: str,
    model_id: str,
    phase: str,
    status_code: int | None,
    detail: str,
) -> None:
    log_record(
        settings,
        level="WARN",
        component="proxy.chat",
        category="provider_limit",
        message="Upstream provider returned 429",
        data={
            "request_id": request_id,
            "session_id": session_id,
            "provider_key": provider_key,
            "model_id": model_id,
            "status_code": status_code,
            "detail": detail,
            "provider_limit_bucket": f"provider_429_{phase}",
            "phase": phase,
        },
    )


@router.post("/v1/messages/count_tokens", response_model=AnthropicCountTokensResponse)
async def anthropic_count_tokens(
    request: AnthropicMessagesRequest,
    rate_limit_session: Session = Depends(get_session),
    _listener: dict[str, object] = Depends(require_proxy_listener),
    _principal: AuthPrincipal = Depends(require_api_token),
) -> AnthropicCountTokensResponse:
    return AnthropicCountTokensResponse(input_tokens=_estimate_anthropic_input_tokens(rate_limit_session, request))


@router.post("/v1/messages", response_model=None)
async def anthropic_messages(
    request: AnthropicMessagesRequest,
    http_request: Request,
    cache_control: str | None = Header(default=None, alias="Cache-Control"),
    _anthropic_version: str | None = Header(default=None, alias="anthropic-version"),
    session: AsyncSession = Depends(get_async_session),
    rate_limit_session: Session = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
    _listener: dict[str, object] = Depends(require_proxy_listener),
    principal: AuthPrincipal = Depends(require_api_token),
):
    translated_request = _chat_request_from_anthropic_messages(request)
    response = await chat_completions(
        translated_request,
        http_request=http_request,
        cache_control=cache_control,
        session=session,
        rate_limit_session=rate_limit_session,
        settings=settings,
        principal=principal,
    )
    if isinstance(response, StreamingResponse):
        return StreamingResponse(
            _anthropic_stream_from_openai_stream(response.body_iterator),
            media_type="text/event-stream",
        )
    raw_payload = json.loads(response.body.decode("utf-8"))
    payload = _anthropic_messages_response_from_openai_payload(raw_payload)
    return Response(
        content=json.dumps(payload),
        media_type="application/json",
        headers={key: value for key, value in response.headers.items() if key.lower().startswith("x-llmproxy-")},
    )


@router.post(
    "/v1/chat/completions",
    response_model=None,
)
async def chat_completions(
    request: ChatCompletionRequest,
    http_request: Request,
    cache_control: str | None = Header(default=None, alias="Cache-Control"),
    session: AsyncSession = Depends(get_async_session),
    rate_limit_session: Session = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
    _listener: dict[str, object] = Depends(require_proxy_listener),
    principal: AuthPrincipal = Depends(require_api_token),
) -> ChatCompletionResponse | StreamingResponse:
    request = _apply_inbound_listener_metadata(request, http_request=http_request, settings=settings)
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
        try:
            enforce_rate_limits(rate_limit_session, principal, estimated_tokens=reserved_tokens)
        except HTTPException as exc:
            _log_rate_limit_event(
                settings,
                request=effective_request,
                principal=principal,
                endpoint="/v1/chat/completions",
                detail=str(exc.detail),
                estimated_tokens=reserved_tokens,
            )
            raise
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
        effective_request = enrich_request_for_principal(effective_request, principal)
        try:
            bypass_cache, suppress_cache_store = _cache_control_flags(cache_control)
            request_log_id, request_created_at = await _record_request_async(
                session,
                request=request,
                effective_request=effective_request,
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
                _mark_provider_result_first_response_latency(
                    provider_result,
                    first_response_latency_ms=int(provider_result.get("latency_ms", 0) or 0),
                    streamed=True,
                )
                guardrail_context.provider_result = provider_result
                await run_post_guardrails(guardrail_context)
                await _persist_selected_response_async(
                    session,
                    raw_request=request,
                    effective_request=effective_request,
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
            cache_observation = {"outcome": "unused", "layer": "none"}
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
                    first_response_latency_ms: int | None = None
                    chunk_count = 0
                    yield _stream_chunk_bytes(
                        response_id=response_id,
                        model=provider_model,
                        delta={"role": "assistant"},
                        finish_reason=None,
                    )
                    _log_stream_lifecycle_event(
                        settings,
                        message="Streaming chat started",
                        request_id=request_log_id,
                        session_id=request.metadata.session_id,
                        provider_key=str(resolved_decision.selected_provider),
                        model_id=str(provider_model),
                        selected_mode=resolved_decision.selected_mode,
                    )
                    try:
                        async for chunk, resolved_decision in _stream_with_fallback(settings, provider_registry, selected_route, request):
                            chunk_count += 1
                            provider_model = str(chunk.get("model", provider_model))
                            delta_text = str(chunk.get("delta", ""))
                            if delta_text:
                                aggregated_content += delta_text
                                if first_response_latency_ms is None:
                                    first_response_latency_ms = int((perf_counter() - started_at) * 1000)
                                yield _stream_chunk_bytes(
                                    response_id=response_id,
                                    model=provider_model,
                                    delta={"content": delta_text},
                                    finish_reason=None,
                                )
                            chunk_tool_calls = chunk.get("tool_calls")
                            if isinstance(chunk_tool_calls, list) and chunk_tool_calls:
                                aggregated_tool_calls = _merge_tool_calls(aggregated_tool_calls, chunk_tool_calls)
                                if first_response_latency_ms is None:
                                    first_response_latency_ms = int((perf_counter() - started_at) * 1000)
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
                        _mark_provider_result_first_response_latency(
                            provider_result,
                            first_response_latency_ms=first_response_latency_ms or int(provider_result["latency_ms"]),
                            streamed=True,
                        )
                        _annotate_provider_result_cost_breakdown(provider_result)
                        guardrail_context.provider_result = provider_result
                        await run_post_guardrails(guardrail_context)
                        await _persist_selected_response_async(
                            session,
                            raw_request=request,
                            effective_request=request,
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
                        _log_stream_lifecycle_event(
                            settings,
                            message="Streaming chat completed",
                            request_id=request_log_id,
                            session_id=request.metadata.session_id,
                            provider_key=str(provider_result["provider"]),
                            model_id=str(provider_result["model"]),
                            selected_mode=resolved_decision.selected_mode,
                            chunk_count=chunk_count,
                            first_response_latency_ms=first_response_latency_ms,
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
                        _log_stream_lifecycle_event(
                            settings,
                            message="Streaming chat failed",
                            request_id=request_log_id,
                            session_id=request.metadata.session_id,
                            provider_key=str(getattr(resolved_decision, "selected_provider", selected_provider_label)),
                            model_id=str(provider_model),
                            selected_mode=getattr(resolved_decision, "selected_mode", None),
                            chunk_count=chunk_count,
                            first_response_latency_ms=first_response_latency_ms,
                            error=str(exc),
                            stream_abort_phase=_stream_abort_phase(
                                chunk_count=chunk_count,
                                first_response_latency_ms=first_response_latency_ms,
                            ),
                        )
                        provider_limit = _classify_provider_limit(exc)
                        if provider_limit is not None:
                            _log_provider_limit_event(
                                settings,
                                request_id=request_log_id,
                                session_id=request.metadata.session_id,
                                provider_key=str(getattr(resolved_decision, "selected_provider", selected_provider_label)),
                                model_id=str(provider_model),
                                phase="stream",
                                status_code=provider_limit.get("status_code") if isinstance(provider_limit.get("status_code"), int) else None,
                                detail=str(provider_limit.get("detail") or str(exc)),
                            )
                        message = str(exc)
                        status_code_value = getattr(exc, "status_code", None)
                        detail = getattr(exc, "detail", None)
                        if isinstance(detail, str) and detail:
                            message = detail
                        yield _stream_error_bytes(
                            message=message,
                            status_code=status_code_value,
                            error_type=exc.__class__.__name__,
                        )
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
                    if cache_hit_result is not None:
                        cache_observation = {"outcome": "hit", "layer": "exact"}
                    else:
                        cache_observation = {"outcome": "miss", "layer": "none"}
                else:
                    cache_observation = {"outcome": "bypass", "layer": "none"}
            if cache_hit_result is not None and cache_observation["layer"] == "none":
                cache_observation = {"outcome": "hit", "layer": "semantic"}
            if cache_hit_result is not None and not request_has_mcp_tools(request):
                provider_result = dict(cache_hit_result)
                _annotate_provider_result_cache(provider_result, outcome=cache_observation["outcome"], layer=cache_observation["layer"])
                _annotate_provider_result_cost_breakdown(provider_result)
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
                if semantic_cache_enabled and cache_observation["outcome"] == "miss" and cache_hit_result is not None:
                    cache_observation = {"outcome": "hit", "layer": "semantic"}
                _annotate_provider_result_cache(provider_result, outcome=cache_observation["outcome"], layer=cache_observation["layer"])
                _annotate_provider_result_cost_breakdown(provider_result)
                guardrail_context.provider_result = provider_result
                await run_post_guardrails(guardrail_context)
                await _persist_selected_response_async(
                    session,
                    raw_request=request,
                    effective_request=effective_request,
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
            _log_llm_cache_event(
                settings,
                request_id=request_log_id,
                session_id=request.metadata.session_id,
                provider_key=str(provider_result.get("provider", selected_route.provider_key)),
                model_id=str(provider_result.get("model", selected_route.decision.selected_model)),
                outcome=str(cache_observation["outcome"]),
                layer=str(cache_observation["layer"]),
            )
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
            provider_limit = _classify_provider_limit(exc)
            if provider_limit is not None:
                _log_provider_limit_event(
                    settings,
                    request_id=request_log_id,
                    session_id=effective_request.metadata.session_id,
                    provider_key=selected_provider_label,
                    model_id=str(getattr(exc, "model_id", None) or effective_request.model),
                    phase="request",
                    status_code=provider_limit.get("status_code") if isinstance(provider_limit.get("status_code"), int) else None,
                    detail=str(provider_limit.get("detail") or exc.detail),
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
            provider_limit = _classify_provider_limit(exc)
            if provider_limit is not None:
                _log_provider_limit_event(
                    settings,
                    request_id=request_log_id,
                    session_id=effective_request.metadata.session_id,
                    provider_key=selected_provider_label,
                    model_id=effective_request.model,
                    phase="request",
                    status_code=provider_limit.get("status_code") if isinstance(provider_limit.get("status_code"), int) else None,
                    detail=str(provider_limit.get("detail") or exc),
                )
            raise


@router.post("/v1/completions", response_model=CompletionResponse)
async def completions(
    request: CompletionRequest,
    http_request: Request,
    session: AsyncSession = Depends(get_async_session),
    rate_limit_session: Session = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
    _listener: dict[str, object] = Depends(require_proxy_listener),
    principal: AuthPrincipal = Depends(require_api_token),
) -> CompletionResponse | StreamingResponse:
    translated_request = _chat_request_from_completion(request)
    response = await chat_completions(
        translated_request,
        http_request=http_request,
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
async def list_models(
    settings: Settings = Depends(get_runtime_settings),
    _listener: dict[str, object] = Depends(require_proxy_listener),
    principal: AuthPrincipal = Depends(require_api_token),
) -> list[ModelInfo]:
    allowed_models = set(principal.models_allowed) if principal.models_allowed else None
    return [
        ModelInfo.model_validate(item)
        for item in await list_proxy_models_async(settings, allowed_models=allowed_models)
    ]


@router.get("/v1/pricing")
def list_pricing(
    _listener: dict[str, object] = Depends(require_proxy_listener),
    _principal: AuthPrincipal = Depends(require_api_token),
) -> list[dict[str, float | str]]:
    return pricing_catalog()


@router.post("/v1/embeddings", response_model=EmbeddingResponse)
async def embeddings(
    request: EmbeddingRequest,
    rate_limit_session: Session = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
    _listener: dict[str, object] = Depends(require_proxy_listener),
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
    _listener: dict[str, object] = Depends(require_proxy_listener),
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
    _listener: dict[str, object] = Depends(require_proxy_listener),
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
    _listener: dict[str, object] = Depends(require_proxy_listener),
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
    _listener: dict[str, object] = Depends(require_proxy_listener),
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
