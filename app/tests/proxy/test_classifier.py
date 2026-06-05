from app.proxy.classifier import classify_request
from app.proxy.router import select_route
from app.schemas.chat import ChatCompletionRequest
from app.config import Settings


def test_classifier_marks_private_requests() -> None:
    request = ChatCompletionRequest.model_validate(
        {
            "model": "proxy-auto",
            "messages": [{"role": "user", "content": "This is a private secret architecture note."}],
            "metadata": {"session_id": "sess_123", "domain_hint": "software_architecture"},
        }
    )

    classification = classify_request(request)

    assert classification["privacy_level"] == "private"
    assert classification["domain"] == "software_architecture"


def test_router_selects_local_for_private_requests() -> None:
    request = ChatCompletionRequest.model_validate(
        {
            "model": "proxy-auto",
            "messages": [{"role": "user", "content": "This is a private secret architecture note."}],
            "metadata": {"session_id": "sess_123", "domain_hint": "software_architecture"},
        }
    )

    classification = classify_request(request)
    selected_route = select_route("req_123", request, classification, Settings())

    assert selected_route.provider_key == "ollama"
    assert selected_route.decision.selected_mode == "local_only"
