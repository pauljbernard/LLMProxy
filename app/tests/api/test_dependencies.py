from decimal import Decimal

from fastapi.security import HTTPAuthorizationCredentials

from app.api.dependencies import require_api_token, virtual_key_hash
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

    def execute(self, statement):
        return _ExecuteResult(self.record)


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
