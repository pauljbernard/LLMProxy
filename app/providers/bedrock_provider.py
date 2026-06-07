"""AWS Bedrock provider implementation."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Sequence
from threading import Thread
from time import time
from typing import Any

from app.config import Settings
from app.providers.base import BaseProvider, ProviderConfigurationError
from app.services.cost import estimate_cost_usd
from app.schemas.chat import ChatCompletionRequest


class BedrockProvider(BaseProvider):
    provider_family = "AWS Bedrock"
    provider_name = "bedrock"
    price_per_token = 0.000023
    supports_streaming = True

    def __init__(
        self,
        model_id: str,
        *,
        region: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        session_token: str | None = None,
        timeout_seconds: float = 60.0,
        client: Any | None = None,
    ) -> None:
        super().__init__(model_id, timeout_seconds=timeout_seconds)
        self.region = region
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.session_token = session_token
        self._client_override = client

    @classmethod
    def from_settings(cls, settings: Settings, *, client: Any | None = None) -> "BedrockProvider":
        return cls(
            settings.llmproxy_bedrock_runtime_model_id or settings.llmproxy_bedrock_model,
            region=settings.llmproxy_bedrock_region,
            access_key_id=settings.llmproxy_bedrock_access_key_id,
            secret_access_key=settings.llmproxy_bedrock_secret_access_key,
            session_token=settings.llmproxy_bedrock_session_token,
            timeout_seconds=settings.llmproxy_provider_timeout_seconds,
            client=client,
        )

    @staticmethod
    def _request_messages(messages: Sequence[object]) -> list[dict[str, str]]:
        payload: list[dict[str, str]] = []
        for message in messages:
            role = str(getattr(message, "role", "user"))
            if role == "system":
                role = "user"
            payload.append(
                {
                    "role": role,
                    "content": str(getattr(message, "content", "")),
                }
            )
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

    def _client(self) -> Any:
        if self._client_override is not None:
            return self._client_override
        region = self._require_config(self.region, field_name="llmproxy_bedrock_region")
        if not self.access_key_id or not self.secret_access_key:
            raise ProviderConfigurationError(
                "bedrock provider is missing required configuration: llmproxy_bedrock_access_key_id or llmproxy_bedrock_secret_access_key"
            )
        try:
            import boto3  # type: ignore
        except ImportError as exc:
            raise ProviderConfigurationError("boto3 is required for AWS Bedrock provider support") from exc

        session = boto3.session.Session(
            aws_access_key_id=self.access_key_id,
            aws_secret_access_key=self.secret_access_key,
            aws_session_token=self.session_token,
            region_name=region,
        )
        return session.client("bedrock-runtime")

    @staticmethod
    def _decode_payload(raw_payload: object) -> dict[str, Any]:
        if isinstance(raw_payload, bytes):
            return json.loads(raw_payload.decode("utf-8"))
        if isinstance(raw_payload, str):
            return json.loads(raw_payload)
        if isinstance(raw_payload, dict):
            return raw_payload
        raise TypeError("Unsupported Bedrock response payload type.")

    def _invoke_model_sync(self, payload: dict[str, object]) -> dict[str, Any]:
        client = self._client()
        response = client.invoke_model(
            modelId=self.model_id,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(payload).encode("utf-8"),
        )
        body = response["body"]
        raw_payload = body.read() if hasattr(body, "read") else body
        return self._decode_payload(raw_payload)

    async def chat(self, request: ChatCompletionRequest) -> dict[str, object]:
        payload = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": self._request_messages(request.messages),
        }
        raw_response = await asyncio.to_thread(self._invoke_model_sync, payload)

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
            "input_tokens": prompt_tokens,
            "output_tokens": completion_tokens,
            "finish_reason": str(raw_response.get("stop_reason", "stop")),
            "cost_estimate": cost_estimate,
            "raw_response": raw_response,
        }

    async def stream_chat(self, request: ChatCompletionRequest) -> AsyncIterator[dict[str, object]]:
        payload = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": self._request_messages(request.messages),
        }
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[dict[str, object] | BaseException | object] = asyncio.Queue()
        sentinel = object()

        def _producer() -> None:
            try:
                client = self._client()
                response = client.invoke_model_with_response_stream(
                    modelId=self.model_id,
                    contentType="application/json",
                    accept="application/json",
                    body=json.dumps(payload).encode("utf-8"),
                )
                stream = response.get("body", [])
                for event in stream:
                    chunk = event.get("chunk", {}) if isinstance(event, dict) else {}
                    raw_bytes = chunk.get("bytes", b"")
                    raw_chunk = self._decode_payload(raw_bytes)
                    chunk_type = raw_chunk.get("type")
                    usage = raw_chunk.get("usage") or {}
                    delta = ""
                    finish_reason = None
                    if chunk_type == "content_block_delta":
                        delta_obj = raw_chunk.get("delta") or {}
                        if delta_obj.get("type") == "text_delta":
                            delta = str(delta_obj.get("text", ""))
                    elif chunk_type == "message_delta":
                        delta_obj = raw_chunk.get("delta") or {}
                        finish_reason = delta_obj.get("stop_reason")
                    elif chunk_type == "message_stop":
                        finish_reason = "stop"
                    item = {
                        "model": str(raw_chunk.get("model", self.model_id)),
                        "delta": delta,
                        "finish_reason": finish_reason,
                        "input_tokens": int(usage.get("input_tokens", 0)),
                        "output_tokens": int(usage.get("output_tokens", 0)),
                        "raw_chunk": raw_chunk,
                    }
                    asyncio.run_coroutine_threadsafe(queue.put(item), loop).result()
            except Exception as exc:  # pragma: no cover - propagated to async consumer
                asyncio.run_coroutine_threadsafe(queue.put(exc), loop).result()
            finally:
                asyncio.run_coroutine_threadsafe(queue.put(sentinel), loop).result()

        Thread(target=_producer, daemon=True).start()

        while True:
            item = await queue.get()
            if item is sentinel:
                break
            if isinstance(item, BaseException):
                raise item
            yield item

    async def healthcheck(self) -> dict[str, object]:
        payload = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1,
            "temperature": 0,
            "messages": [{"role": "user", "content": "ping"}],
        }
        started_at = time()
        try:
            await asyncio.to_thread(self._invoke_model_sync, payload)
            return {
                "ok": True,
                "provider": self.provider_name,
                "model": self.model_id,
                "latency_ms": int((time() - started_at) * 1000),
            }
        except Exception as exc:
            return {
                "ok": False,
                "provider": self.provider_name,
                "model": self.model_id,
                "error": str(exc),
                "latency_ms": int((time() - started_at) * 1000),
            }
