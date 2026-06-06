from app.proxy.classifier import classify_request
from app.proxy.router import select_route
from app.schemas.chat import ChatCompletionRequest
from app.config import Settings
from app.db.models import RoutingPolicyVersion


class FakeScalarResult:
    def __init__(self, items):
        self._items = items

    def first(self):
        return self._items[0] if self._items else None

    def scalars(self):
        return self


class FakeExecuteResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return FakeScalarResult(self._items)


class FakeSession:
    def __init__(self, policy_record=None) -> None:
        self.policy_record = policy_record

    def execute(self, statement):
        text = str(statement)
        if "routing_policy_version" in text and self.policy_record is not None:
            return FakeExecuteResult([self.policy_record])
        return FakeExecuteResult([])


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
    assert selected_route.decision.fallback_chain == []


def test_router_records_loaded_policy_version() -> None:
    request = ChatCompletionRequest.model_validate(
        {
            "model": "proxy-auto",
            "messages": [{"role": "user", "content": "General question"}],
            "metadata": {"session_id": "sess_456", "domain_hint": "general"},
        }
    )
    classification = classify_request(request)
    policy_record = RoutingPolicyVersion(
        id="rpol_1",
        policy_version="rpol_1",
        policy_json={"entries": []},
    )

    selected_route = select_route(
        "req_456",
        request,
        classification,
        Settings(),
        session=FakeSession(policy_record=policy_record),
    )

    assert selected_route.decision.policy_version == "rpol_1"
