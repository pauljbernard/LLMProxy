"""Training candidate and export schemas."""

from pydantic import BaseModel


class TrainingCandidateView(BaseModel):
    id: str
    request_log_id: str
    routing_decision_id: str
    session_id: str
    domain: str
    task_type: str
    status: str
    quality_score: float
    approval_status: str
    export_eligible: bool
    selected_response: str
    metadata: dict[str, object]


class CandidateStatusUpdateResponse(BaseModel):
    candidate_id: str
    status: str
    approval_status: str
    export_eligible: bool


class DatasetExportRequest(BaseModel):
    domain: str
    name: str | None = None
    min_quality_score: float = 0.0


class DatasetExportResponse(BaseModel):
    dataset_export_id: str
    manifest_path: str
    data_path: str
    record_count: int
