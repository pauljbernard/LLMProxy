from datetime import datetime, timezone
from decimal import Decimal

from app.db.models import ModelResponse, RoutingDecisionRecord, RoutingPolicyVersion
from app.services import routing_topology


class _FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def __iter__(self):
        return iter(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    def __init__(self, policy_versions, routing_decisions, model_responses) -> None:
        self.policy_versions = policy_versions
        self.routing_decisions = routing_decisions
        self.model_responses = model_responses

    def execute(self, statement):
        entity = statement.column_descriptions[0]["entity"]
        if entity is RoutingPolicyVersion:
            return _FakeScalarResult(self.policy_versions)
        if entity is RoutingDecisionRecord:
            return _FakeScalarResult(self.routing_decisions)
        if entity is ModelResponse:
            return _FakeScalarResult(self.model_responses)
        raise AssertionError(f"Unexpected entity: {entity}")


def test_build_routing_topology_inventory_includes_runtime_signals(monkeypatch) -> None:
    created_at = datetime.now(timezone.utc)
    policy = RoutingPolicyVersion(
        id="rpol_live",
        policy_version="rpol_live",
        policy_json={
            "entries": [
                {
                    "entry_id": "rpentry_1",
                    "provider_key": "openai",
                    "model_id": "gpt-5.5",
                    "deployment_mode": "production",
                    "node_id": "node-east-1",
                    "node_role": "execution",
                    "capacity_class": "gpu-large",
                    "node_labels": ["gpu", "east"],
                    "pool_id": "east-pool",
                    "pool_weight": 2,
                    "balancing_strategy": "session_affinity",
                    "affinity_key": "session_id",
                    "supports_local_models": True,
                    "supports_training": False,
                }
            ]
        },
        created_at=created_at,
    )
    decision = RoutingDecisionRecord(
        id="rd_1",
        request_log_id="req_1",
        session_id="sess_1",
        policy_version="rpol_live",
        selected_provider="openai",
        selected_provider_family="openai",
        selected_model="gpt-5.5",
        selected_mode="production",
        selected_pool_id="east-pool",
        selected_node_id="node-east-1",
        selected_node_role="execution",
        selected_capacity_class="gpu-large",
        selected_balancing_strategy="session_affinity",
        selected_affinity_key="session_id",
        selected_node_labels_json=["gpu", "east"],
        decision_rationale="best",
        predicted_cost_class="medium",
        predicted_latency_class="low",
        ranked_alternatives_json=[],
        fallback_chain_json=[],
        created_at=created_at,
    )
    response = ModelResponse(
        id="resp_1",
        request_log_id="req_1",
        provider="openai",
        provider_family="openai",
        model="gpt-5.5",
        latency_ms=42,
        input_tokens=100,
        output_tokens=50,
        cost_estimate=Decimal("0.10"),
        finish_reason="stop",
        response_json={},
        response_role="assistant",
        created_at=created_at,
    )
    monkeypatch.setattr(
        routing_topology,
        "provider_health_snapshot",
        lambda: {"openai": {"cooled_down": True}},
    )
    session = _FakeSession([policy], [decision], [response])

    payload = routing_topology.build_routing_topology_inventory(session)

    assert payload["policy_version"] == "rpol_live"
    assert payload["summary"]["node_count"] == 1
    assert payload["summary"]["cooled_node_count"] == 1
    assert payload["nodes"][0]["node_id"] == "node-east-1"
    assert payload["nodes"][0]["recent_request_count"] == 1
    assert payload["nodes"][0]["successful_request_count"] == 1
    assert payload["nodes"][0]["avg_latency_ms"] == 42
    assert payload["nodes"][0]["cooled_down"] is True
    assert payload["pools"][0]["pool_id"] == "east-pool"
    assert payload["pools"][0]["recent_request_count"] == 1
    assert payload["pools"][0]["avg_latency_ms"] == 42
