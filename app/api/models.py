"""Model registry endpoints."""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import AuthPrincipal, get_runtime_settings, require_api_token, require_platform_listener
from app.config import Settings
from app.registry.artifact_store import list_model_packages
from app.registry.model_registry import list_provider_capabilities_async
from app.schemas.provider import ProviderCapability
from app.schemas.registry import ModelPackageView

router = APIRouter(prefix="/models", tags=["models"], dependencies=[Depends(require_platform_listener)])


@router.get("", response_model=list[ProviderCapability])
async def list_registered_models(
    settings: Settings = Depends(get_runtime_settings),
    principal: AuthPrincipal = Depends(require_api_token),
) -> list[ProviderCapability]:
    allowed_models = set(principal.models_allowed) if principal.models_allowed else None
    return await list_provider_capabilities_async(settings, allowed_models=allowed_models)


@router.get("/local")
def list_local_model_packages(
    paginated: bool = False,
    limit: int = Query(default=20, le=200),
    offset: int = Query(default=0, ge=0),
    settings: Settings = Depends(get_runtime_settings),
    principal: AuthPrincipal = Depends(require_api_token),
) -> list[ModelPackageView] | dict[str, Any]:
    manifests = list_model_packages(Path(settings.llmproxy_models_path))
    allowed_models = set(principal.models_allowed) if principal.models_allowed else None
    payload = [
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
        if allowed_models is None or str(manifest["model_alias"]) in allowed_models
    ]
    if not paginated:
        return payload
    items = payload[offset:offset + limit]
    return {
        "items": [item.model_dump(mode="json") for item in items],
        "total": len(payload),
        "limit": limit,
        "offset": offset,
    }
