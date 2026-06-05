"""Request classification helpers."""

from app.schemas.chat import ChatCompletionRequest


def classify_request(request: ChatCompletionRequest) -> dict[str, str]:
    combined_content = " ".join(message.content.lower() for message in request.messages)
    domain = request.metadata.domain_hint or "general"
    task_type = request.metadata.task_type_hint or "question_answer"
    complexity = "high" if len(combined_content.split()) > 120 else "medium"
    privacy_level = "private" if "secret" in combined_content or "private" in combined_content else "standard"
    return {
        "domain": domain,
        "task_type": task_type,
        "complexity": complexity,
        "privacy_level": privacy_level,
    }
