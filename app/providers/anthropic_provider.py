"""Anthropic provider implementation."""

from collections.abc import AsyncIterator, Sequence
import json
from time import time

from app.config import Settings
from app.providers.base import BaseProvider
from app.services.cost import estimate_cost_usd
from app.schemas.chat import ChatCompletionRequest
from app.schemas.provider import ProviderCapability, ProviderRequestShape


class AnthropicProvider(BaseProvider):
    provider_family = "Anthropic"
    provider_name = "anthropic"
    price_per_token = 0.000024
    anthropic_version = "2023-06-01"
    supports_streaming = True
    supports_tools = True

    def __init__(
        self,
        model_id: str,
        *,
        api_key: str | None = None,
        base_url: str = "https://api.anthropic.com/v1",
        timeout_seconds: float = 60.0,
        transport=None,
    ) -> None:
        super().__init__(model_id, timeout_seconds=timeout_seconds, transport=transport)
        self.api_key = api_key
        self.base_url = base_url

    @classmethod
    def from_settings(cls, settings: Settings, *, transport=None) -> "AnthropicProvider":
        return cls(
            settings.llmproxy_anthropic_model,
            api_key=settings.llmproxy_anthropic_api_key,
            base_url=settings.llmproxy_anthropic_base_url,
            timeout_seconds=settings.llmproxy_provider_timeout_seconds,
            transport=transport,
        )

    @staticmethod
    def _normalize_text_blocks(content: object) -> list[dict[str, object]]:
        if isinstance(content, str):
            if not content:
                return []
            return [{"type": "text", "text": content}]
        if not isinstance(content, list):
            return []
        blocks: list[dict[str, object]] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type", ""))
            if item_type == "text" and isinstance(item.get("text"), str):
                blocks.append({"type": "text", "text": item["text"]})
                continue
            if item_type in {"tool_use", "tool_result"}:
                blocks.append(dict(item))
                continue
            if isinstance(item.get("text"), str):
                blocks.append({"type": "text", "text": item["text"]})
        return blocks

    @staticmethod
    def _tool_use_block(tool_call: object) -> dict[str, object] | None:
        if not isinstance(tool_call, dict):
            return None
        function = tool_call.get("function")
        if not isinstance(function, dict):
            return None
        name = str(function.get("name", "")).strip()
        if not name:
            return None
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
        return {
            "type": "tool_use",
            "id": str(tool_call.get("id") or f"toolu_{name}"),
            "name": name,
            "input": arguments,
        }

    @staticmethod
    def _tool_result_blocks(message: object) -> list[dict[str, object]]:
        tool_use_id = str(getattr(message, "tool_call_id", "") or "").strip()
        if not tool_use_id:
            return []
        content = getattr(message, "content", None)
        if isinstance(content, str):
            block_content: object = content
        else:
            block_content = AnthropicProvider._normalize_text_blocks(content)
        return [{"type": "tool_result", "tool_use_id": tool_use_id, "content": block_content}]

    @staticmethod
    def _request_messages(messages: Sequence[object]) -> tuple[str | list[dict[str, object]] | None, list[dict[str, object]]]:
        system_blocks: list[dict[str, object]] = []
        payload: list[dict[str, object]] = []
        for message in messages:
            role = str(getattr(message, "role", "user"))
            if role == "system":
                system_blocks.extend(AnthropicProvider._normalize_text_blocks(getattr(message, "content", "")))
                continue
            if role == "tool":
                tool_result_blocks = AnthropicProvider._tool_result_blocks(message)
                if tool_result_blocks:
                    payload.append({"role": "user", "content": tool_result_blocks})
                continue
            blocks = AnthropicProvider._normalize_text_blocks(getattr(message, "content", ""))
            if role == "assistant":
                tool_calls = getattr(message, "tool_calls", None)
                if isinstance(tool_calls, list):
                    for tool_call in tool_calls:
                        block = AnthropicProvider._tool_use_block(tool_call)
                        if block is not None:
                            blocks.append(block)
            payload.append(
                {
                    "role": "user" if role == "user" else "assistant",
                    "content": blocks if blocks else "",
                }
            )
        if not system_blocks:
            return None, payload
        if len(system_blocks) == 1 and isinstance(system_blocks[0].get("text"), str):
            return str(system_blocks[0]["text"]), payload
        return system_blocks, payload

    @staticmethod
    def _tool_choice_payload(choice: object) -> dict[str, object] | None:
        if choice is None:
            return None
        if isinstance(choice, str):
            mapping = {
                "auto": {"type": "auto"},
                "required": {"type": "any"},
                "none": {"type": "none"},
            }
            return mapping.get(choice)
        if not isinstance(choice, dict):
            return None
        choice_type = str(choice.get("type", "")).strip()
        if choice_type == "function":
            function = choice.get("function")
            if isinstance(function, dict) and isinstance(function.get("name"), str):
                return {"type": "tool", "name": function["name"]}
            return {"type": "any"}
        if choice_type in {"auto", "none", "any", "tool"}:
            payload = {"type": choice_type}
            if isinstance(choice.get("name"), str):
                payload["name"] = choice["name"]
            return payload
        return None

    @staticmethod
    def _extract_tool_calls(content_blocks: object) -> list[dict[str, object]] | None:
        if not isinstance(content_blocks, list):
            return None
        tool_calls: list[dict[str, object]] = []
        for block in content_blocks:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            tool_calls.append(
                {
                    "id": str(block.get("id") or "toolu_generated"),
                    "type": "function",
                    "function": {
                        "name": str(block.get("name") or "tool"),
                        "arguments": json.dumps(block.get("input") or {}),
                    },
                }
            )
        return tool_calls or None

    @staticmethod
    def _map_stop_reason(stop_reason: object) -> str:
        value = str(stop_reason or "end_turn")
        return {
            "end_turn": "stop",
            "stop_sequence": "stop",
            "max_tokens": "length",
            "tool_use": "tool_calls",
        }.get(value, value)

    @classmethod
    def _request_shape_for_model(cls, model_id: str) -> ProviderRequestShape:
        normalized = str(model_id or "").strip().lower()
        rules: list[tuple[str, ProviderRequestShape]] = [
            ("claude-fable-", ProviderRequestShape(accepts_temperature=False)),
            ("claude-opus-4-7", ProviderRequestShape(accepts_temperature=False)),
            ("claude-opus-4-8", ProviderRequestShape(accepts_temperature=False)),
        ]
        for prefix, shape in rules:
            if normalized.startswith(prefix):
                return shape
        return ProviderRequestShape()

    @staticmethod
    def _request_payload(request: ChatCompletionRequest, *, model_id: str, stream: bool) -> dict[str, object]:
        system, messages = AnthropicProvider._request_messages(request.messages)
        request_shape = AnthropicProvider._request_shape_for_model(model_id)
        payload: dict[str, object] = {
            "model": model_id,
            "messages": messages,
            "max_tokens": request.max_tokens,
        }
        if request.temperature is not None and request_shape.accepts_temperature:
            payload["temperature"] = request.temperature
        if system is not None:
            payload["system"] = system
        if request.top_p is not None and request_shape.accepts_top_p:
            payload["top_p"] = request.top_p
        if request.stop is not None and request_shape.accepts_stop_sequences:
            payload["stop_sequences"] = [request.stop] if isinstance(request.stop, str) else request.stop
        if request.user:
            payload["metadata"] = {"user_id": request.user}
        if request.tools is not None:
            payload["tools"] = [
                {
                    "name": tool.function.name,
                    "description": tool.function.description,
                    "input_schema": tool.function.parameters or {"type": "object"},
                }
                for tool in request.tools
                if getattr(tool, "type", "") == "function"
            ]
        tool_choice = AnthropicProvider._tool_choice_payload(request.tool_choice)
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        if stream:
            payload["stream"] = True
        return payload

    @staticmethod
    def _extract_content(content_blocks: object) -> str:
        if not isinstance(content_blocks, list):
            return ""
        parts: list[str] = []
        for block in content_blocks:
            if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "".join(parts)

    async def list_models(self) -> list[ProviderCapability]:
        api_key = self._require_config(self.api_key, field_name="llmproxy_anthropic_api_key")
        headers = {
            "x-api-key": api_key,
            "anthropic-version": self.anthropic_version,
        }
        after_id: str | None = None
        capabilities: list[ProviderCapability] = []
        async with self._client(
            base_url=self.base_url,
            headers=headers,
            timeout_seconds=min(self.timeout_seconds, 10.0),
        ) as client:
            while True:
                params = {"limit": 1000}
                if after_id:
                    params["after_id"] = after_id
                response = await client.get("/models", params=params)
                response.raise_for_status()
                payload = response.json()
                for item in payload.get("data", []):
                    if not isinstance(item, dict):
                        continue
                    model_id = str(item.get("id") or "").strip()
                    if not model_id:
                        continue
                    capabilities.append(
                        ProviderCapability(
                            provider_family=self.provider_family,
                            provider_name=self.provider_name,
                            model_id=model_id,
                            supports_streaming=self.supports_streaming,
                            supports_embeddings=False,
                            supports_tools=self.supports_tools,
                            max_context_tokens=int(item.get("context_window") or 128_000),
                            max_output_tokens=int(item.get("max_tokens") or 8_192),
                            request_shape=self._request_shape_for_model(model_id),
                        )
                    )
                if not payload.get("has_more"):
                    break
                after_id = str(payload.get("last_id") or "").strip() or None
                if not after_id:
                    break
        return capabilities or [self.capability]

    async def chat(self, request: ChatCompletionRequest) -> dict[str, object]:
        api_key = self._require_config(self.api_key, field_name="llmproxy_anthropic_api_key")
        payload = self._request_payload(request, model_id=self.model_id, stream=False)
        headers = {
            "x-api-key": api_key,
            "anthropic-version": self.anthropic_version,
            "content-type": "application/json",
        }
        async with self._client(
            base_url=self.base_url,
            headers=headers,
            timeout_seconds=self._timeout_for_request(request),
        ) as client:
            response = await client.post("/messages", json=payload)
            response.raise_for_status()
            raw_response = response.json()

        usage = raw_response.get("usage", {})
        prompt_tokens = int(usage.get("input_tokens", 0))
        completion_tokens = int(usage.get("output_tokens", 0))
        model_name = str(raw_response.get("model", self.model_id))
        cost_estimate = estimate_cost_usd(
            provider_name=self.provider_name,
            model_id=model_name,
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
        )
        return {
            "model": model_name,
            "content": self._extract_content(raw_response.get("content")),
            "tool_calls": self._extract_tool_calls(raw_response.get("content")),
            "input_tokens": prompt_tokens,
            "output_tokens": completion_tokens,
            "finish_reason": self._map_stop_reason(raw_response.get("stop_reason", "end_turn")),
            "cost_estimate": cost_estimate,
            "raw_response": raw_response,
        }

    async def stream_chat(self, request: ChatCompletionRequest) -> AsyncIterator[dict[str, object]]:
        api_key = self._require_config(self.api_key, field_name="llmproxy_anthropic_api_key")
        payload = self._request_payload(request, model_id=self.model_id, stream=True)
        headers = {
            "x-api-key": api_key,
            "anthropic-version": self.anthropic_version,
            "content-type": "application/json",
        }
        async with self._client(
            base_url=self.base_url,
            headers=headers,
            timeout_seconds=self._timeout_for_request(request),
        ) as client:
            async with client.stream("POST", "/messages", json=payload) as response:
                response.raise_for_status()
                event_name: str | None = None
                async for line in response.aiter_lines():
                    if not line:
                        event_name = None
                        continue
                    if line.startswith("event: "):
                        event_name = line[7:].strip()
                        continue
                    if not line.startswith("data: "):
                        continue
                    raw_chunk = json.loads(line[6:].strip())
                    chunk_type = event_name or raw_chunk.get("type")
                    delta = ""
                    tool_calls = None
                    finish_reason = None
                    usage = raw_chunk.get("usage") or {}
                    if chunk_type == "content_block_delta":
                        delta_obj = raw_chunk.get("delta") or {}
                        if delta_obj.get("type") == "text_delta":
                            delta = str(delta_obj.get("text", ""))
                        elif delta_obj.get("type") == "input_json_delta":
                            tool_calls = [
                                {
                                    "index": int(raw_chunk.get("index", 0)),
                                    "type": "function",
                                    "function": {"arguments": str(delta_obj.get("partial_json", ""))},
                                }
                            ]
                    elif chunk_type == "content_block_start":
                        content_block = raw_chunk.get("content_block") or {}
                        if isinstance(content_block, dict) and content_block.get("type") == "tool_use":
                            tool_calls = [
                                {
                                    "index": int(raw_chunk.get("index", 0)),
                                    "id": str(content_block.get("id") or "toolu_generated"),
                                    "type": "function",
                                    "function": {
                                        "name": str(content_block.get("name") or "tool"),
                                        "arguments": "",
                                    },
                                }
                            ]
                    elif chunk_type == "message_delta":
                        delta_obj = raw_chunk.get("delta") or {}
                        finish_reason = self._map_stop_reason(delta_obj.get("stop_reason"))
                    elif chunk_type == "message_stop":
                        finish_reason = "stop"
                    yield {
                        "model": str(raw_chunk.get("model", self.model_id)),
                        "delta": delta,
                        "tool_calls": tool_calls,
                        "finish_reason": finish_reason,
                        "input_tokens": int(usage.get("input_tokens", 0)),
                        "output_tokens": int(usage.get("output_tokens", 0)),
                        "raw_chunk": raw_chunk,
                    }

    async def healthcheck(self) -> dict[str, object]:
        api_key = self._require_config(self.api_key, field_name="llmproxy_anthropic_api_key")
        headers = {
            "x-api-key": api_key,
            "anthropic-version": self.anthropic_version,
            "content-type": "application/json",
        }
        payload = {
            "model": self.model_id,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 1,
        }
        if self._request_shape_for_model(self.model_id).accepts_temperature:
            payload["temperature"] = 0
        started_at = time()
        try:
            async with self._client(base_url=self.base_url, headers=headers, timeout_seconds=5.0) as client:
                response = await client.post("/messages", json=payload)
            detail = ""
            if response.status_code >= 400:
                try:
                    detail = str((response.json().get("error") or {}).get("message") or "").strip()
                except Exception:
                    detail = response.text[:200].strip()
            return {
                "ok": 200 <= response.status_code < 300,
                "provider": self.provider_name,
                "model": self.model_id,
                "status_code": response.status_code,
                "latency_ms": int((time() - started_at) * 1000),
                "detail": detail,
            }
        except Exception as exc:
            return {
                "ok": False,
                "provider": self.provider_name,
                "model": self.model_id,
                "error": str(exc),
                "latency_ms": int((time() - started_at) * 1000),
            }
