"""Provider readiness aggregation for the System workbench."""

from __future__ import annotations

import asyncio
from collections import OrderedDict

from app.config import Settings
from app.integration.routing_policy import get_latest_policy
from app.registry.model_registry import get_provider_registry, resolve_provider


async def _provider_discovery_entries(provider_key: str, provider: object) -> list[tuple[str, dict[str, object] | None]]:
    try:
        capabilities = await provider.list_models()
    except Exception:
        return [(provider_key, None)]
    if not capabilities:
        return [(provider_key, None)]
    entries: list[tuple[str, dict[str, object] | None]] = []
    for capability in capabilities:
        entries.append(
            (
                provider_key,
                {
                    "provider_key": provider_key,
                    "provider_family": getattr(capability, "provider_family", getattr(provider, "provider_family", provider_key)),
                    "model_id": getattr(capability, "model_id", getattr(provider, "model_id", provider_key)),
                },
            )
        )
    return entries


def _provider_group_key(provider: object, provider_key: str) -> str:
    provider_family = str(getattr(provider, "provider_family", "") or "").lower()
    provider_name = str(getattr(provider, "provider_name", "") or provider_key).lower()
    if provider_family == "local runtime":
        return f"local:{provider_name}"
    return provider_key


def _provider_group_label(provider: object, provider_key: str) -> str:
    provider_family = str(getattr(provider, "provider_family", "") or "").lower()
    provider_name = str(getattr(provider, "provider_name", "") or provider_key)
    if provider_family == "local runtime":
        return provider_name
    return provider_key


def _model_target_key(provider_key: str, entry: dict[str, object] | None, provider: object) -> tuple[str, str, str, str]:
    base_url = str(getattr(provider, "base_url", "") or getattr(provider, "endpoint", "") or "")
    runtime_name = str(entry.get("runtime", "") if entry else "")
    model_id = str(
        (entry or {}).get("model_alias")
        or (entry or {}).get("model_id")
        or getattr(provider, "model_id", provider_key)
    )
    return (provider_key, runtime_name, base_url, model_id)


def _model_source(entry: dict[str, object] | None) -> str:
    if entry is None:
        return "configured default"
    if entry.get("model_alias"):
        return "routing policy"
    if entry.get("domains") or entry.get("task_types") or entry.get("route_tags") or entry.get("regions"):
        return "routing policy"
    return "frontier default"


def _status_for_model(model: dict[str, object]) -> str:
    if not model.get("configured", True):
        return "missing_config"
    if model.get("ok") is True:
        return "healthy"
    return "unavailable"


def _status_for_group(configured: bool, models: list[dict[str, object]]) -> str:
    if not configured:
        return "missing_config"
    if not models:
        return "unavailable"
    healthy_count = sum(1 for model in models if model.get("ok") is True)
    if healthy_count == len(models):
        return "healthy"
    if healthy_count:
        return "partial"
    return "unavailable"


def _status_note(status: str, configured: bool, models: list[dict[str, object]]) -> str:
    if not configured:
        return "Missing configuration for this provider."
    if not models:
        return "No routed models registered for readiness checks."
    healthy_count = sum(1 for model in models if model.get("ok") is True)
    if status == "healthy":
        return f"All {healthy_count} model targets responded."
    if status == "partial":
        return f"{healthy_count}/{len(models)} model targets responded."
    first_error = next((str(model.get("error") or model.get("detail") or "").strip() for model in models if model.get("ok") is not True), "")
    return first_error or "No model targets responded."


async def build_provider_readiness(settings: Settings, session=None) -> list[dict[str, object]]:
    provider_registry = get_provider_registry(settings, session=session)
    configured_families = dict(settings.provider_configuration)
    policy = get_latest_policy(session)

    candidate_entries: list[tuple[str, dict[str, object] | None]] = []
    discovered_provider_entries = await asyncio.gather(
        *(_provider_discovery_entries(provider_key, provider) for provider_key, provider in provider_registry.items()),
        return_exceptions=True,
    )
    for provider_key, discovered in zip(provider_registry.keys(), discovered_provider_entries, strict=False):
        if isinstance(discovered, Exception):
            candidate_entries.append((provider_key, None))
            continue
        candidate_entries.extend(discovered)
    for entry in settings.llmproxy_frontier_default_entries:
        provider_key = str(entry.get("provider_key", "")).strip()
        if provider_key:
            candidate_entries.append((provider_key, dict(entry)))
    for entry in policy.get("entries", []):
        provider_key = str(entry.get("provider_key", "")).strip()
        if provider_key:
            candidate_entries.append((provider_key, dict(entry)))

    targets: list[tuple[str, object, dict[str, object] | None, str, bool]] = []
    seen_target_keys: set[tuple[str, str, str, str]] = set()
    for provider_key, entry in candidate_entries:
        try:
            provider = resolve_provider(
                settings,
                provider_registry,
                provider_key=provider_key,
                entry=entry,
            )
        except Exception:
            provider = provider_registry.get(provider_key)
        if provider is None:
            continue
        target_key = _model_target_key(provider_key, entry, provider)
        if target_key in seen_target_keys:
            continue
        seen_target_keys.add(target_key)
        logical_group_key = _provider_group_key(provider, provider_key)
        configured = configured_families.get(provider_key)
        if configured is None and logical_group_key.startswith("local:"):
            configured = True
        targets.append((provider_key, provider, entry, logical_group_key, bool(configured)))

    ping_results = await asyncio.gather(
        *(provider.healthcheck() for _, provider, _, _, _ in targets),
        return_exceptions=True,
    )

    groups: OrderedDict[str, dict[str, object]] = OrderedDict()
    for (provider_key, provider, entry, logical_group_key, configured), result in zip(targets, ping_results, strict=False):
        if isinstance(result, Exception):
            health = {"ok": False, "error": str(result), "model": getattr(provider, "model_id", provider_key)}
        else:
            health = dict(result)
        group = groups.setdefault(
            logical_group_key,
            {
                "provider_key": logical_group_key,
                "provider_name": _provider_group_label(provider, provider_key),
                "provider_family": getattr(provider, "provider_family", provider_key),
                "configured": configured,
                "models": [],
            },
        )
        group["configured"] = bool(group["configured"]) or configured
        model_row = {
            "provider_key": provider_key,
            "model_id": str(health.get("model") or getattr(provider, "model_id", provider_key)),
            "source": _model_source(entry),
            "ok": health.get("ok"),
            "status_code": health.get("status_code"),
            "latency_ms": health.get("latency_ms"),
            "error": health.get("error") or "",
            "detail": health.get("detail") or "",
            "configured": configured,
        }
        model_row["status"] = _status_for_model(model_row)
        group["models"].append(model_row)

    readiness: list[dict[str, object]] = []
    for group in groups.values():
        models = sorted(group["models"], key=lambda item: (item["status"] != "healthy", item["model_id"]))
        configured = bool(group["configured"])
        status = _status_for_group(configured, models)
        readiness.append(
            {
                "provider_key": group["provider_key"],
                "provider_name": group["provider_name"],
                "provider_family": group["provider_family"],
                "configured": configured,
                "status": status,
                "healthy_model_count": sum(1 for item in models if item.get("ok") is True),
                "model_count": len(models),
                "note": _status_note(status, configured, models),
                "models": models,
            }
        )

    readiness.sort(key=lambda item: (not item["configured"], item["provider_name"]))
    return readiness
