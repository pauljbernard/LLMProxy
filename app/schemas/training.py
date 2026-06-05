"""Training schemas."""

from pydantic import BaseModel


class TrainingRunRequest(BaseModel):
    dataset_version_id: str
    base_model: str
    training_mode: str
