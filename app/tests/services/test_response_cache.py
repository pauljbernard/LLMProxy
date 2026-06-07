from app.config import Settings
from app.services import response_cache


class FakeRedisClient:
    def __init__(self) -> None:
        self.storage: dict[str, str] = {}

    def ping(self) -> bool:
        return True

    def get(self, key: str) -> str | None:
        return self.storage.get(key)

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.storage[key] = value

    def scan_iter(self, match: str | None = None):
        prefix = (match or "").rstrip("*")
        for key in sorted(self.storage):
            if not prefix or key.startswith(prefix):
                yield key

    def delete(self, *keys: str) -> None:
        for key in keys:
            self.storage.pop(key, None)


def test_response_cache_uses_redis_when_available(monkeypatch) -> None:
    fake_client = FakeRedisClient()
    monkeypatch.setattr(response_cache, "get_settings", lambda: Settings(llmproxy_redis_url="redis://fake"))
    monkeypatch.setattr(response_cache.redis, "from_url", lambda *args, **kwargs: fake_client)
    response_cache.clear_response_cache()

    response_cache.put_cached_response("abc", {"content": "shared"}, ttl_seconds=60)
    payload = response_cache.get_cached_response("abc")

    assert payload == {"content": "shared"}


def test_response_cache_falls_back_to_memory_when_redis_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(response_cache, "get_settings", lambda: Settings(llmproxy_redis_url="redis://fake"))

    def fail_from_url(*args, **kwargs):
        raise OSError("redis down")

    monkeypatch.setattr(response_cache.redis, "from_url", fail_from_url)
    response_cache.clear_response_cache()

    response_cache.put_cached_response("abc", {"content": "memory"}, ttl_seconds=60)
    payload = response_cache.get_cached_response("abc")

    assert payload == {"content": "memory"}


def test_semantic_cache_returns_similar_payload(monkeypatch) -> None:
    monkeypatch.setattr(response_cache, "get_settings", lambda: Settings(llmproxy_redis_url="redis://fake"))

    def fail_from_url(*args, **kwargs):
        raise OSError("redis down")

    monkeypatch.setattr(response_cache.redis, "from_url", fail_from_url)
    response_cache.clear_response_cache()

    namespace = response_cache.semantic_namespace(provider_key="openai", model_id="gpt-5.5", requested_model="proxy-auto")
    response_cache.put_semantic_cached_response(namespace, [1.0, 0.0], {"content": "close enough"}, ttl_seconds=60)

    payload = response_cache.get_semantic_cached_response(namespace, [0.99, 0.01], min_similarity=0.95, max_candidates=10)

    assert payload == {"content": "close enough"}
