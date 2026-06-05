"""Dataset schemas."""

from pydantic import BaseModel


class DatasetImportRequest(BaseModel):
    dataset_export_id: str
    manifest_path: str
    data_path: str
