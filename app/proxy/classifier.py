"""Request classification helpers."""

import re

from app.schemas.chat import ChatCompletionRequest

KNOWN_DOMAINS = {
    "general",
    "coding",
    "software_architecture",
    "writing_style",
    "agent_systems",
    "research",
    "analysis",
}

KNOWN_TASK_TYPES = {
    "question_answer",
    "code_review",
    "design_review",
    "analysis",
}

PRIVATE_PATTERNS = (
    re.compile(r"\bprivate key\b"),
    re.compile(r"\bsecret key\b"),
    re.compile(r"\bapi key\b"),
    re.compile(r"\baccess token\b"),
    re.compile(r"\bauth token\b"),
    re.compile(r"\bpassword\b"),
    re.compile(r"\bcredential(s)?\b"),
    re.compile(r"\bconfidential\b"),
    re.compile(r"\bdo not share\b"),
    re.compile(r"\bssn\b"),
    re.compile(r"\bpassport number\b"),
    re.compile(r"\bpatient record\b"),
    re.compile(r"-----begin [a-z ]*private key-----"),
)


def _validated_hint(value: str | None, *, allowed: set[str], fallback: str) -> str:
    if not value:
        return fallback
    normalized = value.strip().lower()
    return normalized if normalized in allowed else fallback


def classify_request(request: ChatCompletionRequest) -> dict[str, str | list[str]]:
    combined_content = " ".join(message.content.lower() for message in request.messages)
    domain = _validated_hint(request.metadata.domain_hint, allowed=KNOWN_DOMAINS, fallback="general")
    task_type = _validated_hint(request.metadata.task_type_hint, allowed=KNOWN_TASK_TYPES, fallback="question_answer")
    complexity = "high" if len(combined_content.split()) > 120 else "medium"
    route_tags = [str(item).strip().lower() for item in (request.metadata.route_tags or []) if str(item).strip()]
    region = str(request.metadata.region_hint).strip().lower() if request.metadata.region_hint else ""
    if request.metadata.privacy_hint is True:
        privacy_level = "private"
    elif request.metadata.privacy_hint is False:
        privacy_level = "standard"
    else:
        privacy_level = "private" if any(pattern.search(combined_content) for pattern in PRIVATE_PATTERNS) else "standard"
    return {
        "domain": domain,
        "task_type": task_type,
        "complexity": complexity,
        "privacy_level": privacy_level,
        "region": region,
        "route_tags": route_tags,
    }
