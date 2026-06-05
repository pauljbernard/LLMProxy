"""Deployment endpoints."""

from fastapi import APIRouter

router = APIRouter(prefix="/deployment", tags=["deployment"])


@router.post("/rollback")
async def rollback() -> dict[str, str]:
    return {"status": "not_implemented"}
