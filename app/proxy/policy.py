"""Routing policy helpers."""

from app.schemas.routing import FallbackTarget, RankedAlternative, RoutingDecision

POLICY_VERSION = "1.0.0"


def policy_version() -> str:
    return POLICY_VERSION


def build_routing_decision(
    *,
    request_id: str,
    session_id: str,
    selected_provider: str,
    selected_provider_family: str,
    selected_model: str,
    selected_mode: str,
    rationale: str,
    predicted_cost_class: str,
    predicted_latency_class: str,
    ranked_alternatives: list[RankedAlternative],
    fallback_chain: list[FallbackTarget],
) -> RoutingDecision:
    return RoutingDecision(
        routing_decision_id=f"route_{request_id.split('_', 1)[-1]}",
        session_id=session_id,
        request_id=request_id,
        policy_version=policy_version(),
        selected_provider=selected_provider,
        selected_provider_family=selected_provider_family,
        selected_model=selected_model,
        selected_mode=selected_mode,
        ranked_alternatives=ranked_alternatives,
        decision_rationale=rationale,
        predicted_cost_class=predicted_cost_class,
        predicted_latency_class=predicted_latency_class,
        fallback_chain=fallback_chain,
    )
