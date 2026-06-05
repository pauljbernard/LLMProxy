"""Curriculum builder helpers."""

from __future__ import annotations


def build_curriculum(*, domain: str, record_count: int) -> dict[str, object]:
    stages = [
        {"name": "foundation", "target_share": 0.4},
        {"name": "intermediate", "target_share": 0.35},
        {"name": "advanced", "target_share": 0.25},
    ]
    return {
        "status": "ready",
        "domain": domain,
        "record_count": record_count,
        "stages": stages,
        "recommendation": f"Start with foundation examples for {domain}, then progress to harder domain tasks.",
    }
