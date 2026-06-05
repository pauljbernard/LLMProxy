"""Style-domain evaluation helpers."""

from __future__ import annotations


def score_style(*, training_mode: str, record_count: int, benchmark_record_count: int) -> float:
    mode_bonus = 0.02 if training_mode == "qlora" else 0.0
    data_bonus = min(record_count / max(benchmark_record_count, 1), 1.0) * 0.04
    return round(min(0.83 + mode_bonus + data_bonus, 0.93), 4)
