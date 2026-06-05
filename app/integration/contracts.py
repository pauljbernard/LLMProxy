"""Integration contract metadata helpers."""


def contract_version() -> str:
    return "1.0.0"


def event_contract(event_type: str) -> dict[str, object]:
    return {
        "contract_version": contract_version(),
        "event_type": event_type,
        "delivery_mode": "postgres_outbox",
        "idempotency_key_fields": ["event_id"],
    }
