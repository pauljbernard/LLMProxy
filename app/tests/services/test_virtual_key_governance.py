from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.db.models import VirtualAPIKey
from app.services.virtual_key_governance import reset_due_virtual_key_budgets


class _ScalarResult:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


class _ExecuteResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return _ScalarResult(self._items)


class FakeSession:
    def __init__(self, items):
        self._items = items

    def execute(self, _statement):
        return _ExecuteResult(self._items)


def test_reset_due_virtual_key_budgets_resets_spend_and_advances_recurring_window() -> None:
    now = datetime(2026, 6, 6, 12, 0, tzinfo=timezone.utc)
    record = VirtualAPIKey(
        id="vkey_1",
        key_prefix="sk-test",
        key_hash="hash",
        role="api",
        status="active",
        spend_usd=Decimal("12.5"),
        budget_reset_period="weekly",
        budget_reset_at=now - timedelta(minutes=5),
    )
    session = FakeSession([record])

    reset_count = reset_due_virtual_key_budgets(session, now=now)

    assert reset_count == 1
    assert float(record.spend_usd) == 0.0
    assert record.budget_reset_at == now + timedelta(weeks=1)


def test_reset_due_virtual_key_budgets_clears_one_shot_budget_reset() -> None:
    now = datetime(2026, 6, 6, 12, 0, tzinfo=timezone.utc)
    record = VirtualAPIKey(
        id="vkey_2",
        key_prefix="sk-test",
        key_hash="hash",
        role="api",
        status="active",
        spend_usd=Decimal("3.75"),
        budget_reset_period=None,
        budget_reset_at=now - timedelta(days=1),
    )
    session = FakeSession([record])

    reset_count = reset_due_virtual_key_budgets(session, now=now)

    assert reset_count == 1
    assert float(record.spend_usd) == 0.0
    assert record.budget_reset_at is None
