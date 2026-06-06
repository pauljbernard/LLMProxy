"""Model registry endpoints."""

from pathlib import Path

from fastapi import APIRouter, Depends

from app.api.dependencies import get_runtime_settings, require_api_token
from app.config import Settings
from app.registry.artifact_store import list_model_packages
from app.registry.model_registry import list_provider_capabilities
from app.schemas.provider import ProviderCapability
from app.schemas.registry import ModelPackageView

router = APIRouter(prefix="/models", tags=["models"])


@router.get("", response_model=list[ProviderCapability], dependencies=[Depends(require_api_token)])
def list_registered_models(
    settings: Settings = Depends(get_runtime_settings),
) -> list[ProviderCapability]:
    return list_provider_capabilities(settings)


@router.get("/local", response_model=list[ModelPackageView], dependencies=[Depends(require_api_token)])
def list_local_model_packages(
    settings: Settings = Depends(get_runtime_settings),
) -> list[ModelPackageView]:
    manifests = list_model_packages(Path(settings.llmproxy_models_path))
    return [
        ModelPackageView(
            model_registry_id=str(manifest["model_registry_id"]),
            model_alias=str(manifest["model_alias"]),
            base_model=str(manifest["base_model"]),
            adapter_type=str(manifest["adapter_type"]),
            artifact_paths=[str(path) for path in manifest["artifact_paths"]],
            domains=[str(domain) for domain in manifest["domains"]],
            promotion_status=str(manifest["quality_summary"]["promotion_status"]),
        )
        for manifest in manifests
    ]
