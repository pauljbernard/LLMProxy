"""Evaluation endpoints."""

from fastapi import APIRouter

router = APIRouter(prefix="/evaluation", tags=["evaluation"])


@router.get("/runs")
async def list_evaluation_runs() -> dict[str, list[object]]:
    return {"items": []}
