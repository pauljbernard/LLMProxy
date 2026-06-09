"""Evaluation endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_runtime_settings, get_session, require_api_token, require_operator_token, require_platform_listener
from app.config import Settings
from app.db.models import EvaluationRun
from app.evaluation.runner import create_evaluation_run, list_evaluation_runs
from app.integration.performance import generate_kpi_report
from app.schemas.evaluation import EvaluationEnqueueResponse, EvaluationRunRequest, EvaluationRunView
from app.schemas.integration import KpiReportResponse

router = APIRouter(prefix="/evaluation", tags=["evaluation"], dependencies=[Depends(require_platform_listener)])


def _evaluation_run_view(run: EvaluationRun) -> EvaluationRunView:
    return EvaluationRunView(
        id=run.id,
        training_run_id=run.training_run_id,
        domain=run.domain,
        frontier_baseline_name=run.frontier_baseline_name,
        status=run.status,
        overall_score=run.overall_score,
        quality_delta_vs_frontier=run.quality_delta_vs_frontier,
        value_per_dollar_gain_vs_frontier=run.value_per_dollar_gain_vs_frontier,
        promotion_status=run.promotion_status,
        package_manifest_path=str(run.result_json.get("package_manifest_path", "")) or None,
    )


@router.post(
    "/runs",
    response_model=EvaluationEnqueueResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_operator_token)],
)
def submit_evaluation_run(
    request: EvaluationRunRequest,
    response: Response,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
) -> EvaluationEnqueueResponse:
    try:
        payload = create_evaluation_run(session, request=request, settings=settings)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    session.commit()
    response.status_code = status.HTTP_202_ACCEPTED
    return payload


@router.get("/runs", dependencies=[Depends(require_api_token)])
def list_evaluation_runs_endpoint(
    paginated: bool = False,
    limit: int = Query(default=20, le=200),
    offset: int = Query(default=0, ge=0),
    domain: str | None = None,
    promotion_status: str | None = None,
    session: Session = Depends(get_session),
) -> list[EvaluationRunView] | dict[str, Any]:
    if paginated:
        statement = select(EvaluationRun)
        if domain:
            statement = statement.where(EvaluationRun.domain == domain)
        if promotion_status:
            statement = statement.where(EvaluationRun.promotion_status == promotion_status)
        total = int(session.execute(select(func.count()).select_from(statement.subquery())).scalar_one())
        rows = list(
            session.execute(
                statement.order_by(EvaluationRun.created_at.desc()).limit(limit).offset(offset)
            ).scalars()
        )
        return {
            "items": [_evaluation_run_view(run).model_dump(mode="json") for run in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    runs = list_evaluation_runs(session)
    return [_evaluation_run_view(run) for run in runs]


@router.get("/kpis", response_model=KpiReportResponse, dependencies=[Depends(require_api_token)])
def get_kpi_report(
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_runtime_settings),
) -> KpiReportResponse:
    return generate_kpi_report(session, settings=settings)
