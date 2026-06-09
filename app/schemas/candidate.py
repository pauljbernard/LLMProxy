"""Training candidate and export schemas."""

from typing import Literal

from pydantic import BaseModel


class TrainingCandidateView(BaseModel):
    id: str
    request_log_id: str
    routing_decision_id: str
    session_id: str
    domain: str
    task_type: str
    status: str
    quality_score: float | None
    approval_status: str
    export_eligible: bool
    selected_response: str
    metadata: dict[str, object]
    requested_model: str | None = None
    effective_model: str | None = None
    prompt_template_name: str | None = None
    prompt_template_version: int | None = None
    prompt_template_render_hash: str | None = None
    prompt_template_selection_mode: str | None = None
    prompt_template_rollout_percentage: float | None = None
    interaction_protocols: list[str]
    interaction_operations: list[str]
    interaction_outcome: str
    interaction_trace_count: int


class CandidateStatusUpdateResponse(BaseModel):
    candidate_id: str
    status: str
    approval_status: str
    export_eligible: bool


class DatasetExportRequest(BaseModel):
    domain: str
    name: str | None = None
    min_quality_score: float = 0.0
    interaction_protocol: str | None = None
    interaction_operation: str | None = None
    interaction_outcome: Literal["success", "failure", "mixed"] | None = None
    prompt_template_name: str | None = None
    prompt_template_version: int | None = None
    prompt_template_selection_mode: Literal["active", "challenger_canary", "explicit"] | None = None


class DatasetExportResponse(BaseModel):
    dataset_export_id: str
    manifest_path: str
    data_path: str
    record_count: int
