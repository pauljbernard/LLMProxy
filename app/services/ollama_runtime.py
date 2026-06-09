"""Ollama runtime helpers."""

from __future__ import annotations

from pathlib import Path

import httpx
from sqlalchemy.orm import Session

from app.config import Settings
from app.deployment.manager import list_local_deployment_inventory


def _fetch_installed_ollama_models(base_url: str, *, transport=None) -> list[str]:
    with httpx.Client(base_url=base_url.rstrip("/"), timeout=10.0, transport=transport) as client:
        response = client.get("/api/tags")
        response.raise_for_status()
        payload = response.json()
    return sorted(
        {
            str(item.get("name") or "").strip()
            for item in (payload.get("models") or [])
            if str(item.get("name") or "").strip()
        }
    )


def reconcile_ollama_runtime(
    session: Session,
    *,
    settings: Settings,
    transport=None,
) -> dict[str, object]:
    installed_models = _fetch_installed_ollama_models(settings.llmproxy_ollama_base_url, transport=transport)
    inventory = list_local_deployment_inventory(session, settings=settings)
    ollama_rows = [
        row
        for row in inventory
        if str(row.get("runtime_target") or "") == "ollama" or str(row.get("deployment_runtime") or "") == "ollama"
    ]
    installed_lookup = {item.lower() for item in installed_models}
    package_rows: list[dict[str, object]] = []
    missing_base_model_count = 0
    missing_alias_count = 0
    for row in ollama_rows:
        base_model = str(row.get("base_model") or "")
        model_alias = str(row.get("model_alias") or "")
        base_model_present = base_model.lower() in installed_lookup if base_model else False
        alias_present = model_alias.lower() in installed_lookup if model_alias else False
        if not base_model_present:
            missing_base_model_count += 1
        if not alias_present:
            missing_alias_count += 1
        package_rows.append(
            {
                "model_alias": model_alias,
                "base_model": base_model,
                "lifecycle_stage": str(row.get("lifecycle_stage") or "registered"),
                "deployment_status": str(row.get("deployment_status") or "not_deployed"),
                "routed_live": bool(row.get("routed_live")),
                "base_model_present": base_model_present,
                "alias_present": alias_present,
                "recommended_action": (
                    "pull_base_model"
                    if base_model and not base_model_present
                    else "deploy_package"
                    if str(row.get("deployment_status") or "") != "deployed"
                    else "activate_route"
                    if not bool(row.get("routed_live"))
                    else "ready"
                ),
            }
        )
    return {
        "runtime": "ollama",
        "base_url": settings.llmproxy_ollama_base_url,
        "installed_model_count": len(installed_models),
        "installed_models": installed_models,
        "managed_package_count": len(package_rows),
        "missing_base_model_count": missing_base_model_count,
        "missing_alias_count": missing_alias_count,
        "packages": package_rows,
    }


def pull_ollama_model(
    *,
    settings: Settings,
    model_name: str,
    transport=None,
) -> dict[str, object]:
    with httpx.Client(base_url=settings.llmproxy_ollama_base_url.rstrip("/"), timeout=60.0, transport=transport) as client:
        response = client.post("/api/pull", json={"name": model_name, "stream": False})
        response.raise_for_status()
        payload = response.json() if response.content else {}
    return {
        "runtime": "ollama",
        "model": model_name,
        "status": str(payload.get("status") or "ok"),
        "detail": payload,
    }
