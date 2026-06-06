"""API dependencies."""

from collections.abc import Generator
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.session import get_async_db_session, get_db_session

security = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthPrincipal:
    token: str
    role: str


def get_runtime_settings() -> Settings:
    return get_settings()


def require_api_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    settings: Settings = Depends(get_runtime_settings),
) -> AuthPrincipal:
    if credentials is None or credentials.credentials not in settings.auth_tokens:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid bearer token.",
        )
    if credentials.credentials in settings.operator_tokens:
        return AuthPrincipal(token=credentials.credentials, role="operator")
    if credentials.credentials in settings.automation_tokens:
        return AuthPrincipal(token=credentials.credentials, role="automation")
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


def get_session() -> Generator[Session, None, None]:
    yield from get_db_session()


async def get_async_session() -> AsyncSession:
    async for session in get_async_db_session():
        return session
    raise RuntimeError("Async session generator did not yield a session.")
