from decimal import Decimal
from datetime import datetime, timezone

from fastapi.security import HTTPAuthorizationCredentials

from app.api.dependencies import (
    enforce_rate_limits,
    record_virtual_key_usage,
    release_rate_limit_token_reservation,
    require_api_token,
    virtual_key_hash,
)
from app.config import Settings
from app.db.models import VirtualAPIKey


class _ExecuteResult:
    def __init__(self, record):
        self._record = record

    def scalar_one_or_none(self):
        return self._record


class FakeSession:
    def __init__(self, record=None) -> None:
        self.record = record
        self.commits = 0

    def execute(self, statement):
        return _ExecuteResult(self.record)

    def get(self, _model, _key):
        return self.record

    def commit(self):
        self.commits += 1


def test_require_api_token_accepts_virtual_api_key() -> None:
    record = VirtualAPIKey(
        id="vkey_123",
        key_prefix="sk-test",
        key_hash=virtual_key_hash("sk-test-secret"),
        display_name="Test Key",
        owner_id="team_123",
        role="api",
        status="active",
        models_allowed_json=["gpt-5.5", "proxy-auto"],
        rpm_limit=30,
        tpm_limit=4000,
        spend_usd=Decimal("1.250000"),
        max_budget_usd=Decimal("10.000000"),
    )

    principal = require_api_token(
        credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials="sk-test-secret"),
        settings=Settings(),
        session=FakeSession(record),
    )

    assert principal.role == "api"
    assert principal.key_id == "vkey_123"
    assert principal.owner_id == "team_123"
    assert principal.models_allowed == ("gpt-5.5", "proxy-auto")
    assert principal.rpm_limit == 30
    assert principal.tpm_limit == 4000
    assert principal.spend_usd == 1.25
    assert principal.max_budget_usd == 10.0


def test_require_api_token_preserves_static_operator_token() -> None:
    principal = require_api_token(
        credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials="change-me"),
        settings=Settings(),
        session=FakeSession(),
    )

    assert principal.role == "operator"
    assert principal.key_id is None


def test_enforce_rate_limits_records_request_and_token_usage() -> None:
    now = datetime.now(timezone.utc)
    record = VirtualAPIKey(
        id="vkey_123",
        key_prefix="sk-test",
        key_hash=virtual_key_hash("sk-test-secret"),
        role="api",
        status="active",
        rpm_limit=5,
        tpm_limit=100,
        spend_usd=Decimal("0"),
        rate_limit_window_started_at=now,
        requests_used_current_window=1,
        tokens_used_current_window=10,
    )
    session = FakeSession(record)
    principal = require_api_token(
        credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials="sk-test-secret"),
        settings=Settings(),
        session=session,
    )

    enforce_rate_limits(session, principal, estimated_tokens=12)

    assert record.requests_used_current_window == 2
    assert record.tokens_used_current_window == 22
    assert session.commits == 1


def test_rate_limit_token_reconciliation_replaces_reserved_tokens_with_actual_usage() -> None:
    now = datetime.now(timezone.utc)
    record = VirtualAPIKey(
        id="vkey_123",
        key_prefix="sk-test",
        key_hash=virtual_key_hash("sk-test-secret"),
        role="api",
        status="active",
        rpm_limit=5,
        tpm_limit=100,
        spend_usd=Decimal("0"),
        rate_limit_window_started_at=now,
        requests_used_current_window=1,
        tokens_used_current_window=50,
    )
    session = FakeSession(record)
    principal = require_api_token(
        credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials="sk-test-secret"),
        settings=Settings(),
        session=session,
    )

    record_virtual_key_usage(session, principal, cost_usd=1.5, reserved_tokens=20, actual_tokens=8)

    assert float(record.spend_usd) == 1.5
    assert record.tokens_used_current_window == 38
    assert record.last_used_at is not None
    assert session.commits == 1


def test_release_rate_limit_token_reservation_does_not_go_negative() -> None:
    record = VirtualAPIKey(
        id="vkey_123",
        key_prefix="sk-test",
        key_hash=virtual_key_hash("sk-test-secret"),
        role="api",
        status="active",
        spend_usd=Decimal("0"),
        tokens_used_current_window=5,
    )
    session = FakeSession(record)
    principal = require_api_token(
        credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials="sk-test-secret"),
        settings=Settings(),
        session=session,
    )

    release_rate_limit_token_reservation(session, principal, reserved_tokens=10)

    assert record.tokens_used_current_window == 0
    assert session.commits == 1
