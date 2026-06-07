"""Virtual-key rate limit and budget reset helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import VirtualAPIKey


def _next_budget_reset_at(current: datetime, period: str | None) -> datetime | None:
    if period == "daily":
        return current + timedelta(days=1)
    if period == "weekly":
        return current + timedelta(weeks=1)
    if period == "monthly":
        return current + timedelta(days=30)
    return None


def reset_due_virtual_key_budgets(session: Session, *, now: datetime | None = None) -> int:
    current_time = now or datetime.now(timezone.utc)
    records = session.execute(
        select(VirtualAPIKey).where(
            VirtualAPIKey.status == "active",
            VirtualAPIKey.budget_reset_at.is_not(None),
            VirtualAPIKey.budget_reset_at <= current_time,
        )
    ).scalars().all()
    reset_count = 0
    for record in records:
        record.spend_usd = 0
        record.budget_reset_at = _next_budget_reset_at(current_time, record.budget_reset_period)
        reset_count += 1
    return reset_count
