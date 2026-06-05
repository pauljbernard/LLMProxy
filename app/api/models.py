"""Model registry endpoints."""

from fastapi import APIRouter

router = APIRouter(prefix="/models", tags=["models"])


@router.get("")
async def list_registered_models() -> dict[str, list[object]]:
    return {"items": []}
