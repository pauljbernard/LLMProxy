"""Dataset schemas."""

from pydantic import BaseModel


class DatasetImportRequest(BaseModel):
    dataset_export_id: str
    manifest_path: str
    data_path: str


class DatasetImportResponse(BaseModel):
    dataset_export_id: str
    dataset_import_id: str
    dataset_version_id: str
    status: str
    record_count: int
