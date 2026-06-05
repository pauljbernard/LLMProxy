"""Telemetry helpers."""

from __future__ import annotations

from datetime import datetime, timezone


def emit_metric(name: str, value: float, *, attributes: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "metric": name,
        "value": value,
        "attributes": attributes or {},
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }


def emit_counter(name: str, *, increment: int = 1, attributes: dict[str, object] | None = None) -> dict[str, object]:
    return emit_metric(name, float(increment), attributes=attributes)
