"""Secret helpers."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class SecretReference:
    name: str
    source: str


def get_secret(name: str) -> tuple[str | None, SecretReference]:
    value = os.getenv(name)
    source = "environment"
    if not value:
        file_value = os.getenv(f"{name}_FILE")
        if file_value:
            with open(file_value, encoding="utf-8") as handle:
                value = handle.read().strip()
            source = "file"
    return value, SecretReference(name=name, source=source)


def require_secret(name: str) -> str:
    value, _ = get_secret(name)
    if not value:
        raise RuntimeError(f"Missing required secret: {name}")
    return value
