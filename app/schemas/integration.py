"""Integration event schemas."""

from app.schemas.routing import FallbackTarget
from pydantic import BaseModel


class IntegrationEvent(BaseModel):
    event_id: str
    event_type: str
    source: str
    payload: dict[str, object]


class DeploymentRequest(BaseModel):
    deployment_mode: str
    domains: list[str] | None = None
    task_types: list[str] | None = None
    canary_percent: float = 0.0


class DeploymentResponse(BaseModel):
    model_alias: str
    deployment_mode: str
    status: str
    policy_version: str
    runtime: str
    endpoint_url: str


class RoutingPolicyVersionView(BaseModel):
    id: str
    policy_version: str
    policy: dict[str, object]


class FrontierPolicyEntryRequest(BaseModel):
    entry_id: str | None = None
    provider_key: str
    model_id: str
    requested_models: list[str] | None = None
    domains: list[str]
    task_types: list[str] | None = None
    tags: list[str] | None = None
    labels: list[str] | None = None
    regions: list[str] | None = None
    listener_ids: list[str] | None = None
    deployment_mode: str = "production"
    canary_percent: float = 0.0
    endpoint_url: str | None = None
    node_id: str | None = None
    node_role: str | None = None
    node_labels: list[str] | None = None
    capacity_class: str | None = None
    supports_local_models: bool | None = None
    supports_training: bool | None = None
    pool_id: str | None = None
    pool_weight: float = 1.0
    balancing_strategy: str | None = None
    affinity_key: str | None = None
    forward_request_metadata: bool = False
    fallback_chain: list[FallbackTarget] | None = None
    decision_rationale: str | None = None


class RoutingPolicyEntryMutationResponse(BaseModel):
    entry_id: str
    policy_version: str
    action: str


class OutboxProcessResponse(BaseModel):
    processed_count: int
    imported_count: int


class KpiMetricView(BaseModel):
    time_window: str
    metric_name: str
    metric_value: float
    formula_version: str
    policy_version: str
    sample_size: int
    currency: str | None = None
    estimation_flag: bool | None = None


class KpiTopologyCostRollupView(BaseModel):
    topology_type: str
    topology_id: str
    node_role: str | None = None
    capacity_class: str | None = None
    request_count: int
    production_request_count: int
    learning_request_count: int
    spend_total: float
    production_spend_total: float
    learning_spend_total: float
    share_of_tco: float


class KpiReportResponse(BaseModel):
    report_path: str
    metrics: list[KpiMetricView]
    node_rollups: list[KpiTopologyCostRollupView] = []
    pool_rollups: list[KpiTopologyCostRollupView] = []
    listener_rollups: list[KpiTopologyCostRollupView] = []
