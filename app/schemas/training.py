"""Training schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class TrainingRunRequest(BaseModel):
    dataset_version_id: str
    base_model: str
    training_mode: str
    trainer_backend: str = "custom"
    epochs: int = 3
    learning_rate: float = 0.0002
    adapter_name: str | None = None


class TrainingRunResponse(BaseModel):
    training_run_id: str
    dataset_version_id: str
    training_mode: str
    trainer_backend: str
    status: str
    artifact_path: str
    metrics: dict[str, object]


class TrainingRunView(BaseModel):
    id: str
    dataset_version_id: str
    base_model: str
    training_mode: str
    trainer_backend: str
    status: str
    artifact_path: str
    metrics: dict[str, object]


class TrainingPreflightCheck(BaseModel):
    name: str
    status: str
    detail: str


class TrainingRuntimeDependencyStatus(BaseModel):
    name: str
    available: bool
    detail: str


class TrainingWorkerRuntimeStatus(BaseModel):
    reported_at: datetime | None = None
    role: str = "training-worker"
    ready: bool = False
    backend_import_ready: bool = False
    unsloth_command_configured: bool = False
    unsloth_command: str | None = None
    internal_api_base_url: str | None = None
    cuda_available: bool | None = None
    device_count: int | None = None
    torch_version: str | None = None
    unsloth_version: str | None = None
    dependencies: list[TrainingRuntimeDependencyStatus] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class TrainingStudioStatus(BaseModel):
    enabled: bool = False
    configured: bool = False
    external_url: str | None = None
    internal_url: str | None = None
    password_configured: bool = False
    reachable: bool = False
    status_code: int | None = None
    detail: str | None = None
    notes: list[str] = Field(default_factory=list)


class TrainingPreflightResponse(BaseModel):
    dataset_version_id: str
    base_model: str
    training_mode: str
    trainer_backend: str
    ready: bool
    record_counts: dict[str, int]
    checks: list[TrainingPreflightCheck]
    errors: list[str]
    warnings: list[str]
    worker_runtime_status: TrainingWorkerRuntimeStatus | None = None
