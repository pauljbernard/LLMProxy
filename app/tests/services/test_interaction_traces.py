from datetime import datetime, timezone
from decimal import Decimal

from app.db.models import ModelResponse, RequestLog, RoutingDecisionRecord
from app.services.interaction_traces import (
    build_http_interaction_trace,
    build_request_interaction_traces,
    summarize_interaction_trace_protocols,
)


def test_build_request_interaction_traces_includes_llm_and_mcp() -> None:
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
            "model": "proxy-auto",
            "messages": [{"role": "user", "content": "Check status"}],
            "metadata": {
                "session_id": "sess_1",
                "traffic_origin": "interactive",
            },
        },
        created_at=created_at,
    )
    routing = RoutingDecisionRecord(
        id="rd_1",
        request_log_id="req_1",
        session_id="sess_1",
        policy_version="policy_v1",
        selected_provider="openai",
        selected_provider_family="OpenAI",
        selected_model="gpt-5.5",
        selected_mode="production",
        selected_pool_id="pool_a",
        selected_node_id="node_a",
        selected_node_role="execution",
        selected_balancing_strategy="session_affinity",
        selected_affinity_key="session_id",
        decision_rationale="Prefer primary provider.",
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
        provider_family="OpenAI",
        model="gpt-5.5",
        latency_ms=240,
        input_tokens=11,
        output_tokens=5,
        cost_estimate=Decimal("0.012300"),
        finish_reason="stop",
        response_json={
            "content": "Current cluster status is healthy.",
            "mcp_trace": [
                {
                    "server": "cluster",
                    "tool_name": "status_lookup",
                    "arguments": {"cluster": "prod"},
                    "result": {"status": "healthy"},
                }
            ],
        },
        response_role="selected_response",
        created_at=created_at,
    )

    traces = build_request_interaction_traces(
        request=request,
        routing_decisions=[routing],
        model_responses=[response],
    )

    assert len(traces) == 2
    assert traces[0]["protocol"] == "llm"
    assert traces[0]["routing"]["selected_pool_id"] == "pool_a"
    assert traces[1]["protocol"] == "mcp"
    assert traces[1]["tool_name"] == "status_lookup"
    assert traces[1]["parent_trace_id"] == traces[0]["trace_id"]
    assert summarize_interaction_trace_protocols(traces) == {"llm": 1, "mcp": 1}


def test_build_http_interaction_trace_supports_a2a_and_rest() -> None:
    a2a_trace = build_http_interaction_trace(
        protocol="a2a",
        operation="discovery_document",
        method="GET",
        endpoint="http://planner.test/.well-known/agent.json",
        success=True,
        status_code=200,
        latency_ms=45,
        peer="planner",
        response_payload={"name": "Planner Agent"},
    )
    rest_trace = build_http_interaction_trace(
        protocol="rest",
        operation="prediction_create",
        method="POST",
        endpoint="https://api.replicate.com/v1/predictions",
        success=True,
        status_code=201,
        latency_ms=320,
        request_payload={"model": "replicate/hello-world"},
        response_payload={"id": "pred_1"},
    )

    assert a2a_trace["protocol"] == "a2a"
    assert a2a_trace["peer"] == "planner"
    assert rest_trace["protocol"] == "rest"
    assert rest_trace["method"] == "POST"
    assert summarize_interaction_trace_protocols([a2a_trace, rest_trace]) == {"a2a": 1, "rest": 1}
