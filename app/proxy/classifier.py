"""Request classification helpers."""

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


def _validated_hint(value: str | None, *, allowed: set[str], fallback: str) -> str:
    if not value:
        return fallback
    normalized = value.strip().lower()
    return normalized if normalized in allowed else fallback


def classify_request(request: ChatCompletionRequest) -> dict[str, str]:
    combined_content = " ".join(message.content.lower() for message in request.messages)
    domain = _validated_hint(request.metadata.domain_hint, allowed=KNOWN_DOMAINS, fallback="general")
    task_type = _validated_hint(request.metadata.task_type_hint, allowed=KNOWN_TASK_TYPES, fallback="question_answer")
    complexity = "high" if len(combined_content.split()) > 120 else "medium"
    privacy_level = "private" if "secret" in combined_content or "private" in combined_content else "standard"
    return {
        "domain": domain,
        "task_type": task_type,
        "complexity": complexity,
        "privacy_level": privacy_level,
    }
