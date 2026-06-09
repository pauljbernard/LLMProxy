"""Routing schemas."""

from pydantic import BaseModel
from pydantic import Field


class RankedAlternative(BaseModel):
    rank: int
    provider: str
    model: str
    score: float


class FallbackTarget(BaseModel):
    order: int
    provider: str
    model: str
    entry_id: str | None = None
    pool_id: str | None = None
    node_id: str | None = None
    node_role: str | None = None
    node_labels: list[str] = Field(default_factory=list)
    capacity_class: str | None = None
    provider_family: str | None = None
    balancing_strategy: str | None = None
    affinity_key: str | None = None


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
    selected_entry_id: str | None = None
    selected_pool_id: str | None = None
    selected_node_id: str | None = None
    selected_node_role: str | None = None
    selected_node_labels: list[str] = Field(default_factory=list)
    selected_capacity_class: str | None = None
    selected_balancing_strategy: str | None = None
    selected_affinity_key: str | None = None
