"""In-memory MCP runtime status tracking."""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Any

_LOCK = Lock()
_STATE: dict[str, dict[str, Any]] = {}


def record_mcp_validation(*, server: str, success: bool, latency_ms: int | None = None, tool_count: int | None = None, error: str | None = None) -> None:
    with _LOCK:
        entry = _STATE.setdefault(server, _base_entry(server))
        entry["last_validation_at"] = datetime.now(timezone.utc).isoformat()
        entry["last_error"] = error
        entry["last_latency_ms"] = latency_ms
        if tool_count is not None:
            entry["tool_count"] = tool_count
        entry["validation_count"] += 1
        if success:
            entry["successful_validations"] += 1
            entry["status"] = "connected"
        else:
            entry["failed_validations"] += 1
            entry["status"] = "failed"


def record_mcp_tool_call(*, server: str, tool_name: str, success: bool, latency_ms: int | None = None, error: str | None = None) -> None:
    with _LOCK:
        entry = _STATE.setdefault(server, _base_entry(server))
        entry["last_tool_at"] = datetime.now(timezone.utc).isoformat()
        entry["last_tool_name"] = tool_name
        entry["last_error"] = error
        entry["tool_call_count"] += 1
        if latency_ms is not None:
            entry["last_latency_ms"] = latency_ms
        if success:
            entry["successful_tool_calls"] += 1
            if entry["status"] == "idle":
                entry["status"] = "connected"
        else:
            entry["failed_tool_calls"] += 1
            entry["status"] = "failed"


def mcp_runtime_snapshot() -> dict[str, dict[str, Any]]:
    with _LOCK:
        return {key: dict(value) for key, value in _STATE.items()}


def clear_mcp_runtime_state() -> None:
    with _LOCK:
        _STATE.clear()


def _base_entry(server: str) -> dict[str, Any]:
    return {
        "server": server,
        "status": "idle",
        "tool_count": 0,
        "validation_count": 0,
        "successful_validations": 0,
        "failed_validations": 0,
        "tool_call_count": 0,
        "successful_tool_calls": 0,
        "failed_tool_calls": 0,
        "last_validation_at": None,
        "last_tool_at": None,
        "last_tool_name": None,
        "last_latency_ms": None,
        "last_error": None,
    }
