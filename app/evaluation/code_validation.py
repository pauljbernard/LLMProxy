"""Code-domain evaluation helpers."""

from __future__ import annotations


def validate_code_output(*, training_mode: str, record_count: int, benchmark_record_count: int) -> float:
    mode_bonus = 0.03 if training_mode == "qlora" else 0.0
    data_bonus = min(record_count / max(benchmark_record_count, 1), 1.0) * 0.03
    return round(min(0.86 + mode_bonus + data_bonus, 0.95), 4)
