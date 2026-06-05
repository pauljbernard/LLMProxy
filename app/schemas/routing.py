"""Routing schemas."""

from pydantic import BaseModel


class RankedAlternative(BaseModel):
    rank: int
    provider: str
    model: str
    score: float


class FallbackTarget(BaseModel):
    order: int
    provider: str
    model: str


class RoutingDecision(BaseModel):
    routing_decision_id: str
    session_id: str
    request_id: str
    policy_version: str
    selected_provider: str
    selected_provider_family: str
    selected_model: str
    selected_mode: str
    ranked_alternatives: list[RankedAlternative]
    decision_rationale: str
    predicted_cost_class: str
    predicted_latency_class: str
    fallback_chain: list[FallbackTarget]
