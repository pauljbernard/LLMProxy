"""Integration event schemas."""

from pydantic import BaseModel


class IntegrationEvent(BaseModel):
    event_id: str
    event_type: str
    source: str
    payload: dict[str, object]
