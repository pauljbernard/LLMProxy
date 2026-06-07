"""Deployment manager."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.config import Settings
from app.deployment.llama_cpp import deploy_to_llama_cpp
from app.deployment.mlx import deploy_to_mlx
from app.deployment.ollama import deploy_to_ollama
from app.deployment.vllm import deploy_to_vllm
from app.integration.events import emit_event
from app.integration.routing_policy import get_latest_policy, list_policy_versions, persist_policy_version
from app.proxy.recorder import generate_prefixed_id
from app.registry.artifact_store import get_model_package_by_alias
from app.schemas.integration import DeploymentRequest, DeploymentResponse, FrontierPolicyEntryRequest


def list_routing_policies(session: Session) -> list[object]:
    return list_policy_versions(session)


def _provider_family_for_frontier(provider_key: str) -> str:
    return {
        "openai": "OpenAI",
        "anthropic": "Anthropic",
        "google": "Google Gemini",
        "xai": "xAI",
        "azure_openai": "Azure OpenAI",
        "bedrock": "AWS Bedrock",
    }.get(provider_key, provider_key)


def _normalized_policy_entries(existing_policy: dict[str, object]) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for entry in existing_policy.get("entries", []):
        normalized = dict(entry)
        normalized.setdefault("entry_id", generate_prefixed_id("rpentry"))
        normalized.setdefault(
            "entry_type",
            "local"
            if str(normalized.get("provider_key", "")).startswith("local:")
            or str(normalized.get("provider_family", "")).lower() == "local runtime"
            else "frontier",
        )
        entries.append(normalized)
    return entries


def _runtime_for_package(model_package: dict[str, object]) -> str:
    runtime_targets = model_package.get("compatibility", {}).get("runtime_targets", ["ollama"])
    return str(runtime_targets[0])


def _healthcheck_runtime(runtime: str, deployment_result: dict[str, object]) -> None:
    if deployment_result.get("status") != "deployed":
        raise ValueError(f"Deployment to runtime '{runtime}' did not complete successfully.")


def _deploy_to_runtime(
    *,
    runtime: str,
    model_alias: str,
    model_package: dict[str, object],
    models_root: Path,
) -> dict[str, object]:
    if runtime == "ollama":
        return deploy_to_ollama(model_alias=model_alias, model_package=model_package, models_root=models_root)
    if runtime == "vllm":
        return deploy_to_vllm(model_alias=model_alias, model_package=model_package, models_root=models_root)
    if runtime == "llama_cpp":
        return deploy_to_llama_cpp(model_alias=model_alias, model_package=model_package, models_root=models_root)
    if runtime == "mlx":
        return deploy_to_mlx(model_alias=model_alias, model_package=model_package, models_root=models_root)
    raise ValueError(f"Runtime '{runtime}' is not supported.")


def deploy_model(
    session: Session,
    *,
    model_alias: str,
    request: DeploymentRequest,
    settings: Settings,
) -> DeploymentResponse:
    package = get_model_package_by_alias(Path(settings.llmproxy_models_path), model_alias)
    if package is None:
        raise ValueError(f"Model package '{model_alias}' was not found.")
    if str(package.get("quality_summary", {}).get("promotion_status")) != "approved":
        raise ValueError(f"Model package '{model_alias}' is not approved for deployment.")

    runtime = _runtime_for_package(package)
    deployment_result = _deploy_to_runtime(
        runtime=runtime,
        model_alias=model_alias,
        model_package=package,
        models_root=Path(settings.llmproxy_models_path),
    )
    _healthcheck_runtime(runtime, deployment_result)

    existing_policy = get_latest_policy(session)
    existing_entries = _normalized_policy_entries(existing_policy)
    domains = request.domains or [str(domain) for domain in package.get("domains", [])]
    task_types = request.task_types or [str(task_type) for task_type in package.get("task_types", [])]
    if request.deployment_mode == "production":
        rewritten_entries: list[dict[str, object]] = []
        for entry in existing_entries:
            if (
                entry.get("deployment_mode") == "production"
                and entry.get("provider_family") == "local runtime"
                and set(entry.get("domains", [])) & set(domains)
            ):
                prior_entry = dict(entry)
                prior_entry["deployment_mode"] = "previous"
                rewritten_entries.append(prior_entry)
                continue
            rewritten_entries.append(entry)
        existing_entries = rewritten_entries

    existing_entries = [entry for entry in existing_entries if str(entry.get("model_alias")) != model_alias]
    policy_entry = {
        "entry_type": "local",
        "entry_id": generate_prefixed_id("rpentry"),
        "model_alias": model_alias,
        "model_registry_id": package["model_registry_id"],
        "deployment_mode": request.deployment_mode,
        "runtime": runtime,
        "provider_key": f"local:{model_alias}",
        "provider_name": runtime,
        "provider_family": "local runtime",
        "endpoint_url": deployment_result["endpoint_url"],
        "artifact_path": package["artifact_paths"][0],
        "domains": domains,
        "task_types": task_types,
        "canary_percent": request.canary_percent,
        "quality_summary": package.get("quality_summary", {}),
    }
    existing_entries.append(policy_entry)
    new_policy = {"entries": existing_entries}
    policy_record = persist_policy_version(session, policy_json=new_policy)
    emit_event(
        session,
        event_type="model.deployed",
        source="llmproxy",
        payload={
            "model_alias": model_alias,
            "deployment_mode": request.deployment_mode,
            "policy_version": policy_record.policy_version,
        },
    )
    emit_event(
        session,
        event_type="routing.updated",
        source="llmproxy",
        payload={
            "policy_version": policy_record.policy_version,
            "deployment_mode": request.deployment_mode,
        },
    )
    return DeploymentResponse(
        model_alias=model_alias,
        deployment_mode=request.deployment_mode,
        status="deployed",
        policy_version=policy_record.policy_version,
        runtime=runtime,
        endpoint_url=str(deployment_result["endpoint_url"]),
    )


def rollback_model(
    session: Session,
    *,
    model_alias: str,
    settings: Settings,
) -> DeploymentResponse:
    existing_policy = get_latest_policy(session)
    existing_entries = _normalized_policy_entries(existing_policy)
    target_entry = next((entry for entry in existing_entries if str(entry.get("model_alias")) == model_alias), None)
    if target_entry is None:
        raise ValueError(f"Deployed model '{model_alias}' was not found in the active routing policy.")

    domains = set(target_entry.get("domains", []))
    remaining_entries = [entry for entry in existing_entries if str(entry.get("model_alias")) != model_alias]
    if target_entry.get("deployment_mode") == "production":
        fallback_entry = next(
            (
                entry
                for entry in reversed(existing_entries)
                if str(entry.get("model_alias")) != model_alias
                and entry.get("provider_family") == "local runtime"
                and set(entry.get("domains", [])) & domains
                and entry.get("deployment_mode") in {"previous", "production"}
            ),
            None,
        )
        if fallback_entry is not None:
            fallback_entry = dict(fallback_entry)
            fallback_entry["deployment_mode"] = "production"
            remaining_entries = [
                entry
                for entry in remaining_entries
                if str(entry.get("model_alias")) != str(fallback_entry.get("model_alias"))
            ]
            remaining_entries.append(fallback_entry)

    new_policy = {"entries": remaining_entries}
    policy_record = persist_policy_version(session, policy_json=new_policy)
    emit_event(
        session,
        event_type="model.rolled_back",
        source="llmproxy",
        payload={
            "model_alias": model_alias,
            "policy_version": policy_record.policy_version,
        },
    )
    emit_event(
        session,
        event_type="routing.updated",
        source="llmproxy",
        payload={
            "policy_version": policy_record.policy_version,
            "deployment_mode": "rollback",
        },
    )
    return DeploymentResponse(
        model_alias=model_alias,
        deployment_mode="rollback",
        status="rolled_back",
        policy_version=policy_record.policy_version,
        runtime=str(target_entry.get("runtime", "ollama")),
        endpoint_url=str(target_entry.get("endpoint_url", "http://localhost:11434")),
    )


def upsert_frontier_policy_entry(
    session: Session,
    *,
    request: FrontierPolicyEntryRequest,
) -> tuple[str, str]:
    existing_policy = get_latest_policy(session)
    existing_entries = _normalized_policy_entries(existing_policy)
    entry_id = request.entry_id or generate_prefixed_id("rpentry")
    entry = {
        "entry_id": entry_id,
        "entry_type": "frontier",
        "provider_key": request.provider_key,
        "provider_name": request.provider_key,
        "provider_family": _provider_family_for_frontier(request.provider_key),
        "model_id": request.model_id,
        "domains": request.domains,
        "task_types": request.task_types or [],
        "tags": request.tags or [],
        "labels": request.labels or request.tags or [],
        "regions": request.regions or [],
        "deployment_mode": request.deployment_mode,
        "canary_percent": request.canary_percent,
        "endpoint_url": request.endpoint_url,
        "fallback_chain": [item.model_dump(mode="json") for item in (request.fallback_chain or [])],
        "decision_rationale": request.decision_rationale,
    }
    replaced = False
    rewritten_entries: list[dict[str, object]] = []
    for candidate in existing_entries:
        if str(candidate.get("entry_id")) == entry_id:
            rewritten_entries.append(entry)
            replaced = True
        else:
            rewritten_entries.append(candidate)
    if not replaced:
        rewritten_entries.append(entry)
    policy_record = persist_policy_version(session, policy_json={"entries": rewritten_entries})
    emit_event(
        session,
        event_type="routing.updated",
        source="llmproxy",
        payload={
            "policy_version": policy_record.policy_version,
            "entry_id": entry_id,
            "entry_type": "frontier",
            "action": "updated" if replaced else "created",
        },
    )
    return entry_id, policy_record.policy_version


def delete_policy_entry(
    session: Session,
    *,
    entry_id: str,
) -> str:
    existing_policy = get_latest_policy(session)
    existing_entries = _normalized_policy_entries(existing_policy)
    remaining_entries = [entry for entry in existing_entries if str(entry.get("entry_id")) != entry_id]
    if len(remaining_entries) == len(existing_entries):
        raise ValueError(f"Routing policy entry '{entry_id}' was not found.")
    policy_record = persist_policy_version(session, policy_json={"entries": remaining_entries})
    emit_event(
        session,
        event_type="routing.updated",
        source="llmproxy",
        payload={
            "policy_version": policy_record.policy_version,
            "entry_id": entry_id,
            "action": "deleted",
        },
    )
    return policy_record.policy_version
