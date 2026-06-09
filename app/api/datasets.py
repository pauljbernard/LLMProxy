"""Dataset endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_runtime_settings, get_session, require_api_token, require_platform_listener
from app.config import Settings
from app.datasets.ingestion import import_dataset as import_dataset_service
from app.schemas.dataset import DatasetImportRequest, DatasetImportResponse

router = APIRouter(prefix="/datasets", tags=["datasets"], dependencies=[Depends(require_platform_listener)])


@router.post("/import", response_model=DatasetImportResponse, dependencies=[Depends(require_api_token)])
def import_dataset(
    request: DatasetImportRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
) -> DatasetImportResponse:
    try:
        response = import_dataset_service(session, request=request, settings=settings)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    session.commit()
    return response
