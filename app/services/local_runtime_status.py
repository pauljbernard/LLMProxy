"""Local runtime status helpers."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from app.config import Settings
from app.integration.routing_policy import get_latest_policy
from app.registry.artifact_store import list_model_packages


def _normalize_openai_base_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.path in {"", "/"}:
        return base_url.rstrip("/") + "/v1"
    return base_url.rstrip("/")


def _runtime_health_url(runtime: str, base_url: str) -> tuple[str, str]:
    if runtime == "ollama":
        return base_url.rstrip("/"), "/api/tags"
    return _normalize_openai_base_url(base_url), "/models"


def _runtime_rows(settings: Settings) -> list[dict[str, object]]:
    return [
        {
            "runtime": "ollama",
            "provider_family": "local runtime",
            "base_url": settings.llmproxy_ollama_base_url,
            "configured": bool(settings.llmproxy_ollama_base_url),
            "supports_hosting": True,
            "notes": "Native Ollama runtime integration for colocated or network-hosted serving.",
        },
        {
            "runtime": "vllm",
            "provider_family": "local runtime",
            "base_url": settings.llmproxy_vllm_base_url,
            "configured": bool(settings.llmproxy_vllm_base_url),
            "supports_hosting": True,
            "notes": "OpenAI-compatible runtime integration for GPU-hosted serving.",
        },
        {
            "runtime": "llama_cpp",
            "provider_family": "local runtime",
            "base_url": settings.llmproxy_llama_cpp_base_url,
            "configured": bool(settings.llmproxy_llama_cpp_base_url),
            "supports_hosting": True,
            "notes": "OpenAI-compatible llama.cpp runtime endpoint.",
        },
        {
            "runtime": "mlx",
            "provider_family": "local runtime",
            "base_url": settings.llmproxy_mlx_base_url,
            "configured": bool(settings.llmproxy_mlx_base_url),
            "supports_hosting": True,
            "notes": "OpenAI-compatible MLX runtime endpoint.",
        },
    ]


def build_local_runtime_status(session: Session, settings: Settings) -> list[dict[str, object]]:
    policy = get_latest_policy(session)
    active_entries = list(policy.get("entries", []))
    packages = list_model_packages(Path(settings.llmproxy_models_path))

    package_aliases_by_runtime: dict[str, list[str]] = {}
    deployed_aliases_by_runtime: dict[str, list[str]] = {}
    for manifest in packages:
        runtime_targets = manifest.get("compatibility", {}).get("runtime_targets") or [manifest.get("runtime") or "ollama"]
        runtime = str(runtime_targets[0] or "ollama")
        model_alias = str(manifest.get("model_alias", ""))
        if model_alias:
            package_aliases_by_runtime.setdefault(runtime, []).append(model_alias)
            package_dir = Path(settings.llmproxy_models_path) / model_alias
            deployment_manifests = sorted(package_dir.glob("deployment*.json"))
            if deployment_manifests:
                try:
                    deployment_payload = deployment_manifests[-1].read_text(encoding="utf-8")
                    deployment_status = str(json.loads(deployment_payload).get("status") or "")
                except Exception:
                    deployment_status = ""
                if deployment_status == "deployed":
                    deployed_aliases_by_runtime.setdefault(runtime, []).append(model_alias)

    route_aliases_by_runtime: dict[str, list[str]] = {}
    for entry in active_entries:
        if str(entry.get("entry_type", "")) != "local":
            continue
        runtime = str(entry.get("runtime") or "ollama")
        route_aliases_by_runtime.setdefault(runtime, []).append(str(entry.get("model_alias") or entry.get("model_id") or ""))

    rows: list[dict[str, object]] = []
    for row in _runtime_rows(settings):
        runtime = str(row["runtime"])
        package_aliases = sorted({alias for alias in package_aliases_by_runtime.get(runtime, []) if alias})
        deployed_aliases = sorted({alias for alias in deployed_aliases_by_runtime.get(runtime, []) if alias})
        route_aliases = sorted({alias for alias in route_aliases_by_runtime.get(runtime, []) if alias})
        base_url = str(row["base_url"])
        health_base_url, health_path = _runtime_health_url(runtime, base_url)
        reachable = False
        status_code = None
        detail = "Runtime endpoint not checked yet."
        models_visible = None
        if row["configured"]:
            try:
                with httpx.Client(base_url=health_base_url, timeout=3.0) as client:
                    response = client.get(health_path)
                status_code = response.status_code
                reachable = response.status_code < 500
                payload = response.json() if response.content else {}
                if runtime == "ollama":
                    models_visible = len(payload.get("models") or [])
                else:
                    models_visible = len(payload.get("data") or [])
                detail = "Runtime responded." if reachable else f"Runtime returned status {response.status_code}."
            except Exception as exc:
                detail = str(exc)
        rows.append(
            {
                **row,
                "reachable": reachable,
                "status_code": status_code,
                "detail": detail,
                "models_visible": models_visible,
                "package_alias_count": len(package_aliases),
                "package_aliases": package_aliases,
                "deployed_alias_count": len(deployed_aliases),
                "deployed_aliases": deployed_aliases,
                "active_route_count": len(route_aliases),
                "active_route_aliases": route_aliases,
            }
        )
    return rows
