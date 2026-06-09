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


def test_router_scopes_policy_entries_by_listener_id() -> None:
    request = ChatCompletionRequest.model_validate(
        {
            "model": "proxy-auto",
            "messages": [{"role": "user", "content": "Research this topic"}],
            "metadata": {
                "session_id": "sess_listener",
                "listener_id": "internal-tools",
                "domain_hint": "research",
                "task_type_hint": "analysis",
            },
        }
    )
    classification = classify_request(request)
    policy_record = RoutingPolicyVersion(
        id="rpol_listener",
        policy_version="rpol_listener",
        policy_json={
            "entries": [
                {
                    "entry_type": "frontier",
                    "provider_key": "openai",
                    "provider_family": "OpenAI",
                    "model_id": "gpt-public",
                    "domains": ["research"],
                    "task_types": ["analysis"],
                    "listener_ids": ["public-api"],
                    "deployment_mode": "production",
                },
                {
                    "entry_type": "frontier",
                    "provider_key": "anthropic",
                    "provider_family": "Anthropic",
                    "model_id": "claude-internal",
                    "domains": ["research"],
                    "task_types": ["analysis"],
                    "listener_ids": ["internal-tools"],
                    "deployment_mode": "production",
                },
            ]
        },
    )

    selected_route = select_route(
        "req_listener",
        request,
        classification,
        Settings(),
        session=FakeSession(policy_record=policy_record),
    )

    assert selected_route.provider_key == "anthropic"
    assert selected_route.decision.selected_model == "claude-internal"


def test_router_honors_direct_access_for_configured_provider_model() -> None:
    request = ChatCompletionRequest.model_validate(
        {
            "model": "claude-sonnet-4-6",
            "messages": [{"role": "user", "content": "Answer directly with the requested model"}],
            "metadata": {"session_id": "sess_direct_provider", "domain_hint": "general"},
        }
    )
    classification = classify_request(request)

    selected_route = select_route(
        "req_direct_provider",
        request,
        classification,
        Settings(
            llmproxy_anthropic_api_key="test-anthropic-key",
            llmproxy_anthropic_model="claude-sonnet-4-6",
        ),
        session=FakeSession(
            policy_record=RoutingPolicyVersion(
                id="rpol_empty",
                policy_version="rpol_empty",
                policy_json={"entries": []},
            )
        ),
    )

    assert selected_route.provider_key == "anthropic"
    assert selected_route.decision.selected_model == "claude-sonnet-4-6"
    assert selected_route.decision.selected_mode == "production"


def test_router_prefers_explicit_requested_model_over_generic_domain_policy() -> None:
    request = ChatCompletionRequest.model_validate(
        {
            "model": "gpt-5",
            "messages": [{"role": "user", "content": "Use OpenAI directly"}],
            "metadata": {"session_id": "sess_direct_precedence", "domain_hint": "general"},
        }
    )
    classification = classify_request(request)
    policy_record = RoutingPolicyVersion(
        id="rpol_generic_vs_direct",
        policy_version="rpol_generic_vs_direct",
        policy_json={
            "entries": [
                {
                    "entry_type": "frontier",
                    "provider_key": "anthropic",
                    "provider_family": "Anthropic",
                    "model_id": "claude-sonnet-4-6",
                    "domains": ["general"],
                    "deployment_mode": "production",
                }
            ]
        },
    )

    selected_route = select_route(
        "req_direct_precedence",
        request,
        classification,
        Settings(
            llmproxy_openai_api_key="test-openai-key",
            llmproxy_openai_model="gpt-5",
            llmproxy_anthropic_api_key="test-anthropic-key",
            llmproxy_anthropic_model="claude-sonnet-4-6",
        ),
        session=FakeSession(policy_record=policy_record),
    )

    assert selected_route.provider_key == "openai"
    assert selected_route.decision.selected_model == "gpt-5"
    assert "Direct model access" in selected_route.decision.decision_rationale


def test_router_honors_discovered_non_default_provider_model_when_hint_is_available() -> None:
    request = ChatCompletionRequest.model_validate(
        {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "Use the discovered OpenAI model directly"}],
            "metadata": {"session_id": "sess_discovered_precedence", "domain_hint": "general"},
        }
    )
    classification = classify_request(request)
    policy_record = RoutingPolicyVersion(
        id="rpol_generic_vs_discovered",
        policy_version="rpol_generic_vs_discovered",
        policy_json={
            "entries": [
                {
                    "entry_type": "frontier",
                    "provider_key": "anthropic",
                    "provider_family": "Anthropic",
                    "model_id": "claude-sonnet-4-6",
                    "domains": ["general"],
                    "deployment_mode": "production",
                }
            ]
        },
    )

    selected_route = select_route(
        "req_discovered_precedence",
        request,
        classification,
        Settings(
            llmproxy_openai_api_key="test-openai-key",
            llmproxy_openai_model="gpt-5",
            llmproxy_anthropic_api_key="test-anthropic-key",
            llmproxy_anthropic_model="claude-sonnet-4-6",
        ),
        session=FakeSession(policy_record=policy_record),
        requested_model_provider_key="openai",
    )

    assert selected_route.provider_key == "openai"
    assert selected_route.decision.selected_model == "gpt-4o"
    assert "Direct model access" in selected_route.decision.decision_rationale


def test_router_honors_direct_access_for_local_policy_model_even_when_domain_differs() -> None:
    request = ChatCompletionRequest.model_validate(
        {
            "model": "coding-reviewer",
            "messages": [{"role": "user", "content": "Use the local reviewer directly"}],
            "metadata": {"session_id": "sess_direct_local", "domain_hint": "general"},
        }
    )
    classification = classify_request(request)
    policy_record = RoutingPolicyVersion(
        id="rpol_local_direct",
        policy_version="rpol_local_direct",
        policy_json={
            "entries": [
                {
                    "entry_type": "local",
                    "provider_key": "local:coding-reviewer",
                    "provider_family": "local runtime",
                    "model_alias": "coding-reviewer",
                    "domains": ["coding"],
                    "deployment_mode": "production",
                }
            ]
        },
    )

    selected_route = select_route(
        "req_direct_local",
        request,
        classification,
        Settings(),
        session=FakeSession(policy_record=policy_record),
    )

    assert selected_route.provider_key == "local:coding-reviewer"
    assert selected_route.decision.selected_model == "coding-reviewer"


def test_router_can_redirect_requested_model_to_different_target_model() -> None:
    request = ChatCompletionRequest.model_validate(
        {
            "model": "claude-3-5-sonnet",
            "messages": [{"role": "user", "content": "Route this deprecated model to the new target"}],
            "metadata": {"session_id": "sess_redirect", "domain_hint": "general"},
        }
    )
    classification = classify_request(request)
    policy_record = RoutingPolicyVersion(
        id="rpol_redirect",
        policy_version="rpol_redirect",
        policy_json={
            "entries": [
                {
                    "entry_type": "frontier",
                    "provider_key": "anthropic",
                    "provider_family": "Anthropic",
                    "model_id": "claude-sonnet-4-6",
                    "requested_models": ["claude-3-5-sonnet"],
                    "domains": ["general"],
                    "deployment_mode": "production",
                }
            ]
        },
    )

    selected_route = select_route(
        "req_redirect",
        request,
        classification,
        Settings(),
        session=FakeSession(policy_record=policy_record),
    )

    assert selected_route.provider_key == "anthropic"
    assert selected_route.decision.selected_model == "claude-sonnet-4-6"


def test_router_selects_matching_model_when_vendor_has_multiple_models() -> None:
    request = ChatCompletionRequest.model_validate(
        {
            "model": "gpt-5.5-mini",
            "messages": [{"role": "user", "content": "Use the smaller OpenAI model"}],
            "metadata": {"session_id": "sess_multi_model", "domain_hint": "general"},
        }
    )
    classification = classify_request(request)
    policy_record = RoutingPolicyVersion(
        id="rpol_multi_model",
        policy_version="rpol_multi_model",
        policy_json={
            "entries": [
                {
                    "entry_type": "frontier",
                    "provider_key": "openai",
                    "provider_family": "OpenAI",
                    "model_id": "gpt-5.5",
                    "domains": ["general"],
                    "deployment_mode": "production",
                },
                {
                    "entry_type": "frontier",
                    "provider_key": "openai",
                    "provider_family": "OpenAI",
                    "model_id": "gpt-5.5-mini",
                    "domains": ["general"],
                    "deployment_mode": "production",
                },
            ]
        },
    )

    selected_route = select_route(
        "req_multi_model",
        request,
        classification,
        Settings(),
        session=FakeSession(policy_record=policy_record),
    )

    assert selected_route.provider_key == "openai"
    assert selected_route.decision.selected_model == "gpt-5.5-mini"


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


def test_router_uses_configured_default_frontier_entries_without_hardcoded_branching() -> None:
    request = ChatCompletionRequest.model_validate(
        {
            "model": "test-routing-model",
            "messages": [{"role": "user", "content": "Investigate this architecture choice"}],
            "metadata": {"session_id": "sess_default_frontier", "domain_hint": "software_architecture", "task_type_hint": "analysis"},
        }
    )
    classification = classify_request(request)
    settings = Settings(
        llmproxy_xai_api_key="test-xai-key",
        llmproxy_frontier_default_entries=[
            {
                "entry_type": "frontier",
                "provider_key": "xai",
                "provider_family": "xAI",
                "model_id": "grok-3-mini",
                "domains": ["software_architecture"],
                "task_types": [],
                "deployment_mode": "production",
                "decision_rationale": "Configured xAI architecture route.",
            }
        ]
    )

    selected_route = select_route(
        "req_default_frontier",
        request,
        classification,
        settings,
        session=FakeSession(
            policy_record=RoutingPolicyVersion(
                id="rpol_empty",
                policy_version="rpol_empty",
                policy_json={"entries": []},
            )
        ),
    )

    assert selected_route.provider_key == "xai"
    assert selected_route.decision.selected_model == "grok-3-mini"
    assert selected_route.decision.decision_rationale == "Configured xAI architecture route."


def test_router_prefers_lower_cost_entry_when_strategy_is_cost() -> None:
    request = ChatCompletionRequest.model_validate(
        {
            "model": "proxy-auto",
            "messages": [{"role": "user", "content": "Answer a general question"}],
            "metadata": {"session_id": "sess_cost", "domain_hint": "general", "task_type_hint": "question_answer"},
        }
    )
    classification = classify_request(request)
    policy_record = RoutingPolicyVersion(
        id="rpol_frontier_cost",
        policy_version="rpol_frontier_cost",
        policy_json={
            "entries": [
                {
                    "entry_type": "frontier",
                    "provider_key": "openai",
                    "provider_family": "OpenAI",
                    "model_id": "gpt-5.5",
                    "domains": ["general"],
                    "deployment_mode": "production",
                    "quality_summary": {"overall_score": 0.95},
                    "price_per_token": 0.00002,
                },
                {
                    "entry_type": "frontier",
                    "provider_key": "deepseek",
                    "provider_family": "DeepSeek",
                    "model_id": "deepseek-v4-flash",
                    "domains": ["general"],
                    "deployment_mode": "production",
                    "quality_summary": {"overall_score": 0.90},
                    "price_per_token": 0.000002,
                },
            ]
        },
    )

    selected_route = select_route(
        "req_cost",
        request,
        classification,
        Settings(llmproxy_routing_strategy="cost"),
        session=FakeSession(policy_record=policy_record),
    )

    assert selected_route.provider_key == "deepseek"
    assert selected_route.decision.selected_model == "deepseek-v4-flash"


def test_router_prefers_lower_latency_entry_when_strategy_is_latency() -> None:
    request = ChatCompletionRequest.model_validate(
        {
            "model": "proxy-auto",
            "messages": [{"role": "user", "content": "Answer quickly"}],
            "metadata": {"session_id": "sess_latency", "domain_hint": "general", "task_type_hint": "question_answer"},
        }
    )
    classification = classify_request(request)
    policy_record = RoutingPolicyVersion(
        id="rpol_frontier_latency",
        policy_version="rpol_frontier_latency",
        policy_json={
            "entries": [
                {
                    "entry_type": "frontier",
                    "provider_key": "anthropic",
                    "provider_family": "Anthropic",
                    "model_id": "claude-3-5-sonnet",
                    "domains": ["general"],
                    "deployment_mode": "production",
                    "quality_summary": {"overall_score": 0.95},
                    "latency_ms": 240,
                },
                {
                    "entry_type": "frontier",
                    "provider_key": "groq",
                    "provider_family": "Groq",
                    "model_id": "llama-3.3-70b-versatile",
                    "domains": ["general"],
                    "deployment_mode": "production",
                    "quality_summary": {"overall_score": 0.90},
                    "latency_ms": 40,
                },
            ]
        },
    )

    selected_route = select_route(
        "req_latency",
        request,
        classification,
        Settings(llmproxy_routing_strategy="latency"),
        session=FakeSession(policy_record=policy_record),
    )

    assert selected_route.provider_key == "groq"
    assert selected_route.decision.selected_model == "llama-3.3-70b-versatile"


def test_router_prefers_tag_matched_entry() -> None:
    request = ChatCompletionRequest.model_validate(
        {
            "model": "proxy-auto",
            "messages": [{"role": "user", "content": "Use the finance-optimized route"}],
            "metadata": {
                "session_id": "sess_tags",
                "domain_hint": "general",
                "task_type_hint": "question_answer",
                "route_tags": ["finance", "priority"],
            },
        }
    )
    classification = classify_request(request)
    policy_record = RoutingPolicyVersion(
        id="rpol_tags",
        policy_version="rpol_tags",
        policy_json={
            "entries": [
                {
                    "entry_type": "frontier",
                    "provider_key": "openai",
                    "provider_family": "OpenAI",
                    "model_id": "gpt-5.5",
                    "domains": ["general"],
                    "deployment_mode": "production",
                    "quality_summary": {"overall_score": 0.95},
                },
                {
                    "entry_type": "frontier",
                    "provider_key": "groq",
                    "provider_family": "Groq",
                    "model_id": "llama-3.3-70b-versatile",
                    "domains": ["general"],
                    "tags": ["finance", "priority"],
                    "deployment_mode": "production",
                    "quality_summary": {"overall_score": 0.90},
                },
            ]
        },
    )

    selected_route = select_route(
        "req_tags",
        request,
        classification,
        Settings(),
        session=FakeSession(policy_record=policy_record),
    )

    assert selected_route.provider_key == "groq"


def test_router_prefers_region_matched_entry() -> None:
    request = ChatCompletionRequest.model_validate(
        {
            "model": "proxy-auto",
            "messages": [{"role": "user", "content": "Use the EU route"}],
            "metadata": {
                "session_id": "sess_region",
                "domain_hint": "general",
                "task_type_hint": "question_answer",
                "region_hint": "eu-west",
            },
        }
    )
    classification = classify_request(request)
    policy_record = RoutingPolicyVersion(
        id="rpol_regions",
        policy_version="rpol_regions",
        policy_json={
            "entries": [
                {
                    "entry_type": "frontier",
                    "provider_key": "openai",
                    "provider_family": "OpenAI",
                    "model_id": "gpt-5.5",
                    "domains": ["general"],
                    "deployment_mode": "production",
                    "quality_summary": {"overall_score": 0.95},
                },
                {
                    "entry_type": "frontier",
                    "provider_key": "mistral",
                    "provider_family": "Mistral",
                    "model_id": "mistral-large-latest",
                    "domains": ["general"],
                    "regions": ["eu-west"],
                    "deployment_mode": "production",
                    "quality_summary": {"overall_score": 0.90},
                },
            ]
        },
    )

    selected_route = select_route(
        "req_region",
        request,
        classification,
        Settings(),
        session=FakeSession(policy_record=policy_record),
    )

    assert selected_route.provider_key == "mistral"


def test_router_resolves_pooled_vendor_entry_with_session_affinity() -> None:
    request = ChatCompletionRequest.model_validate(
        {
            "model": "gpt-5.5",
            "messages": [{"role": "user", "content": "Use the scalable coding route"}],
            "metadata": {
                "session_id": "sess_pool",
                "domain_hint": "coding",
                "task_type_hint": "question_answer",
            },
        }
    )
    classification = classify_request(request)
    policy_record = RoutingPolicyVersion(
        id="rpol_pool",
        policy_version="rpol_pool",
        policy_json={
            "entries": [
                {
                    "entry_id": "entry_a",
                    "entry_type": "frontier",
                    "provider_key": "openai",
                    "provider_family": "OpenAI",
                    "model_id": "gpt-5.5",
                    "domains": ["coding"],
                    "deployment_mode": "production",
                    "endpoint_url": "http://child-a:8000/v1",
                    "node_id": "child-a",
                    "node_role": "execution",
                    "pool_id": "coding-east",
                    "pool_weight": 3,
                    "balancing_strategy": "session_affinity",
                    "affinity_key": "session_id",
                    "forward_request_metadata": True,
                },
                {
                    "entry_id": "entry_b",
                    "entry_type": "frontier",
                    "provider_key": "openai",
                    "provider_family": "OpenAI",
                    "model_id": "gpt-5.5",
                    "domains": ["coding"],
                    "deployment_mode": "production",
                    "endpoint_url": "http://child-b:8000/v1",
                    "node_id": "child-b",
                    "node_role": "execution",
                    "pool_id": "coding-east",
                    "pool_weight": 1,
                    "balancing_strategy": "session_affinity",
                    "affinity_key": "session_id",
                    "forward_request_metadata": True,
                },
            ]
        },
    )

    selected_route = select_route(
        "req_pool",
        request,
        classification,
        Settings(),
        session=FakeSession(policy_record=policy_record),
    )

    assert selected_route.provider_key == "openai"
    assert selected_route.decision.selected_pool_id == "coding-east"
    assert selected_route.decision.selected_balancing_strategy == "session_affinity"
    assert selected_route.decision.selected_affinity_key == "session_id"
    assert selected_route.decision.selected_node_id in {"child-a", "child-b"}
    assert selected_route.selected_entry["endpoint_url"] in {"http://child-a:8000/v1", "http://child-b:8000/v1"}


def test_router_builds_concrete_pool_fallback_chain() -> None:
    request = ChatCompletionRequest.model_validate(
        {
            "model": "gpt-5.5",
            "messages": [{"role": "user", "content": "Use the scalable coding route"}],
            "metadata": {
                "session_id": "sess_pool_fallback",
                "domain_hint": "coding",
                "task_type_hint": "question_answer",
            },
        }
    )
    classification = classify_request(request)
    policy_record = RoutingPolicyVersion(
        id="rpol_pool_fallback",
        policy_version="rpol_pool_fallback",
        policy_json={
            "entries": [
                {
                    "entry_id": "entry_a",
                    "entry_type": "frontier",
                    "provider_key": "openai",
                    "provider_family": "OpenAI",
                    "model_id": "gpt-5.5",
                    "domains": ["coding"],
                    "deployment_mode": "production",
                    "endpoint_url": "http://child-a:8000/v1",
                    "node_id": "child-a",
                    "node_role": "execution",
                    "pool_id": "coding-east",
                    "pool_weight": 3,
                    "balancing_strategy": "session_affinity",
                    "affinity_key": "session_id",
                    "forward_request_metadata": True,
                },
                {
                    "entry_id": "entry_b",
                    "entry_type": "frontier",
                    "provider_key": "openai",
                    "provider_family": "OpenAI",
                    "model_id": "gpt-5.5",
                    "domains": ["coding"],
                    "deployment_mode": "production",
                    "endpoint_url": "http://child-b:8000/v1",
                    "node_id": "child-b",
                    "node_role": "execution",
                    "pool_id": "coding-east",
                    "pool_weight": 1,
                    "balancing_strategy": "session_affinity",
                    "affinity_key": "session_id",
                    "forward_request_metadata": True,
                },
            ]
        },
    )

    selected_route = select_route(
        "req_pool_fallback",
        request,
        classification,
        Settings(),
        session=FakeSession(policy_record=policy_record),
    )

    fallback = selected_route.decision.fallback_chain[0]
    assert fallback.provider == "openai"
    assert fallback.model == "gpt-5.5"
    assert fallback.pool_id == "coding-east"
    assert fallback.entry_id in {"entry_a", "entry_b"}
    assert fallback.node_id in {"child-a", "child-b"}
    assert fallback.entry_id != selected_route.decision.selected_entry_id
    assert fallback.node_id != selected_route.decision.selected_node_id
