"""Shared virtual API key schemas and operations."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from secrets import token_urlsafe
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import virtual_key_hash
from app.db.models import VirtualAPIKey


class VirtualKeyCreateRequest(BaseModel):
    display_name: str | None = None
    owner_id: str | None = None
    role: str = "api"
    models_allowed: list[str] = Field(default_factory=list)
    rpm_limit: int | None = None
    tpm_limit: int | None = None
    max_budget_usd: float | None = None
    budget_reset_period: str | None = None
    budget_reset_at: datetime | None = None


class VirtualKeyUpdateRequest(BaseModel):
    display_name: str | None = None
    owner_id: str | None = None
    role: str | None = None
    models_allowed: list[str] | None = None
    rpm_limit: int | None = None
    tpm_limit: int | None = None
    max_budget_usd: float | None = None
    budget_reset_period: str | None = None
    budget_reset_at: datetime | None = None
    status: str | None = None


class VirtualKeyView(BaseModel):
    id: str
    key_prefix: str
    display_name: str | None = None
    owner_id: str | None = None
    role: str
    status: str
    models_allowed: list[str]
    rpm_limit: int | None = None
    tpm_limit: int | None = None
    spend_usd: float
    max_budget_usd: float | None = None
    budget_reset_period: str | None = None
    budget_reset_at: str | None = None
    last_used_at: str | None = None
    created_at: str


class VirtualKeyCreateResponse(VirtualKeyView):
    token: str


class VirtualKeyRotateResponse(VirtualKeyCreateResponse):
    previous_key_prefix: str


def virtual_key_payload(item: VirtualAPIKey) -> dict[str, Any]:
    return {
        "id": item.id,
        "key_prefix": item.key_prefix,
        "display_name": item.display_name,
        "owner_id": item.owner_id,
        "role": item.role,
        "status": item.status,
        "models_allowed": [str(value) for value in (item.models_allowed_json or [])],
        "rpm_limit": item.rpm_limit,
        "tpm_limit": item.tpm_limit,
        "spend_usd": float(item.spend_usd) if item.spend_usd is not None else 0.0,
        "max_budget_usd": float(item.max_budget_usd) if item.max_budget_usd is not None else None,
        "budget_reset_period": item.budget_reset_period,
        "budget_reset_at": item.budget_reset_at.isoformat() if item.budget_reset_at else None,
        "last_used_at": item.last_used_at.isoformat() if item.last_used_at else None,
        "created_at": item.created_at.isoformat(),
    }


def list_virtual_key_records(session: Session) -> list[VirtualAPIKey]:
    return session.execute(
        select(VirtualAPIKey).order_by(VirtualAPIKey.created_at.desc())
    ).scalars().all()


def create_virtual_key_record(session: Session, request: VirtualKeyCreateRequest) -> tuple[VirtualAPIKey, str]:
    raw_token = f"sk-{token_urlsafe(24)}"
    record = VirtualAPIKey(
        id=f"vkey_{uuid4().hex}",
        key_prefix=raw_token[:12],
        key_hash=virtual_key_hash(raw_token),
        display_name=request.display_name,
        owner_id=request.owner_id,
        role=request.role,
        status="active",
        models_allowed_json=request.models_allowed,
        rpm_limit=request.rpm_limit,
        tpm_limit=request.tpm_limit,
        max_budget_usd=request.max_budget_usd,
        budget_reset_period=request.budget_reset_period,
        budget_reset_at=request.budget_reset_at,
        spend_usd=Decimal("0"),
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record, raw_token


def get_virtual_key_or_404(session: Session, key_id: str) -> VirtualAPIKey:
    record = session.get(VirtualAPIKey, key_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Virtual API key not found.")
    return record


def disable_virtual_key_record(session: Session, key_id: str) -> VirtualAPIKey:
    record = get_virtual_key_or_404(session, key_id)
    record.status = "disabled"
    session.commit()
    session.refresh(record)
    return record


def update_virtual_key_record(
    session: Session,
    key_id: str,
    request: VirtualKeyUpdateRequest,
) -> VirtualAPIKey:
    record = get_virtual_key_or_404(session, key_id)
    if request.display_name is not None:
        record.display_name = request.display_name
    if request.owner_id is not None:
        record.owner_id = request.owner_id
    if request.role is not None:
        record.role = request.role
    if request.models_allowed is not None:
        record.models_allowed_json = request.models_allowed
    if request.rpm_limit is not None:
        record.rpm_limit = request.rpm_limit
    if request.tpm_limit is not None:
        record.tpm_limit = request.tpm_limit
    if request.max_budget_usd is not None:
        record.max_budget_usd = request.max_budget_usd
    if request.budget_reset_period is not None:
        record.budget_reset_period = request.budget_reset_period
    if request.budget_reset_at is not None:
        record.budget_reset_at = request.budget_reset_at
    if request.status is not None:
        record.status = request.status
    session.commit()
    session.refresh(record)
    return record


def rotate_virtual_key_record(session: Session, key_id: str) -> tuple[VirtualAPIKey, str, str]:
    record = get_virtual_key_or_404(session, key_id)
    previous_key_prefix = str(record.key_prefix)
    raw_token = f"sk-{token_urlsafe(24)}"
    record.key_prefix = raw_token[:12]
    record.key_hash = virtual_key_hash(raw_token)
    record.last_used_at = datetime.now(timezone.utc)
    session.commit()
    session.refresh(record)
    return record, raw_token, previous_key_prefix
