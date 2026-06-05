"""Dataset import orchestration."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import Settings
from app.datasets.dedupe import dedupe_dataset
from app.datasets.normalization import normalize_dataset
from app.datasets.splitter import split_dataset
from app.datasets.validation import validate_dataset
from app.db.models import DatasetImport, DatasetVersion
from app.integration.events import emit_event
from app.proxy.recorder import generate_prefixed_id
from app.schemas.dataset import DatasetImportRequest, DatasetImportResponse


def import_dataset(
    session: Session,
    *,
    request: DatasetImportRequest,
    settings: Settings,
) -> DatasetImportResponse:
    manifest, records = validate_dataset(request)
    normalized = normalize_dataset(records)
    deduped = dedupe_dataset(normalized)
    splits = split_dataset(deduped)

    dataset_dir = Path(settings.llmproxy_datasets_path)
    dataset_dir.mkdir(parents=True, exist_ok=True)
    dataset_import_id = generate_prefixed_id("dsimp")
    version_id = generate_prefixed_id("dsv")
    version_name = f"{manifest['domain']}-{version_id}"

    train_path = dataset_dir / f"{version_name}-train.jsonl"
    validation_path = dataset_dir / f"{version_name}-validation.jsonl"
    test_path = dataset_dir / f"{version_name}-test.jsonl"

    for path, key in (
        (train_path, "train"),
        (validation_path, "validation"),
        (test_path, "test"),
    ):
        content = "\n".join(json.dumps(record, sort_keys=True) for record in splits[key])
        if content:
            content += "\n"
        path.write_text(content, encoding="utf-8")

    dataset_import = DatasetImport(
        id=dataset_import_id,
        dataset_export_id=request.dataset_export_id,
        manifest_path=request.manifest_path,
        data_path=request.data_path,
        status="imported",
        record_count=len(deduped),
        quarantined_count=len(records) - len(deduped),
    )
    session.add(dataset_import)

    dataset_version = DatasetVersion(
        id=version_id,
        domain=str(manifest["domain"]),
        version_name=version_name,
        source_import_id=dataset_import_id,
        train_path=str(train_path),
        validation_path=str(validation_path),
        test_path=str(test_path),
        record_count=len(deduped),
    )
    session.add(dataset_version)
    emit_event(
        session,
        event_type="dataset.imported",
        source="llmproxy",
        payload={
            "dataset_export_id": request.dataset_export_id,
            "dataset_import_id": dataset_import_id,
            "dataset_version_id": version_id,
            "domain": manifest["domain"],
        },
    )

    return DatasetImportResponse(
        dataset_export_id=request.dataset_export_id,
        dataset_import_id=dataset_import_id,
        dataset_version_id=version_id,
        status="imported",
        record_count=len(deduped),
    )
