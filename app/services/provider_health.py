"""Provider retry/cooldown tracking with Redis-backed shared state."""

from __future__ import annotations

from dataclasses import dataclass
from time import time
from typing import Protocol

import redis

from app.config import get_settings


@dataclass
class _ProviderFailureState:
    consecutive_failures: int = 0
    cooldown_until_epoch: float = 0.0


class _ProviderHealthBackend(Protocol):
    def clear(self) -> None: ...

    def get_state(self, provider_key: str) -> _ProviderFailureState: ...

    def set_state(self, provider_key: str, state: _ProviderFailureState) -> None: ...

    def snapshot(self) -> dict[str, dict[str, float | int | bool]]: ...


class _InMemoryProviderHealthBackend:
    def __init__(self) -> None:
        self._state: dict[str, _ProviderFailureState] = {}

    def _entry(self, provider_key: str) -> _ProviderFailureState:
        if provider_key not in self._state:
            self._state[provider_key] = _ProviderFailureState()
        return self._state[provider_key]

    def clear(self) -> None:
        self._state.clear()

    def get_state(self, provider_key: str) -> _ProviderFailureState:
        return self._entry(provider_key)

    def set_state(self, provider_key: str, state: _ProviderFailureState) -> None:
        self._state[provider_key] = state

    def snapshot(self) -> dict[str, dict[str, float | int | bool]]:
        now = time()
        return {
            provider_key: {
                "consecutive_failures": state.consecutive_failures,
                "cooled_down": state.cooldown_until_epoch > now,
                "cooldown_remaining_seconds": max(0.0, state.cooldown_until_epoch - now),
            }
            for provider_key, state in self._state.items()
        }


class _RedisProviderHealthBackend:
    KEY_PREFIX = "llmproxy:provider_health"

    def __init__(self, url: str) -> None:
        self._client = redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=0.2,
            socket_timeout=0.2,
        )
        self._client.ping()

    def _key(self, provider_key: str) -> str:
        return f"{self.KEY_PREFIX}:{provider_key}"

    @staticmethod
    def _snapshot_payload(state: _ProviderFailureState) -> dict[str, float | int | bool]:
        now = time()
        return {
            "consecutive_failures": state.consecutive_failures,
            "cooled_down": state.cooldown_until_epoch > now,
            "cooldown_remaining_seconds": max(0.0, state.cooldown_until_epoch - now),
        }

    def clear(self) -> None:
        keys = list(self._client.scan_iter(match=f"{self.KEY_PREFIX}:*"))
        if keys:
            self._client.delete(*keys)

    def get_state(self, provider_key: str) -> _ProviderFailureState:
        payload = self._client.hgetall(self._key(provider_key))
        if not payload:
            return _ProviderFailureState()
        return _ProviderFailureState(
            consecutive_failures=int(payload.get("consecutive_failures") or 0),
            cooldown_until_epoch=float(payload.get("cooldown_until_epoch") or 0.0),
        )

    def set_state(self, provider_key: str, state: _ProviderFailureState) -> None:
        self._client.hset(
            self._key(provider_key),
            mapping={
                "consecutive_failures": state.consecutive_failures,
                "cooldown_until_epoch": state.cooldown_until_epoch,
            },
        )

    def snapshot(self) -> dict[str, dict[str, float | int | bool]]:
        snapshot: dict[str, dict[str, float | int | bool]] = {}
        for key in self._client.scan_iter(match=f"{self.KEY_PREFIX}:*"):
            provider_key = str(key).split(":", 2)[-1]
            snapshot[provider_key] = self._snapshot_payload(self.get_state(provider_key))
        return snapshot


_MEMORY_BACKEND = _InMemoryProviderHealthBackend()
_BACKEND: _ProviderHealthBackend | None = None
_BACKEND_URL: str | None = None


def _resolve_backend() -> _ProviderHealthBackend:
    global _BACKEND, _BACKEND_URL
    settings = get_settings()
    redis_url = settings.llmproxy_redis_url
    if _BACKEND is not None and _BACKEND_URL == redis_url:
        return _BACKEND
    try:
        _BACKEND = _RedisProviderHealthBackend(redis_url)
    except Exception:
        _BACKEND = _MEMORY_BACKEND
    _BACKEND_URL = redis_url
    return _BACKEND


def _with_backend(action):
    backend = _resolve_backend()
    try:
        return action(backend)
    except redis.RedisError:
        global _BACKEND
        _BACKEND = _MEMORY_BACKEND
        return action(_MEMORY_BACKEND)


def clear_provider_health_state() -> None:
    global _BACKEND, _BACKEND_URL
    try:
        _with_backend(lambda backend: backend.clear())
    finally:
        _MEMORY_BACKEND.clear()
        _BACKEND = None
        _BACKEND_URL = None


def is_provider_cooled_down(provider_key: str) -> bool:
    state = _with_backend(lambda backend: backend.get_state(provider_key))
    return state.cooldown_until_epoch > time()


def record_provider_success(provider_key: str) -> None:
    state = _with_backend(lambda backend: backend.get_state(provider_key))
    state.consecutive_failures = 0
    state.cooldown_until_epoch = 0.0
    _with_backend(lambda backend: backend.set_state(provider_key, state))


def record_provider_failure(provider_key: str, *, allowed_fails: int, cooldown_seconds: int) -> bool:
    state = _with_backend(lambda backend: backend.get_state(provider_key))
    state.consecutive_failures += 1
    if state.consecutive_failures >= allowed_fails:
        state.cooldown_until_epoch = time() + float(cooldown_seconds)
        _with_backend(lambda backend: backend.set_state(provider_key, state))
        return True
    _with_backend(lambda backend: backend.set_state(provider_key, state))
    return False


def provider_health_snapshot() -> dict[str, dict[str, float | int | bool]]:
    return _with_backend(lambda backend: backend.snapshot())
