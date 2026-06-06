"""Minimal in-memory response cache for successful chat completions."""

from __future__ import annotations

import json
from hashlib import sha256
from time import time
from typing import Any


_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def clear_response_cache() -> None:
    _CACHE.clear()


def cache_key(payload: dict[str, Any]) -> str:
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def get_cached_response(key: str) -> dict[str, Any] | None:
    item = _CACHE.get(key)
    if item is None:
        return None
    expires_at, payload = item
    if expires_at <= time():
        _CACHE.pop(key, None)
        return None
    return dict(payload)


def put_cached_response(key: str, payload: dict[str, Any], *, ttl_seconds: int) -> None:
    _CACHE[key] = (time() + ttl_seconds, dict(payload))
