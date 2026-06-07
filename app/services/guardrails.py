"""Guardrail hook framework for request/response processing."""

from __future__ import annotations

import inspect
import re
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException, status

from app.api.dependencies import AuthPrincipal
from app.config import Settings
from app.schemas.chat import ChatCompletionRequest

_PROMPT_INJECTION_PATTERNS = (
    re.compile(r"\bignore (all|any|the) previous instructions\b", re.IGNORECASE),
    re.compile(r"\breveal (the )?(system|developer) prompt\b", re.IGNORECASE),
    re.compile(r"\bbypass (safety|guardrails|policy)\b", re.IGNORECASE),
    re.compile(r"\bpretend to be the system\b", re.IGNORECASE),
)

_PII_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("email", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)),
    ("phone", re.compile(r"\b(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")),
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("credit_card", re.compile(r"\b(?:\d[ -]*?){13,16}\b")),
)


@dataclass
class GuardrailContext:
    settings: Settings
    request: ChatCompletionRequest
    classification: dict[str, Any]
    principal: AuthPrincipal
    provider_result: dict[str, Any] | None = None
    annotations: dict[str, Any] = field(default_factory=dict)

    @property
    def request_text(self) -> str:
        parts: list[str] = []
        for message in self.request.messages:
            content = getattr(message, "content", "")
            if isinstance(content, str):
                parts.append(content)
        return "\n".join(parts).strip()

    @property
    def response_text(self) -> str:
        if not self.provider_result:
            return ""
        return str(self.provider_result.get("content", ""))


async def _run_hook(hook, context: GuardrailContext) -> None:
    result = hook(context)
    if inspect.isawaitable(result):
        await result


def _mask_text(value: str) -> tuple[str, list[str]]:
    masked = value
    matches: list[str] = []
    for label, pattern in _PII_PATTERNS:
        if pattern.search(masked):
            matches.append(label)
            masked = pattern.sub(f"[REDACTED_{label.upper()}]", masked)
    return masked, sorted(set(matches))


async def built_in_pre_guardrail(context: GuardrailContext) -> None:
    text = context.request_text
    prompt_injection = any(pattern.search(text) for pattern in _PROMPT_INJECTION_PATTERNS)
    if prompt_injection:
        context.annotations["prompt_injection_suspected"] = True
        if context.settings.llmproxy_guardrail_block_prompt_injection:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Guardrail blocked a suspected prompt-injection attempt.",
            )

    pii_labels: list[str] = []
    for label, pattern in _PII_PATTERNS:
        if pattern.search(text):
            pii_labels.append(label)
    if pii_labels:
        context.annotations["input_pii_types"] = sorted(set(pii_labels))


async def built_in_post_guardrail(context: GuardrailContext) -> None:
    if context.provider_result is None:
        return
    content = str(context.provider_result.get("content", ""))
    blocked_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in context.settings.llmproxy_guardrail_blocked_output_patterns]
    for pattern in blocked_patterns:
        if pattern.search(content):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Guardrail blocked provider output that matched a restricted pattern.",
            )

    masked, pii_labels = _mask_text(content)
    if pii_labels:
        context.annotations["output_pii_types"] = pii_labels
        if context.settings.llmproxy_guardrail_mask_pii_output:
            context.provider_result["content"] = masked


async def run_pre_guardrails(context: GuardrailContext) -> None:
    await _run_hook(built_in_pre_guardrail, context)
    for path in context.settings.llmproxy_guardrail_pre_hooks:
        await _run_hook(context.settings._resolve_dotted_callable(path), context)


async def run_post_guardrails(context: GuardrailContext) -> None:
    await _run_hook(built_in_post_guardrail, context)
    for path in context.settings.llmproxy_guardrail_post_hooks:
        await _run_hook(context.settings._resolve_dotted_callable(path), context)
