"""Training schemas."""

from pydantic import BaseModel


class TrainingRunRequest(BaseModel):
    dataset_version_id: str
    base_model: str
    training_mode: str
    epochs: int = 3
    learning_rate: float = 0.0002
    adapter_name: str | None = None


class TrainingRunResponse(BaseModel):
    training_run_id: str
    dataset_version_id: str
    training_mode: str
    status: str
    artifact_path: str
    metrics: dict[str, object]


class TrainingRunView(BaseModel):
    id: str
    dataset_version_id: str
    base_model: str
    training_mode: str
    status: str
    artifact_path: str
    metrics: dict[str, object]
