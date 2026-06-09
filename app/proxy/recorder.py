"""Persistence helpers for proxy runtime."""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.models import JudgeCritique, ModelResponse, RequestLog, RoutingDecisionRecord
from app.schemas.chat import ChatCompletionRequest
from app.schemas.routing import RoutingDecision


def generate_prefixed_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def record_request(
    session: Session,
    request: ChatCompletionRequest,
    classification: dict[str, str],
    *,
    effective_request: ChatCompletionRequest | None = None,
) -> RequestLog:
    effective = effective_request or request
    request_log = RequestLog(
        id=generate_prefixed_id("req"),
        session_id=request.metadata.session_id,
        external_request_id=None,
        requested_model=request.model,
        domain=classification["domain"],
        task_type=classification["task_type"],
        complexity=classification["complexity"],
        privacy_level=classification["privacy_level"],
        request_json=request.model_dump(mode="json"),
        effective_request_json=effective.model_dump(mode="json"),
    )
    session.add(request_log)
    return request_log


def record_routing_decision(
    session: Session,
    request_log_id: str,
    decision: RoutingDecision,
) -> RoutingDecisionRecord:
    record = RoutingDecisionRecord(
        id=decision.routing_decision_id,
        request_log_id=request_log_id,
        session_id=decision.session_id,
        policy_version=decision.policy_version,
        selected_provider=decision.selected_provider,
        selected_provider_family=decision.selected_provider_family,
        selected_model=decision.selected_model,
        selected_mode=decision.selected_mode,
        selected_entry_id=getattr(decision, "selected_entry_id", None),
        selected_pool_id=getattr(decision, "selected_pool_id", None),
        selected_node_id=getattr(decision, "selected_node_id", None),
        selected_node_role=getattr(decision, "selected_node_role", None),
        selected_node_labels_json=list(getattr(decision, "selected_node_labels", []) or []),
        selected_capacity_class=getattr(decision, "selected_capacity_class", None),
        selected_balancing_strategy=getattr(decision, "selected_balancing_strategy", None),
        selected_affinity_key=getattr(decision, "selected_affinity_key", None),
        decision_rationale=decision.decision_rationale,
        predicted_cost_class=decision.predicted_cost_class,
        predicted_latency_class=decision.predicted_latency_class,
        ranked_alternatives_json=[item.model_dump(mode="json") for item in decision.ranked_alternatives],
        fallback_chain_json=[item.model_dump(mode="json") for item in decision.fallback_chain],
    )
    session.add(record)
    return record


def record_model_response(
    session: Session,
    request_log_id: str,
    provider_result: dict[str, object],
    response_role: str = "teacher_candidate",
) -> ModelResponse:
    response = ModelResponse(
        id=generate_prefixed_id("resp"),
        request_log_id=request_log_id,
        provider=str(provider_result["provider"]),
        provider_family=str(provider_result["provider_family"]),
        model=str(provider_result["model"]),
        latency_ms=int(provider_result["latency_ms"]),
        input_tokens=int(provider_result["input_tokens"]),
        output_tokens=int(provider_result["output_tokens"]),
        cost_estimate=Decimal(str(provider_result["cost_estimate"])),
        finish_reason=str(provider_result["finish_reason"]),
        response_json=dict(provider_result["raw_response"]),
        response_role=response_role,
        created_at=datetime.now(timezone.utc),
    )
    session.add(response)
    return response


def record_judge_critique(
    session: Session,
    *,
    request_log_id: str,
    routing_decision_id: str,
    judge_provider: str,
    judge_model: str,
    selected_provider: str,
    selected_model: str,
    selected_response_id: str,
    critique_json: dict[str, object],
    synthesized_response: str,
) -> JudgeCritique:
    critique = JudgeCritique(
        id=generate_prefixed_id("judge"),
        request_log_id=request_log_id,
        routing_decision_id=routing_decision_id,
        judge_provider=judge_provider,
        judge_model=judge_model,
        selected_provider=selected_provider,
        selected_model=selected_model,
        selected_response_id=selected_response_id,
        critique_json=critique_json,
        synthesized_response=synthesized_response,
    )
    session.add(critique)
    return critique
