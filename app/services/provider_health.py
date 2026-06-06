"""Process-local provider retry/cooldown tracking."""

from __future__ import annotations

from dataclasses import dataclass
from time import time


@dataclass
class _ProviderFailureState:
    consecutive_failures: int = 0
    cooldown_until_epoch: float = 0.0


_STATE: dict[str, _ProviderFailureState] = {}


def _entry(provider_key: str) -> _ProviderFailureState:
    if provider_key not in _STATE:
        _STATE[provider_key] = _ProviderFailureState()
    return _STATE[provider_key]


def clear_provider_health_state() -> None:
    _STATE.clear()


def is_provider_cooled_down(provider_key: str) -> bool:
    state = _entry(provider_key)
    return state.cooldown_until_epoch > time()


def record_provider_success(provider_key: str) -> None:
    state = _entry(provider_key)
    state.consecutive_failures = 0
    state.cooldown_until_epoch = 0.0


def record_provider_failure(provider_key: str, *, allowed_fails: int, cooldown_seconds: int) -> bool:
    state = _entry(provider_key)
    state.consecutive_failures += 1
    if state.consecutive_failures >= allowed_fails:
        state.cooldown_until_epoch = time() + float(cooldown_seconds)
        return True
    return False


def provider_health_snapshot() -> dict[str, dict[str, float | int | bool]]:
    now = time()
    return {
        provider_key: {
            "consecutive_failures": state.consecutive_failures,
            "cooled_down": state.cooldown_until_epoch > now,
            "cooldown_remaining_seconds": max(0.0, state.cooldown_until_epoch - now),
        }
        for provider_key, state in _STATE.items()
    }
