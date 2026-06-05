"""Telemetry helpers."""


def emit_metric(name: str, value: float) -> dict[str, float | str]:
    return {"metric": name, "value": value}
