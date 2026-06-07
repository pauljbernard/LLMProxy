"""Response cache for successful chat completions with Redis-backed sharing."""

from __future__ import annotations

import json
from hashlib import sha256
from time import time
from typing import Any

import redis

from app.config import get_settings


_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_SEMANTIC_CACHE: dict[str, list[tuple[float, list[float], dict[str, Any]]]] = {}
_BACKEND: str | None = None
_BACKEND_URL: str | None = None
_REDIS: redis.Redis | None = None
_KEY_PREFIX = "llmproxy:response_cache"


def _memory_clear() -> None:
    _CACHE.clear()
    _SEMANTIC_CACHE.clear()


def _resolve_redis() -> redis.Redis | None:
    global _BACKEND, _BACKEND_URL, _REDIS
    settings = get_settings()
    redis_url = settings.llmproxy_redis_url
    if _BACKEND_URL == redis_url:
        return _REDIS if _BACKEND == "redis" else None
    try:
        client = redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=0.2,
            socket_timeout=0.2,
        )
        client.ping()
        _REDIS = client
        _BACKEND = "redis"
    except Exception:
        _REDIS = None
        _BACKEND = "memory"
    _BACKEND_URL = redis_url
    return _REDIS


def _with_cache_backend(redis_action, memory_action):
    client = _resolve_redis()
    if client is None:
        return memory_action()
    try:
        return redis_action(client)
    except redis.RedisError:
        global _BACKEND, _REDIS
        _BACKEND = "memory"
        _REDIS = None
        return memory_action()


def _redis_key(key: str) -> str:
    return f"{_KEY_PREFIX}:{key}"


def _semantic_index_key(namespace: str) -> str:
    return f"{_KEY_PREFIX}:semantic:index:{namespace}"


def _semantic_entry_key(namespace: str, entry_key: str) -> str:
    return f"{_KEY_PREFIX}:semantic:entry:{namespace}:{entry_key}"


def clear_response_cache() -> None:
    global _BACKEND, _BACKEND_URL, _REDIS
    try:
        def _clear_redis(client: redis.Redis) -> None:
            keys = list(client.scan_iter(match=f"{_KEY_PREFIX}:*"))
            if keys:
                client.delete(*keys)

        _with_cache_backend(_clear_redis, _memory_clear)
    finally:
        _memory_clear()
        _BACKEND = None
        _BACKEND_URL = None
        _REDIS = None


def cache_key(payload: dict[str, Any]) -> str:
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def get_cached_response(key: str) -> dict[str, Any] | None:
    def _get_redis(client: redis.Redis) -> dict[str, Any] | None:
        payload = client.get(_redis_key(key))
        if payload is None:
            return None
        return dict(json.loads(payload))

    def _get_memory() -> dict[str, Any] | None:
        item = _CACHE.get(key)
        if item is None:
            return None
        expires_at, payload = item
        if expires_at <= time():
            _CACHE.pop(key, None)
            return None
        return dict(payload)

    return _with_cache_backend(_get_redis, _get_memory)


def put_cached_response(key: str, payload: dict[str, Any], *, ttl_seconds: int) -> None:
    def _put_redis(client: redis.Redis) -> None:
        client.set(_redis_key(key), json.dumps(payload, sort_keys=True), ex=max(1, int(ttl_seconds)))

    def _put_memory() -> None:
        _CACHE[key] = (time() + ttl_seconds, dict(payload))

    _with_cache_backend(_put_redis, _put_memory)


def semantic_namespace(*, provider_key: str, model_id: str, requested_model: str) -> str:
    return sha256(
        json.dumps(
            {
                "provider_key": provider_key,
                "model_id": model_id,
                "requested_model": requested_model,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return -1.0
    dot = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = sum(a * a for a in left) ** 0.5
    right_norm = sum(b * b for b in right) ** 0.5
    if left_norm == 0.0 or right_norm == 0.0:
        return -1.0
    return dot / (left_norm * right_norm)


def get_semantic_cached_response(
    namespace: str,
    embedding: list[float],
    *,
    min_similarity: float,
    max_candidates: int,
) -> dict[str, Any] | None:
    def _get_redis(client: redis.Redis) -> dict[str, Any] | None:
        best_payload: dict[str, Any] | None = None
        best_score = min_similarity
        now = time()
        scanned = 0
        for entry_key in client.smembers(_semantic_index_key(namespace)):
            if scanned >= max_candidates:
                break
            payload_raw = client.get(str(entry_key))
            if payload_raw is None:
                client.srem(_semantic_index_key(namespace), str(entry_key))
                continue
            item = json.loads(payload_raw)
            if float(item.get("expires_at", 0.0)) <= now:
                client.delete(str(entry_key))
                client.srem(_semantic_index_key(namespace), str(entry_key))
                continue
            score = _cosine_similarity(embedding, [float(value) for value in item.get("embedding", [])])
            if score >= best_score:
                best_score = score
                best_payload = dict(item.get("payload") or {})
            scanned += 1
        return best_payload

    def _get_memory() -> dict[str, Any] | None:
        items = _SEMANTIC_CACHE.get(namespace, [])
        if not items:
            return None
        now = time()
        kept: list[tuple[float, list[float], dict[str, Any]]] = []
        best_payload: dict[str, Any] | None = None
        best_score = min_similarity
        for expires_at, candidate_embedding, payload in items[:max_candidates]:
            if expires_at <= now:
                continue
            kept.append((expires_at, candidate_embedding, payload))
            score = _cosine_similarity(embedding, candidate_embedding)
            if score >= best_score:
                best_score = score
                best_payload = dict(payload)
        _SEMANTIC_CACHE[namespace] = kept
        return best_payload

    return _with_cache_backend(_get_redis, _get_memory)


def put_semantic_cached_response(
    namespace: str,
    embedding: list[float],
    payload: dict[str, Any],
    *,
    ttl_seconds: int,
) -> None:
    entry_key = cache_key({"namespace": namespace, "embedding": embedding, "payload": payload})
    expires_at = time() + ttl_seconds

    def _put_redis(client: redis.Redis) -> None:
        redis_entry_key = _semantic_entry_key(namespace, entry_key)
        client.set(
            redis_entry_key,
            json.dumps(
                {
                    "embedding": embedding,
                    "payload": payload,
                    "expires_at": expires_at,
                },
                sort_keys=True,
            ),
            ex=max(1, int(ttl_seconds)),
        )
        client.sadd(_semantic_index_key(namespace), redis_entry_key)
        client.expire(_semantic_index_key(namespace), max(1, int(ttl_seconds)))

    def _put_memory() -> None:
        items = _SEMANTIC_CACHE.setdefault(namespace, [])
        items.append((expires_at, list(embedding), dict(payload)))
        _SEMANTIC_CACHE[namespace] = items[-200:]

    _with_cache_backend(_put_redis, _put_memory)
