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
            "messages": [{"role": "user", "content": "This contains a private key for the architecture service."}],
            "metadata": {"session_id": "sess_123", "domain_hint": "software_architecture"},
        }
    )

    classification = classify_request(request)

    assert classification["privacy_level"] == "private"
    assert classification["domain"] == "software_architecture"


def test_classifier_does_not_mark_private_method_as_sensitive() -> None:
    request = ChatCompletionRequest.model_validate(
        {
            "model": "proxy-auto",
            "messages": [{"role": "user", "content": "Refactor this private method in a repository service."}],
            "metadata": {"session_id": "sess_234", "domain_hint": "coding"},
        }
    )

    classification = classify_request(request)

    assert classification["privacy_level"] == "standard"


def test_classifier_respects_explicit_privacy_hint() -> None:
    request = ChatCompletionRequest.model_validate(
        {
            "model": "proxy-auto",
            "messages": [{"role": "user", "content": "Rotate this API key immediately."}],
            "metadata": {"session_id": "sess_345", "domain_hint": "coding", "privacy_hint": False},
        }
    )

    classification = classify_request(request)

    assert classification["privacy_level"] == "standard"


def test_router_selects_local_for_private_requests() -> None:
    request = ChatCompletionRequest.model_validate(
        {
            "model": "proxy-auto",
            "messages": [{"role": "user", "content": "This contains a private key for the architecture service."}],
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


def test_router_prefers_frontier_policy_entry_over_hardcoded_default() -> None:
    request = ChatCompletionRequest.model_validate(
        {
            "model": "proxy-auto",
            "messages": [{"role": "user", "content": "Research this topic"}],
            "metadata": {"session_id": "sess_frontier", "domain_hint": "research", "task_type_hint": "analysis"},
        }
    )
    classification = classify_request(request)
    policy_record = RoutingPolicyVersion(
        id="rpol_frontier",
        policy_version="rpol_frontier",
        policy_json={
            "entries": [
                {
                    "entry_type": "frontier",
                    "provider_key": "openai",
                    "provider_family": "OpenAI",
                    "model_id": "gpt-frontier-research",
                    "domains": ["research"],
                    "task_types": ["analysis"],
                    "deployment_mode": "production",
                }
            ]
        },
    )

    selected_route = select_route(
        "req_frontier",
        request,
        classification,
        Settings(),
        session=FakeSession(policy_record=policy_record),
    )

    assert selected_route.provider_key == "openai"
    assert selected_route.decision.selected_model == "gpt-frontier-research"
    assert selected_route.decision.policy_version == "rpol_frontier"


def test_router_prefers_more_specific_local_entry() -> None:
    request = ChatCompletionRequest.model_validate(
        {
            "model": "test-routing-model",
            "messages": [{"role": "user", "content": "Review this code diff"}],
            "metadata": {"session_id": "sess_specific", "domain_hint": "coding", "task_type_hint": "code_review"},
        }
    )
    classification = classify_request(request)
    policy_record = RoutingPolicyVersion(
        id="rpol_local_specific",
        policy_version="rpol_local_specific",
        policy_json={
            "entries": [
                {
                    "entry_type": "local",
                    "provider_key": "local:coding-general",
                    "provider_family": "local runtime",
                    "model_alias": "coding-general",
                    "domains": ["coding"],
                    "deployment_mode": "production",
                    "quality_summary": {"overall_score": 0.80},
                },
                {
                    "entry_type": "local",
                    "provider_key": "local:coding-reviewer",
                    "provider_family": "local runtime",
                    "model_alias": "coding-reviewer",
                    "domains": ["coding"],
                    "task_types": ["code_review"],
                    "deployment_mode": "production",
                    "quality_summary": {"overall_score": 0.70},
                },
            ]
        },
    )

    selected_route = select_route(
        "req_specific",
        request,
        classification,
        Settings(),
        session=FakeSession(policy_record=policy_record),
    )

    assert selected_route.provider_key == "local:coding-reviewer"
    assert selected_route.decision.selected_provider == "local:coding-reviewer"
    assert selected_route.decision.selected_model == "coding-reviewer"


def test_router_prefers_higher_quality_local_entry_when_specificity_ties() -> None:
    request = ChatCompletionRequest.model_validate(
        {
            "model": "test-routing-model",
            "messages": [{"role": "user", "content": "Write a Python helper"}],
            "metadata": {"session_id": "sess_quality", "domain_hint": "coding", "task_type_hint": "generation"},
        }
    )
    classification = classify_request(request)
    policy_record = RoutingPolicyVersion(
        id="rpol_local_quality",
        policy_version="rpol_local_quality",
        policy_json={
            "entries": [
                {
                    "entry_type": "local",
                    "provider_key": "local:coding-low",
                    "provider_family": "local runtime",
                    "model_alias": "coding-low",
                    "domains": ["coding"],
                    "deployment_mode": "production",
                    "quality_summary": {"overall_score": 0.81},
                },
                {
                    "entry_type": "local",
                    "provider_key": "local:coding-high",
                    "provider_family": "local runtime",
                    "model_alias": "coding-high",
                    "domains": ["coding"],
                    "deployment_mode": "production",
                    "quality_summary": {"overall_score": 0.92},
                },
            ]
        },
    )

    selected_route = select_route(
        "req_quality",
        request,
        classification,
        Settings(),
        session=FakeSession(policy_record=policy_record),
    )

    assert selected_route.provider_key == "local:coding-high"
    assert selected_route.decision.selected_model == "coding-high"
