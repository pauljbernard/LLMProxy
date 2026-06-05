import json
from pathlib import Path

import pytest

from app.datasets.validation import validate_dataset
from app.schemas.dataset import DatasetImportRequest


def test_validate_dataset_accepts_valid_export(tmp_path: Path) -> None:
    data_path = tmp_path / "data.jsonl"
    manifest_path = tmp_path / "manifest.json"
    record = {
        "schema_version": "1.0",
        "candidate_id": "cand_1",
        "domain": "coding",
        "task_type": "code_review",
        "messages": [
            {"role": "user", "content": "Review patch"},
            {"role": "assistant", "content": "Looks good"},
        ],
        "selected_response": "Looks good",
        "quality_score": 0.9,
        "approval_status": "approved",
        "export_eligible": True,
        "provenance": {},
        "validation": {},
        "metadata": {"domain": "coding", "task_type": "code_review"},
    }
    content = json.dumps(record) + "\n"
    data_path.write_text(content, encoding="utf-8")
    manifest = {
        "schema_version": "1.0",
        "dataset_export_id": "dsexp_1",
        "name": "coding-adapter",
        "domain": "coding",
        "record_count": 1,
        "export_file": data_path.name,
        "sha256": __import__("hashlib").sha256(content.encode("utf-8")).hexdigest(),
        "candidate_status": "approved",
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    manifest_result, records_result = validate_dataset(
        DatasetImportRequest(
            dataset_export_id="dsexp_1",
            manifest_path=str(manifest_path),
            data_path=str(data_path),
        )
    )

    assert manifest_result["dataset_export_id"] == "dsexp_1"
    assert len(records_result) == 1


def test_validate_dataset_rejects_checksum_mismatch(tmp_path: Path) -> None:
    data_path = tmp_path / "data.jsonl"
    manifest_path = tmp_path / "manifest.json"
    data_path.write_text("{}\n", encoding="utf-8")
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "dataset_export_id": "dsexp_1",
                "name": "coding-adapter",
                "domain": "coding",
                "record_count": 1,
                "export_file": data_path.name,
                "sha256": "bad",
                "candidate_status": "approved",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="checksum"):
        validate_dataset(
            DatasetImportRequest(
                dataset_export_id="dsexp_1",
                manifest_path=str(manifest_path),
                data_path=str(data_path),
            )
        )
