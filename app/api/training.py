"""Training endpoints."""

from fastapi import APIRouter

router = APIRouter(prefix="/training", tags=["training"])


@router.get("/runs")
async def list_training_runs() -> dict[str, list[object]]:
    return {"items": []}
