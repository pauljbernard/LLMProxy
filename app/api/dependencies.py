"""API dependencies."""

from collections.abc import AsyncGenerator, Generator
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.models import VirtualAPIKey
from app.db.session import get_async_db_session, get_db_session

security = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthPrincipal:
    token: str
    role: str
    key_id: str | None = None
    owner_id: str | None = None
    models_allowed: tuple[str, ...] = ()
    spend_usd: float | None = None
    max_budget_usd: float | None = None


def get_runtime_settings() -> Settings:
    return get_settings()


def virtual_key_hash(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def resolve_virtual_api_key(token: str, session: Session) -> VirtualAPIKey | None:
    token = token.strip()
    if not token:
        return None
    result = session.execute(
        select(VirtualAPIKey).where(
            VirtualAPIKey.key_hash == virtual_key_hash(token),
            VirtualAPIKey.status == "active",
        )
    ).scalar_one_or_none()
    return result


def enforce_model_access(principal: AuthPrincipal, requested_model: str) -> None:
    if not principal.models_allowed:
        return
    if requested_model in principal.models_allowed:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="This API key is not allowed to access the requested model.",
    )


def enforce_budget(principal: AuthPrincipal) -> None:
    if principal.max_budget_usd is None or principal.spend_usd is None:
        return
    if principal.spend_usd < principal.max_budget_usd:
        return
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="This API key has exhausted its configured budget.",
    )


def record_virtual_key_usage(session: Session, principal: AuthPrincipal, *, cost_usd: float) -> None:
    if not principal.key_id:
        return
    record = session.get(VirtualAPIKey, principal.key_id)
    if record is None:
        return
    record.last_used_at = datetime.now(timezone.utc)
    record.spend_usd = record.spend_usd + cost_usd


def get_session() -> Generator[Session, None, None]:
    yield from get_db_session()


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_async_db_session():
        yield session


def require_api_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    settings: Settings = Depends(get_runtime_settings),
    session: Session = Depends(get_session),
) -> AuthPrincipal:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid bearer token.",
        )
    token = credentials.credentials
    if token in settings.operator_tokens:
        return AuthPrincipal(token=token, role="operator")
    if token in settings.automation_tokens:
        return AuthPrincipal(token=token, role="automation")
    virtual_key = resolve_virtual_api_key(token, session)
    if virtual_key is not None:
        return AuthPrincipal(
            token=token,
            role=str(virtual_key.role),
            key_id=virtual_key.id,
            owner_id=virtual_key.owner_id,
            models_allowed=tuple(str(item) for item in (virtual_key.models_allowed_json or [])),
            spend_usd=float(virtual_key.spend_usd),
            max_budget_usd=float(virtual_key.max_budget_usd) if virtual_key.max_budget_usd is not None else None,
        )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing or invalid bearer token.",
    )


def require_operator_token(
    principal: AuthPrincipal = Depends(require_api_token),
) -> AuthPrincipal:
    if principal.role != "operator":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operator token required for this action.",
        )
    return principal
