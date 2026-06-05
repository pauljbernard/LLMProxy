"""Routing policy persistence helpers."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import RoutingPolicyVersion
from app.proxy.recorder import generate_prefixed_id


EMPTY_POLICY: dict[str, object] = {"entries": []}


def get_latest_policy(session: Session | None) -> dict[str, object]:
    if session is None or not hasattr(session, "execute"):
        return dict(EMPTY_POLICY)
    record = session.execute(
        select(RoutingPolicyVersion).order_by(RoutingPolicyVersion.created_at.desc())
    ).scalars().first()
    if record is None:
        return dict(EMPTY_POLICY)
    return dict(record.policy_json)


def list_policy_versions(session: Session | None) -> list[RoutingPolicyVersion]:
    if session is None or not hasattr(session, "execute"):
        return []
    return list(
        session.execute(
            select(RoutingPolicyVersion).order_by(RoutingPolicyVersion.created_at.desc())
        ).scalars()
    )


def persist_policy_version(
    session: Session,
    *,
    policy_json: dict[str, object],
) -> RoutingPolicyVersion:
    version_id = generate_prefixed_id("rpol")
    record = RoutingPolicyVersion(
        id=version_id,
        policy_version=version_id,
        policy_json=policy_json,
    )
    session.add(record)
    return record
