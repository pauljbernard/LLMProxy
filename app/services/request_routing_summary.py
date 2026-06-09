"""Helpers for attaching latest routing summaries to request payloads."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import RoutingDecisionRecord


def latest_routing_decisions_by_request(
    session: Session,
    request_ids: list[str],
) -> dict[str, RoutingDecisionRecord]:
    ids = [item for item in request_ids if item]
    if not ids:
        return {}
    rows = list(
        session.execute(
            select(RoutingDecisionRecord)
            .where(RoutingDecisionRecord.request_log_id.in_(ids))
            .order_by(RoutingDecisionRecord.created_at.desc())
        ).scalars()
    )
    latest: dict[str, RoutingDecisionRecord] = {}
    for row in rows:
        if row.request_log_id and row.request_log_id not in latest:
            latest[row.request_log_id] = row
    return latest


def enrich_request_summary_with_routing(
    payload: dict[str, Any],
    latest_routing_decision: RoutingDecisionRecord | None = None,
) -> dict[str, Any]:
    if latest_routing_decision is None:
        return {
            **payload,
            "selected_provider": None,
            "selected_model": None,
            "selected_mode": None,
            "selected_pool_id": None,
            "selected_node_id": None,
            "selected_node_role": None,
            "selected_balancing_strategy": None,
            "selected_affinity_key": None,
        }
    return {
        **payload,
        "selected_provider": latest_routing_decision.selected_provider,
        "selected_model": latest_routing_decision.selected_model,
        "selected_mode": latest_routing_decision.selected_mode,
        "selected_pool_id": latest_routing_decision.selected_pool_id,
        "selected_node_id": latest_routing_decision.selected_node_id,
        "selected_node_role": latest_routing_decision.selected_node_role,
        "selected_balancing_strategy": latest_routing_decision.selected_balancing_strategy,
        "selected_affinity_key": latest_routing_decision.selected_affinity_key,
    }
