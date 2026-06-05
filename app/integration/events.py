"""Integration event helpers."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import IntegrationEvent
from app.proxy.recorder import generate_prefixed_id
from app.services.observability import log_record


def emit_event(
    session: Session | None,
    *,
    event_type: str,
    source: str,
    payload: dict[str, object],
) -> IntegrationEvent | None:
    if session is None or not hasattr(session, "add"):
        return None
    event = IntegrationEvent(
        id=generate_prefixed_id("intevt"),
        event_id=generate_prefixed_id("evt"),
        event_type=event_type,
        source=source,
        payload_json=payload,
    )
    session.add(event)
    try:
        log_record(
            get_settings(),
            level="INFO",
            component="integration.events",
            category="event",
            message=f"Event emitted: {event_type}",
            data={
                "event_id": event.event_id,
                "integration_event_id": event.id,
                "source": source,
                "payload": payload,
            },
        )
    except Exception:
        pass
    return event
