"""Topology inventory derived from active routing policy and recent traffic."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ModelResponse, RoutingDecisionRecord
from app.integration.routing_policy import get_latest_policy_record
from app.services.provider_health import provider_health_snapshot


def _latency_stats(latencies: list[int]) -> tuple[float | None, int | None]:
    if not latencies:
        return None, None
    ordered = sorted(int(value) for value in latencies)
    average = round(sum(ordered) / len(ordered), 2)
    index = max(0, min(len(ordered) - 1, int(round((len(ordered) - 1) * 0.95))))
    return average, ordered[index]


def _matching_response_latency(
    responses_by_request: dict[str, list[ModelResponse]],
    decision: RoutingDecisionRecord,
) -> int | None:
    rows = responses_by_request.get(decision.request_log_id, [])
    for row in rows:
        if row.provider == decision.selected_provider and row.model == decision.selected_model:
            return int(row.latency_ms or 0)
    if rows:
        return int(rows[0].latency_ms or 0)
    return None


def _base_runtime_metrics() -> dict[str, Any]:
    return {
        "recent_request_count": 0,
        "successful_request_count": 0,
        "failed_request_count": 0,
        "avg_latency_ms": None,
        "p95_latency_ms": None,
        "last_seen_at": None,
        "cooled_down": False,
        "cooled_provider_count": 0,
    }


def build_routing_topology_inventory(session: Session) -> dict[str, Any]:
    policy_record = get_latest_policy_record(session)
    policy_entries = []
    policy_version = None
    if policy_record is not None:
        policy_version = policy_record.policy_version
        policy_entries = list((policy_record.policy_json or {}).get("entries", []))

    recent_decisions = list(
        session.execute(
            select(RoutingDecisionRecord).order_by(RoutingDecisionRecord.created_at.desc()).limit(500)
        ).scalars()
    )
    request_ids = [item.request_log_id for item in recent_decisions if item.request_log_id]
    response_rows = list(
        session.execute(
            select(ModelResponse)
            .where(ModelResponse.request_log_id.in_(request_ids))
            .order_by(ModelResponse.created_at.desc())
        ).scalars()
    ) if request_ids else []
    responses_by_request: dict[str, list[ModelResponse]] = defaultdict(list)
    for row in response_rows:
        responses_by_request[row.request_log_id].append(row)

    provider_health = provider_health_snapshot()

    node_records: dict[str, dict[str, Any]] = {}
    pool_records: dict[str, dict[str, Any]] = {}

    for entry in policy_entries:
        provider_key = str(entry.get("provider_key") or "")
        model_id = str(entry.get("model_alias") or entry.get("model_id") or "")
        if entry.get("node_id"):
            key = str(entry["node_id"])
            record = node_records.setdefault(
                key,
                {
                    "node_id": key,
                    "node_role": entry.get("node_role"),
                    "capacity_class": entry.get("capacity_class"),
                    "node_labels": set(entry.get("node_labels") or []),
                    "providers": set(),
                    "models": set(),
                    "pool_ids": set(),
                    "balancing_strategies": set(),
                    "supports_local_models": False,
                    "supports_training": False,
                    "entry_count": 0,
                    "policy_version": policy_version,
                    "_latencies": [],
                    "_providers_with_health": set(),
                    **_base_runtime_metrics(),
                },
            )
            record["providers"].add(provider_key)
            if model_id:
                record["models"].add(model_id)
            if entry.get("pool_id"):
                record["pool_ids"].add(str(entry["pool_id"]))
            if entry.get("balancing_strategy"):
                record["balancing_strategies"].add(str(entry["balancing_strategy"]))
            record["supports_local_models"] = bool(record["supports_local_models"] or entry.get("supports_local_models"))
            record["supports_training"] = bool(record["supports_training"] or entry.get("supports_training"))
            record["entry_count"] += 1
            if provider_health.get(provider_key, {}).get("cooled_down"):
                record["_providers_with_health"].add(provider_key)

        if entry.get("pool_id"):
            key = str(entry["pool_id"])
            record = pool_records.setdefault(
                key,
                {
                    "pool_id": key,
                    "balancing_strategy": entry.get("balancing_strategy"),
                    "affinity_key": entry.get("affinity_key"),
                    "node_ids": set(),
                    "node_roles": set(),
                    "capacity_classes": set(),
                    "providers": set(),
                    "models": set(),
                    "entry_count": 0,
                    "total_weight": 0.0,
                    "policy_version": policy_version,
                    "_latencies": [],
                    "_providers_with_health": set(),
                    **_base_runtime_metrics(),
                },
            )
            if entry.get("node_id"):
                record["node_ids"].add(str(entry["node_id"]))
            if entry.get("node_role"):
                record["node_roles"].add(str(entry["node_role"]))
            if entry.get("capacity_class"):
                record["capacity_classes"].add(str(entry["capacity_class"]))
            record["providers"].add(provider_key)
            if model_id:
                record["models"].add(model_id)
            record["entry_count"] += 1
            record["total_weight"] += float(entry.get("pool_weight") or 0)
            if provider_health.get(provider_key, {}).get("cooled_down"):
                record["_providers_with_health"].add(provider_key)

    for decision in recent_decisions:
        latency = _matching_response_latency(responses_by_request, decision)
        success = latency is not None
        if decision.selected_node_id and decision.selected_node_id in node_records:
            record = node_records[decision.selected_node_id]
            record["recent_request_count"] += 1
            record["last_seen_at"] = record["last_seen_at"] or decision.created_at
            if success:
                record["successful_request_count"] += 1
                record["_latencies"].append(latency)
            else:
                record["failed_request_count"] += 1
        if decision.selected_pool_id and decision.selected_pool_id in pool_records:
            record = pool_records[decision.selected_pool_id]
            record["recent_request_count"] += 1
            record["last_seen_at"] = record["last_seen_at"] or decision.created_at
            if success:
                record["successful_request_count"] += 1
                record["_latencies"].append(latency)
            else:
                record["failed_request_count"] += 1

    def finalize_node(record: dict[str, Any]) -> dict[str, Any]:
        avg_latency, p95_latency = _latency_stats(record.pop("_latencies"))
        cooled_providers = sorted(record.pop("_providers_with_health"))
        return {
            **record,
            "avg_latency_ms": avg_latency,
            "p95_latency_ms": p95_latency,
            "cooled_down": bool(cooled_providers),
            "cooled_provider_count": len(cooled_providers),
            "cooled_providers": cooled_providers,
            "providers": sorted(record["providers"]),
            "models": sorted(record["models"]),
            "pool_ids": sorted(record["pool_ids"]),
            "balancing_strategies": sorted(record["balancing_strategies"]),
            "node_labels": sorted(record["node_labels"]),
            "pool_count": len(record["pool_ids"]),
            "provider_count": len(record["providers"]),
            "model_count": len(record["models"]),
        }

    def finalize_pool(record: dict[str, Any]) -> dict[str, Any]:
        avg_latency, p95_latency = _latency_stats(record.pop("_latencies"))
        cooled_providers = sorted(record.pop("_providers_with_health"))
        return {
            **record,
            "avg_latency_ms": avg_latency,
            "p95_latency_ms": p95_latency,
            "cooled_down": bool(cooled_providers),
            "cooled_provider_count": len(cooled_providers),
            "cooled_providers": cooled_providers,
            "providers": sorted(record["providers"]),
            "models": sorted(record["models"]),
            "node_ids": sorted(record["node_ids"]),
            "node_roles": sorted(record["node_roles"]),
            "capacity_classes": sorted(record["capacity_classes"]),
            "node_count": len(record["node_ids"]),
            "provider_count": len(record["providers"]),
            "model_count": len(record["models"]),
            "total_weight": round(float(record["total_weight"]), 2),
        }

    nodes = [finalize_node(record) for record in node_records.values()]
    pools = [finalize_pool(record) for record in pool_records.values()]
    nodes.sort(key=lambda row: row["node_id"])
    pools.sort(key=lambda row: row["pool_id"])

    return {
        "policy_version": policy_version,
        "nodes": nodes,
        "pools": pools,
        "summary": {
            "node_count": len(nodes),
            "pool_count": len(pools),
            "active_node_count": sum(1 for row in nodes if row["recent_request_count"]),
            "active_pool_count": sum(1 for row in pools if row["recent_request_count"]),
            "cooled_node_count": sum(1 for row in nodes if row["cooled_down"]),
            "cooled_pool_count": sum(1 for row in pools if row["cooled_down"]),
        },
    }
