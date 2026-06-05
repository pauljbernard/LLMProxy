"""Model registry schemas."""

from pydantic import BaseModel


class ModelRegistrationRequest(BaseModel):
    model_registry_id: str
    model_alias: str
    base_model: str
    adapter_type: str
    adapter_path: str
    runtime: str
    endpoint_url: str
    domains: list[str]
    task_types: list[str]
    status: str
