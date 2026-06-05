"""Dataset exporter."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import DatasetExport, TrainingCandidate
from app.integration.events import emit_event
from app.proxy.recorder import generate_prefixed_id
from app.schemas.candidate import DatasetExportRequest, DatasetExportResponse


def _build_manifest(
    *,
    dataset_export_id: str,
    name: str,
    domain: str,
    export_file: str,
    record_count: int,
    sha256: str,
    min_quality_score: float,
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "dataset_export_id": dataset_export_id,
        "name": name,
        "domain": domain,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "record_count": record_count,
        "source_system": "llmproxy",
        "export_file": export_file,
        "sha256": sha256,
        "min_quality_score": min_quality_score,
        "candidate_status": "approved",
        "schema_versions": ["1.0"],
        "compatible_learner_versions": ["0.1.0"],
    }


def export_candidates(
    session: Session,
    *,
    request: DatasetExportRequest,
    settings: Settings,
) -> DatasetExportResponse:
    candidates = list(
        session.execute(
            select(TrainingCandidate).where(
                TrainingCandidate.domain == request.domain,
                TrainingCandidate.approval_status == "approved",
                TrainingCandidate.export_eligible.is_(True),
                TrainingCandidate.quality_score >= request.min_quality_score,
            )
        ).scalars()
    )
    if not candidates:
        raise ValueError(f"No approved exportable candidates found for domain '{request.domain}'.")

    export_dir = Path(settings.llmproxy_exports_path)
    export_dir.mkdir(parents=True, exist_ok=True)

    dataset_export_id = generate_prefixed_id("dsexp")
    export_name = request.name or f"{request.domain}-adapter"
    data_path = export_dir / f"{export_name}-{dataset_export_id}.jsonl"
    manifest_path = export_dir / f"{export_name}-{dataset_export_id}.manifest.json"

    lines: list[str] = []
    for candidate in candidates:
        messages = [dict(message) for message in candidate.messages_json]
        if not messages or messages[-1].get("role") != "assistant":
            messages.append({"role": "assistant", "content": candidate.selected_response})
        record = {
            "schema_version": "1.0",
            "candidate_id": candidate.id,
            "domain": candidate.domain,
            "task_type": candidate.task_type,
            "messages": messages,
            "selected_response": candidate.selected_response,
            "quality_score": candidate.quality_score,
            "approval_status": candidate.approval_status,
            "export_eligible": candidate.export_eligible,
            "provenance": candidate.provenance_json,
            "validation": candidate.validation_json,
            "metadata": candidate.metadata_json,
        }
        lines.append(json.dumps(record, sort_keys=True))

    content = "\n".join(lines) + "\n"
    data_path.write_text(content, encoding="utf-8")
    sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()

    manifest = _build_manifest(
        dataset_export_id=dataset_export_id,
        name=export_name,
        domain=request.domain,
        export_file=data_path.name,
        record_count=len(candidates),
        sha256=sha256,
        min_quality_score=request.min_quality_score,
    )
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    dataset_export = DatasetExport(
        id=generate_prefixed_id("dsexprec"),
        domain=request.domain,
        dataset_export_id=dataset_export_id,
        manifest_path=str(manifest_path),
        data_path=str(data_path),
        record_count=len(candidates),
        sha256=sha256,
        schema_version="1.0",
    )
    session.add(dataset_export)
    emit_event(
        session,
        event_type="dataset.exported",
        source="llmproxy",
        payload={
            "dataset_export_id": dataset_export_id,
            "manifest_path": str(manifest_path),
            "data_path": str(data_path),
            "domain": request.domain,
            "record_count": len(candidates),
        },
    )

    for candidate in candidates:
        candidate.status = "exported"

    return DatasetExportResponse(
        dataset_export_id=dataset_export_id,
        manifest_path=str(manifest_path),
        data_path=str(data_path),
        record_count=len(candidates),
    )
