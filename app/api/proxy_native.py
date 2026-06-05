"""Native proxy endpoints."""

from fastapi import APIRouter

router = APIRouter(prefix="/proxy", tags=["proxy-native"])


@router.post("/ensemble")
async def ensemble() -> dict[str, str]:
    return {"status": "not_implemented"}


@router.get("/training-candidates")
async def list_training_candidates() -> dict[str, list[object]]:
    return {"items": []}


@router.post("/models/register")
async def register_model() -> dict[str, str]:
    return {"status": "not_implemented"}
