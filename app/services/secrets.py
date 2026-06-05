"""Secret helpers."""

import os


def require_secret(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required secret: {name}")
    return value
