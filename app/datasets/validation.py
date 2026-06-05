"""Dataset validation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.schemas.dataset import DatasetImportRequest


def validate_dataset(request: DatasetImportRequest) -> tuple[dict[str, object], list[dict[str, object]]]:
    manifest_path = Path(request.manifest_path)
    data_path = Path(request.data_path)
    if not manifest_path.exists():
        raise ValueError("Dataset manifest is missing.")
    if not data_path.exists():
        raise ValueError("Dataset export file is missing.")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    required_manifest_fields = {
        "schema_version",
        "dataset_export_id",
        "name",
        "domain",
        "record_count",
        "export_file",
        "sha256",
        "candidate_status",
    }
    missing_manifest_fields = required_manifest_fields - manifest.keys()
    if missing_manifest_fields:
        raise ValueError(f"Dataset manifest is missing required fields: {sorted(missing_manifest_fields)}")

    content = data_path.read_text(encoding="utf-8")
    checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
    if checksum != manifest["sha256"]:
        raise ValueError("Dataset checksum does not match manifest.")

    records = [json.loads(line) for line in content.splitlines() if line.strip()]
    if len(records) != int(manifest["record_count"]):
        raise ValueError("Dataset record count does not match manifest.")

    for record in records:
        if not record.get("messages"):
            raise ValueError("Dataset record must contain messages.")
        roles = {message.get("role") for message in record["messages"]}
        if "user" not in roles or "assistant" not in roles:
            raise ValueError("Dataset record must contain both user and assistant turns.")
        if not record.get("selected_response"):
            raise ValueError("Dataset record must contain a selected_response.")
        if record.get("approval_status") != "approved":
            raise ValueError("Dataset record must be approved before import.")
        if record.get("export_eligible") is not True:
            raise ValueError("Dataset record must be export eligible before import.")
        metadata = record.get("metadata", {})
        if not record.get("domain") or not record.get("task_type"):
            raise ValueError("Dataset record must include domain and task_type.")
        if not metadata:
            raise ValueError("Dataset record must include metadata.")
    return manifest, records
