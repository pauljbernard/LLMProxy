"""Cloudflare Workers AI native provider implementation."""

from collections.abc import AsyncIterator, Sequence
import json
from time import time

from app.config import Settings
from app.providers.base import BaseProvider
from app.services.cost import estimate_cost_usd
from app.schemas.chat import ChatCompletionRequest


class CloudflareWorkersAIProvider(BaseProvider):
    provider_family = "Cloudflare Workers AI"
    provider_name = "cloudflare_workers_ai"
    price_per_token = 0.000004
    supports_streaming = True
    supports_tools = False

    def __init__(
        self,
        model_id: str,
        *,
        account_id: str | None = None,
        api_token: str | None = None,
        base_url: str = "https://api.cloudflare.com/client/v4",
        gateway_id: str | None = None,
        timeout_seconds: float = 60.0,
        transport=None,
    ) -> None:
        super().__init__(model_id, timeout_seconds=timeout_seconds, transport=transport)
        self.account_id = account_id
        self.api_token = api_token
        self.base_url = base_url.rstrip("/")
        self.gateway_id = gateway_id

    @classmethod
    def from_settings(cls, settings: Settings, *, transport=None) -> "CloudflareWorkersAIProvider":
        return cls(
            settings.llmproxy_cloudflare_workers_ai_model,
            account_id=settings.llmproxy_cloudflare_account_id,
            api_token=settings.llmproxy_cloudflare_api_token,
            base_url=settings.llmproxy_cloudflare_base_url,
            gateway_id=settings.llmproxy_cloudflare_gateway_id,
            timeout_seconds=settings.llmproxy_provider_timeout_seconds,
            transport=transport,
        )

    @property
    def capability(self):
        capability = super().capability
        capability.max_context_tokens = 128_000
        capability.max_output_tokens = 8_192
        return capability

    @staticmethod
    def _request_messages(messages: Sequence[object]) -> list[dict[str, object]]:
        payload: list[dict[str, object]] = []
        for message in messages:
            payload.append(
                {
                    "role": str(getattr(message, "role", "user")),
                    "content": getattr(message, "content", ""),
                }
            )
        return payload

    @staticmethod
    def _request_payload(request: ChatCompletionRequest) -> dict[str, object]:
        payload: dict[str, object] = {
            "messages": CloudflareWorkersAIProvider._request_messages(request.messages),
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": False,
        }
        passthrough_fields = (
            "top_p",
            "stop",
            "presence_penalty",
            "frequency_penalty",
            "seed",
            "logit_bias",
            "logprobs",
            "top_logprobs",
        )
        for field_name in passthrough_fields:
            value = getattr(request, field_name)
            if value is not None:
                payload[field_name] = value
        if request.response_format is not None:
            payload["response_format"] = request.response_format.model_dump(mode="json")
        return payload

    def _headers(self) -> dict[str, str]:
        account_id = self._require_config(self.account_id, field_name="llmproxy_cloudflare_account_id")
        api_token = self._require_config(self.api_token, field_name="llmproxy_cloudflare_api_token")
        headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
            "X-Cloudflare-Account-Id": account_id,
        }
        if self.gateway_id:
            headers["cf-aig-gateway-id"] = self.gateway_id
        return headers

    def _path(self) -> str:
        account_id = self._require_config(self.account_id, field_name="llmproxy_cloudflare_account_id")
        return f"/accounts/{account_id}/ai/run/{self.model_id}"

    @staticmethod
    def _extract_content(result: object) -> str:
        if isinstance(result, dict):
            response = result.get("response")
            if isinstance(response, str):
                return response
            if isinstance(response, dict):
                return json.dumps(response)
        if isinstance(result, str):
            return result
        return ""

    @staticmethod
    def _extract_usage(result: object) -> tuple[int, int]:
        if not isinstance(result, dict):
            return 0, 0
        usage = result.get("usage") or {}
        if not isinstance(usage, dict):
            return 0, 0
        return int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))

    async def chat(self, request: ChatCompletionRequest) -> dict[str, object]:
        payload = self._request_payload(request)
        headers = self._headers()
        async with self._client(
            base_url=self.base_url,
            headers=headers,
            timeout_seconds=self._timeout_for_request(request),
        ) as client:
            response = await client.post(self._path(), json=payload)
            response.raise_for_status()
            raw_response = response.json()

        result = raw_response.get("result", {})
        prompt_tokens, completion_tokens = self._extract_usage(result)
        cost_estimate = estimate_cost_usd(
            provider_name=self.provider_name,
            model_id=self.model_id,
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
        )
        return {
            "model": self.model_id,
            "content": self._extract_content(result),
            "input_tokens": prompt_tokens,
            "output_tokens": completion_tokens,
            "finish_reason": "stop",
            "cost_estimate": cost_estimate,
            "raw_response": raw_response,
        }

    async def stream_chat(self, request: ChatCompletionRequest) -> AsyncIterator[dict[str, object]]:
        payload = self._request_payload(request)
        payload["stream"] = True
        headers = self._headers()
        async with self._client(
            base_url=self.base_url,
            headers=headers,
            timeout_seconds=self._timeout_for_request(request),
        ) as client:
            async with client.stream("POST", self._path(), json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    payload_text = line[6:].strip()
                    if payload_text == "[DONE]":
                        break
                    raw_chunk = json.loads(payload_text)
                    result = raw_chunk.get("result", {})
                    prompt_tokens, completion_tokens = self._extract_usage(result)
                    yield {
                        "model": self.model_id,
                        "delta": self._extract_content(result),
                        "finish_reason": raw_chunk.get("finish_reason"),
                        "input_tokens": prompt_tokens,
                        "output_tokens": completion_tokens,
                        "raw_chunk": raw_chunk,
                    }

    async def healthcheck(self) -> dict[str, object]:
        payload = {
            "messages": [{"role": "user", "content": "ping"}],
            "temperature": 0,
            "max_tokens": 1,
            "stream": False,
        }
        headers = self._headers()
        started_at = time()
        try:
            async with self._client(
                base_url=self.base_url,
                headers=headers,
                timeout_seconds=3.0,
            ) as client:
                response = await client.post(self._path(), json=payload)
            return {
                "ok": response.status_code < 500,
                "provider": self.provider_name,
                "model": self.model_id,
                "status_code": response.status_code,
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
