from app.config import Settings
from app.services import provider_health


class FakeRedisClient:
    def __init__(self) -> None:
        self.storage: dict[str, dict[str, str]] = {}

    def ping(self) -> bool:
        return True

    def hgetall(self, key: str) -> dict[str, str]:
        return dict(self.storage.get(key, {}))

    def hset(self, key: str, mapping: dict[str, object]) -> None:
        self.storage[key] = {field: str(value) for field, value in mapping.items()}

    def scan_iter(self, match: str | None = None):
        prefix = (match or "").rstrip("*")
        for key in sorted(self.storage):
            if not prefix or key.startswith(prefix):
                yield key

    def delete(self, *keys: str) -> None:
        for key in keys:
            self.storage.pop(key, None)


def test_provider_health_uses_redis_backing_when_available(monkeypatch) -> None:
    fake_client = FakeRedisClient()

    monkeypatch.setattr(provider_health, "get_settings", lambda: Settings(llmproxy_redis_url="redis://fake"))
    monkeypatch.setattr(provider_health.redis, "from_url", lambda *args, **kwargs: fake_client)

    provider_health.clear_provider_health_state()

    cooled = provider_health.record_provider_failure("openai", allowed_fails=2, cooldown_seconds=30)
    assert cooled is False
    cooled = provider_health.record_provider_failure("openai", allowed_fails=2, cooldown_seconds=30)
    assert cooled is True
    assert provider_health.is_provider_cooled_down("openai") is True

    snapshot = provider_health.provider_health_snapshot()
    assert snapshot["openai"]["consecutive_failures"] == 2
    assert snapshot["openai"]["cooled_down"] is True


def test_provider_health_falls_back_to_memory_when_redis_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(provider_health, "get_settings", lambda: Settings(llmproxy_redis_url="redis://fake"))

    def fail_from_url(*args, **kwargs):
        raise OSError("redis down")

    monkeypatch.setattr(provider_health.redis, "from_url", fail_from_url)

    provider_health.clear_provider_health_state()

    cooled = provider_health.record_provider_failure("openai", allowed_fails=1, cooldown_seconds=30)
    assert cooled is True
    assert provider_health.is_provider_cooled_down("openai") is True

    snapshot = provider_health.provider_health_snapshot()
    assert snapshot["openai"]["consecutive_failures"] == 1
