from types import SimpleNamespace

import pytest

from app.services import provider_readiness
from app.schemas.provider import ProviderCapability


class _FakeProvider:
    provider_family = "openai"
    provider_name = "openai"

    def __init__(self, model_id: str, *, ok: bool = True) -> None:
        self.model_id = model_id
        self._ok = ok

    async def healthcheck(self) -> dict[str, object]:
        return {
            "ok": self._ok,
            "provider": self.provider_name,
            "model": self.model_id,
            "latency_ms": 12,
        }

    async def list_models(self) -> list[dict[str, object]]:
        return []


@pytest.mark.asyncio
async def test_build_provider_readiness_groups_multiple_models_under_one_provider(monkeypatch) -> None:
    settings = SimpleNamespace(
        provider_configuration={"openai": True},
        llmproxy_frontier_default_entries=[
            {"provider_key": "openai", "model_id": "gpt-5.5"},
            {"provider_key": "openai", "model_id": "gpt-4o-mini"},
        ],
    )

    monkeypatch.setattr(
        provider_readiness,
        "get_provider_registry",
        lambda settings, session=None: {"openai": _FakeProvider("gpt-5.5")},
    )
    monkeypatch.setattr(
        provider_readiness,
        "resolve_provider",
        lambda settings, registry, *, provider_key, entry=None: _FakeProvider(
            (entry or {}).get("model_id") or registry[provider_key].model_id
        ),
    )
    monkeypatch.setattr(
        provider_readiness,
        "get_latest_policy",
        lambda session=None: {
            "entries": [
                {"provider_key": "openai", "model_id": "gpt-4o", "domains": ["analysis"]},
            ]
        },
    )

    readiness = await provider_readiness.build_provider_readiness(settings)

    assert len(readiness) == 1
    group = readiness[0]
    assert group["provider_key"] == "openai"
    assert group["model_count"] == 3
    assert group["healthy_model_count"] == 3
    assert {item["model_id"] for item in group["models"]} == {"gpt-5.5", "gpt-4o-mini", "gpt-4o"}


@pytest.mark.asyncio
async def test_build_provider_readiness_uses_provider_model_discovery(monkeypatch) -> None:
    class _DiscoveredProvider(_FakeProvider):
        async def list_models(self) -> list[ProviderCapability]:
            return [
                ProviderCapability(
                    provider_family="OpenAI",
                    provider_name="openai",
                    model_id="gpt-5.5",
                ),
                ProviderCapability(
                    provider_family="OpenAI",
                    provider_name="openai",
                    model_id="gpt-5.5-mini",
                ),
            ]

    settings = SimpleNamespace(
        provider_configuration={"openai": True},
        llmproxy_frontier_default_entries=[],
    )

    monkeypatch.setattr(
        provider_readiness,
        "get_provider_registry",
        lambda settings, session=None: {"openai": _DiscoveredProvider("gpt-5.5")},
    )
    monkeypatch.setattr(
        provider_readiness,
        "resolve_provider",
        lambda settings, registry, *, provider_key, entry=None: _FakeProvider(
            (entry or {}).get("model_id") or registry[provider_key].model_id
        ),
    )
    monkeypatch.setattr(provider_readiness, "get_latest_policy", lambda session=None: {"entries": []})

    readiness = await provider_readiness.build_provider_readiness(settings)

    assert len(readiness) == 1
    group = readiness[0]
    assert group["provider_key"] == "openai"
    assert group["model_count"] == 2
    assert {item["model_id"] for item in group["models"]} == {"gpt-5.5", "gpt-5.5-mini"}
