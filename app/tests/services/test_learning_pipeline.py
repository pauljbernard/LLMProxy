from datetime import datetime, timezone
from decimal import Decimal

from app.api.dependencies import AuthPrincipal
from app.db.models import ModelResponse, RequestLog, RoutingDecisionRecord, VirtualAPIKey
from app.schemas.chat import ChatCompletionRequest
from app.services.learning_pipeline import (
    build_learning_pipeline_traffic_summary,
    learning_pipeline_request_summary_payload,
    enrich_request_for_principal,
    learning_pipeline_scope_from_owner,
    principal_traffic_context,
    request_automation_owner_id,
    request_automation_scope,
    request_traffic_origin,
)


def test_learning_pipeline_scope_from_owner() -> None:
    assert learning_pipeline_scope_from_owner("train_123") == "training"
    assert learning_pipeline_scope_from_owner("eval_123") == "evaluation"
    assert learning_pipeline_scope_from_owner("org_123") is None


def test_principal_traffic_context_marks_learning_pipeline() -> None:
    principal = AuthPrincipal(
        token="token",
        role="automation",
        key_id="vkey_1",
        owner_id="train_123",
    )
    payload = principal_traffic_context(principal)
    assert payload["traffic_origin"] == "learning_pipeline"
    assert payload["automation_scope"] == "training"
    assert payload["virtual_key_id"] == "vkey_1"


def test_enrich_request_for_principal_adds_metadata() -> None:
    principal = AuthPrincipal(
        token="token",
        role="automation",
        key_id="vkey_1",
        owner_id="eval_123",
    )
    request = ChatCompletionRequest.model_validate(
        {
            "model": "proxy-auto",
            "messages": [{"role": "user", "content": "hello"}],
        }
    )

    enriched = enrich_request_for_principal(request, principal)

    assert enriched.metadata.traffic_origin == "learning_pipeline"
    assert enriched.metadata.automation_scope == "evaluation"
    assert enriched.metadata.automation_owner_id == "eval_123"
    assert enriched.metadata.virtual_key_id == "vkey_1"
    assert request.metadata.traffic_origin is None


def test_request_metadata_helpers_read_request_json() -> None:
    request = RequestLog(
        id="req_1",
        session_id="sess_1",
        requested_model="proxy-auto",
        domain="coding",
        task_type="analysis",
        complexity="medium",
        privacy_level="standard",
        request_json={
            "metadata": {
                "traffic_origin": "learning_pipeline",
                "automation_scope": "training",
                "automation_owner_id": "train_123",
            }
        },
        created_at=datetime.now(timezone.utc),
    )

    assert request_traffic_origin(request) == "learning_pipeline"
    assert request_automation_scope(request) == "training"
    assert request_automation_owner_id(request) == "train_123"


def test_learning_pipeline_request_summary_includes_prompt_lineage() -> None:
    request = RequestLog(
        id="req_prompt_1",
        session_id="sess_prompt_1",
        requested_model="proxy-auto",
        domain="coding",
        task_type="analysis",
        complexity="medium",
        privacy_level="standard",
        request_json={
            "model": "proxy-auto",
            "metadata": {
                "prompt_template_name": "architecture_review",
                "prompt_template_version": 3,
                "traffic_origin": "learning_pipeline",
            },
        },
        effective_request_json={
            "model": "gpt-5",
            "metadata": {
                "prompt_template_render_hash": "abc123",
            },
        },
        created_at=datetime.now(timezone.utc),
    )

    payload = learning_pipeline_request_summary_payload(request)

    assert payload["requested_model"] == "proxy-auto"
    assert payload["effective_model"] == "gpt-5"
    assert payload["prompt_template_name"] == "architecture_review"
    assert payload["prompt_template_version"] == 3
    assert payload["prompt_template_render_hash"] == "abc123"


class _FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def __iter__(self):
        return iter(self._rows)


class _FakeLearningPipelineSession:
    def __init__(self, requests, responses, virtual_keys, routing_decisions) -> None:
        self.requests = requests
        self.responses = responses
        self.virtual_keys = virtual_keys
        self.routing_decisions = routing_decisions

    def execute(self, statement):
        entity = statement.column_descriptions[0]["entity"]
        if entity is VirtualAPIKey:
            return _FakeScalarResult(self.virtual_keys)
        if entity is RequestLog:
            return _FakeScalarResult(self.requests)
        if entity is ModelResponse:
            return _FakeScalarResult(self.responses)
        if entity is RoutingDecisionRecord:
            return _FakeScalarResult(self.routing_decisions)
        raise AssertionError(f"Unexpected entity: {entity}")


def test_build_learning_pipeline_traffic_summary_includes_topology_fields() -> None:
    created_at = datetime.now(timezone.utc)
    request = RequestLog(
        id="req_1",
        session_id="sess_1",
        requested_model="proxy-auto",
        domain="coding",
        task_type="analysis",
        complexity="medium",
        privacy_level="standard",
        request_json={
            "metadata": {
                "traffic_origin": "learning_pipeline",
                "automation_scope": "training",
                "automation_owner_id": "train_123",
                "virtual_key_id": "vkey_1",
            }
        },
        created_at=created_at,
    )
    response = ModelResponse(
        id="resp_1",
        request_log_id="req_1",
        provider="openai",
        provider_family="openai",
        model="gpt-5.5",
        response_json={},
        input_tokens=100,
        output_tokens=50,
        cost_estimate=Decimal("0.10"),
        created_at=created_at,
    )
    virtual_key = VirtualAPIKey(
        id="vkey_1",
        key_hash="hash",
        key_prefix="sk-train",
        role="automation",
        owner_id="train_123",
        status="active",
        spend_usd=Decimal("0.15"),
        created_at=created_at,
    )
    routing_decision = RoutingDecisionRecord(
        id="rd_1",
        request_log_id="req_1",
        policy_version="policy_v1",
        selected_provider="openai",
        selected_provider_family="openai",
        selected_model="gpt-5.5",
        selected_mode="production",
        selected_pool_id="east-pool",
        selected_node_id="node-east-1",
        selected_node_role="execution",
        selected_balancing_strategy="session_affinity",
        selected_affinity_key="session_id",
        created_at=created_at,
    )
    session = _FakeLearningPipelineSession([request], [response], [virtual_key], [routing_decision])

    payload = build_learning_pipeline_traffic_summary(session, owner_id="train_123")

    assert payload["request_count"] == 1
    assert payload["recent_requests"][0]["selected_pool_id"] == "east-pool"
    assert payload["recent_requests"][0]["selected_node_id"] == "node-east-1"
    assert payload["recent_requests"][0]["selected_balancing_strategy"] == "session_affinity"
