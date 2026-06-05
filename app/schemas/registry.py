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
    quality: dict[str, object] | None = None
    status: str
    created_at: str | None = None


class ModelRegistrationResponse(BaseModel):
    model_registry_id: str
    model_alias: str
    manifest_path: str
    status: str
    runtime: str


class ModelPackageView(BaseModel):
    model_registry_id: str
    model_alias: str
    base_model: str
    adapter_type: str
    artifact_paths: list[str]
    domains: list[str]
    promotion_status: str
