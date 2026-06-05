"""Dataset endpoints."""

from fastapi import APIRouter

from app.schemas.dataset import DatasetImportRequest

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.post("/import")
async def import_dataset(request: DatasetImportRequest) -> dict[str, str]:
    return {"dataset_export_id": request.dataset_export_id, "status": "accepted"}
