"""Admin CLI for llmProxy operations."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select, text

from app.api.openai_compatible import chat_completions
from app.api.proxy_native import ensemble as ensemble_chat
from app.config import Settings, get_settings
from app.datasets.ingestion import import_dataset
from app.db.models import (
    DatasetExport,
    DatasetImport,
    DatasetVersion,
    EvaluationRun,
    IntegrationEvent,
    JobQueueRecord,
    JudgeCritique,
    ModelPerformanceSample,
    ModelResponse,
    RequestLog,
    RoutingDecisionRecord,
    TrainingCandidate,
    TrainingRun,
)
from app.db.session import get_engine, get_session_factory
from app.deployment.manager import deploy_model, list_routing_policies, rollback_model
from app.evaluation.runner import create_evaluation_run, list_evaluation_runs, run_evaluation
from app.integration.outbox import process_pending_events
from app.integration.performance import generate_kpi_report
from app.integration.routing_policy import get_latest_policy
from app.operator_payloads import (
    dataset_export_payload,
    dataset_import_payload,
    dataset_version_payload,
    evaluation_run_payload,
    event_payload,
    job_payload,
    request_detail_payload,
    request_summary_payload,
    settings_payload,
    training_run_payload,
)
from app.proxy.candidates import (
    approve_training_candidate,
    get_training_candidate,
    list_training_candidates,
    reject_training_candidate,
)
from app.proxy.exporter import export_candidates
from app.registry.artifact_store import list_model_packages
from app.registry.model_registry import list_provider_capabilities, list_proxy_models
from app.schemas.candidate import DatasetExportRequest
from app.schemas.chat import ChatCompletionRequest, EmbeddingRequest, RequestMetadata, ChatMessage
from app.schemas.dataset import DatasetImportRequest
from app.schemas.evaluation import EvaluationRunRequest
from app.schemas.integration import DeploymentRequest
from app.schemas.registry import ModelRegistrationRequest
from app.schemas.training import TrainingRunRequest
from app.training.orchestrator import create_training_run, list_training_runs
from app.registry.artifact_store import register_model_package
from app.runtime import run_scheduler_iteration, run_worker_iteration


def _json_print(payload: Any) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


@contextmanager
def session_scope():
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

def _write_env_value(env_file: Path, key: str, value: str) -> None:
    lines: list[str] = []
    if env_file.exists():
        lines = env_file.read_text(encoding="utf-8").splitlines()
    updated = False
    rendered = f"{key}={value}"
    for index, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[index] = rendered
            updated = True
            break
    if not updated:
        lines.append(rendered)
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def cmd_health(args: argparse.Namespace) -> int:
    settings = get_settings()
    payload = {
        "status": "ok",
        "environment": settings.llmproxy_env,
        "database_backend": settings.database_backend,
        "redis_configured": bool(settings.llmproxy_redis_url),
        "provider_families_configured": settings_payload(settings)["provider_configuration"],
    }
    with get_engine().connect() as connection:
        connection.execute(text("select 1"))
    _json_print(payload)
    return 0


def _message_specs_to_messages(message_specs: list[str]) -> list[ChatMessage]:
    messages: list[ChatMessage] = []
    for spec in message_specs:
        if ":" not in spec:
            raise ValueError("Messages must use the format 'role:content'.")
        role, content = spec.split(":", 1)
        role = role.strip()
        content = content.strip()
        if not role or not content:
            raise ValueError("Messages must use the format 'role:content' with both values populated.")
        messages.append(ChatMessage(role=role, content=content))
    return messages


def _chat_request_from_args(args: argparse.Namespace) -> ChatCompletionRequest:
    return ChatCompletionRequest(
        model=args.model,
        messages=_message_specs_to_messages(args.message),
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        metadata=RequestMetadata(
            session_id=args.session_id,
            domain_hint=args.domain_hint,
            task_type_hint=args.task_type_hint,
        ),
    )


def cmd_config_show(args: argparse.Namespace) -> int:
    _json_print(settings_payload(get_settings()))
    return 0


def cmd_config_validate(args: argparse.Namespace) -> int:
    settings = get_settings()
    with get_engine().connect() as connection:
        connection.execute(text("select 1"))
    payload = {
        "database_connection": "ok",
        "reports_path_exists": Path(settings.llmproxy_reports_path).exists(),
        "models_path_exists": Path(settings.llmproxy_models_path).exists(),
        "provider_configuration": settings_payload(settings)["provider_configuration"],
    }
    _json_print(payload)
    return 0


def cmd_config_set(args: argparse.Namespace) -> int:
    env_file = Path(args.env_file)
    _write_env_value(env_file, args.key, args.value)
    _json_print({"updated": True, "env_file": str(env_file), "key": args.key, "value": args.value})
    return 0


def cmd_proxy_chat(args: argparse.Namespace) -> int:
    settings = get_settings()
    request = _chat_request_from_args(args)
    with session_scope() as session:
        response = asyncio.run(chat_completions(request=request, session=session, settings=settings))
    _json_print(response.model_dump(mode="json"))
    return 0


def cmd_proxy_ensemble(args: argparse.Namespace) -> int:
    settings = get_settings()
    request = _chat_request_from_args(args)
    with session_scope() as session:
        response = asyncio.run(ensemble_chat(request=request, session=session, settings=settings))
    _json_print(response.model_dump(mode="json"))
    return 0


def cmd_proxy_embeddings(args: argparse.Namespace) -> int:
    request = EmbeddingRequest(model=args.model, input=args.input)
    from app.api.openai_compatible import embeddings
    response = asyncio.run(embeddings(request=request))
    _json_print(response.model_dump(mode="json"))
    return 0


def cmd_proxy_requests_list(args: argparse.Namespace) -> int:
    with session_scope() as session:
        statement = select(RequestLog).order_by(RequestLog.created_at.desc())
        if args.session_id:
            statement = statement.where(RequestLog.session_id == args.session_id)
        if args.domain:
            statement = statement.where(RequestLog.domain == args.domain)
        if args.task_type:
            statement = statement.where(RequestLog.task_type == args.task_type)
        statement = statement.limit(args.limit)
        requests = list(session.execute(statement).scalars())
        payload = [request_summary_payload(request) for request in requests]
    _json_print(payload)
    return 0


def cmd_proxy_requests_show(args: argparse.Namespace) -> int:
    with session_scope() as session:
        request = session.get(RequestLog, args.request_id)
        if request is None:
            raise ValueError(f"Request '{args.request_id}' not found.")
        routing_decisions = list(
            session.execute(
                select(RoutingDecisionRecord).where(RoutingDecisionRecord.request_log_id == request.id)
            ).scalars()
        )
        model_responses = list(
            session.execute(
                select(ModelResponse).where(ModelResponse.request_log_id == request.id).order_by(ModelResponse.created_at.asc())
            ).scalars()
        )
        judge_critiques = list(
            session.execute(
                select(JudgeCritique).where(JudgeCritique.request_log_id == request.id)
            ).scalars()
        )
        candidates = list(
            session.execute(
                select(TrainingCandidate).where(TrainingCandidate.request_log_id == request.id)
            ).scalars()
        )
        samples = list(
            session.execute(
                select(ModelPerformanceSample).where(ModelPerformanceSample.request_log_id == request.id)
            ).scalars()
        )
        payload = request_detail_payload(
            request=request,
            routing_decisions=routing_decisions,
            model_responses=model_responses,
            judge_critiques=judge_critiques,
            candidates=candidates,
            performance_samples=samples,
        )
    _json_print(payload)
    return 0


def cmd_models_list(args: argparse.Namespace) -> int:
    settings = get_settings()
    with session_scope() as session:
        payload = list_proxy_models(settings, session=session) if args.proxy else [
            capability.model_dump(mode="json")
            for capability in list_provider_capabilities(settings, session=session)
        ]
    _json_print(payload)
    return 0


def cmd_models_local(args: argparse.Namespace) -> int:
    settings = get_settings()
    payload = list_model_packages(Path(settings.llmproxy_models_path))
    _json_print(payload)
    return 0


def cmd_models_register(args: argparse.Namespace) -> int:
    settings = get_settings()
    request = ModelRegistrationRequest(
        model_registry_id=args.model_registry_id,
        model_alias=args.model_alias,
        base_model=args.base_model,
        adapter_type=args.adapter_type,
        adapter_path=args.adapter_path,
        runtime=args.runtime,
        endpoint_url=args.endpoint_url,
        domains=args.domains,
        task_types=args.task_types,
        quality={"promotion_status": args.status},
        status=args.status,
    )
    manifest, manifest_path = register_model_package(Path(settings.llmproxy_models_path), request.model_dump(mode="json"))
    _json_print({"manifest_path": manifest_path, "manifest": manifest})
    return 0


def cmd_deploy_activate(args: argparse.Namespace) -> int:
    settings = get_settings()
    request = DeploymentRequest(
        deployment_mode=args.deployment_mode,
        domains=args.domains or None,
        task_types=args.task_types or None,
        canary_percent=args.canary_percent,
    )
    with session_scope() as session:
        response = deploy_model(session, model_alias=args.model_alias, request=request, settings=settings)
    _json_print(response.model_dump(mode="json"))
    return 0


def cmd_deploy_rollback(args: argparse.Namespace) -> int:
    settings = get_settings()
    with session_scope() as session:
        response = rollback_model(session, model_alias=args.model_alias, settings=settings)
    _json_print(response.model_dump(mode="json"))
    return 0


def cmd_deploy_policies(args: argparse.Namespace) -> int:
    with session_scope() as session:
        payload = [policy.policy_json | {"policy_version": policy.policy_version, "id": policy.id} for policy in list_routing_policies(session)]
    _json_print(payload)
    return 0


def cmd_candidates_list(args: argparse.Namespace) -> int:
    with session_scope() as session:
        candidates = list_training_candidates(session)
        payload = [
            {
                "id": candidate.id,
                "domain": candidate.domain,
                "task_type": candidate.task_type,
                "status": candidate.status,
                "approval_status": candidate.approval_status,
                "quality_score": candidate.quality_score,
                "export_eligible": candidate.export_eligible,
            }
            for candidate in candidates
        ]
    _json_print(payload)
    return 0


def _candidate_update(candidate_id: str, updater: Callable) -> dict[str, Any]:
    with session_scope() as session:
        candidate = get_training_candidate(session, candidate_id)
        if candidate is None:
            raise ValueError(f"Candidate '{candidate_id}' not found.")
        updater(session, candidate)
        return {
            "id": candidate.id,
            "status": candidate.status,
            "approval_status": candidate.approval_status,
            "export_eligible": candidate.export_eligible,
        }


def cmd_candidates_approve(args: argparse.Namespace) -> int:
    _json_print(_candidate_update(args.candidate_id, approve_training_candidate))
    return 0


def cmd_candidates_reject(args: argparse.Namespace) -> int:
    _json_print(_candidate_update(args.candidate_id, reject_training_candidate))
    return 0


def cmd_exports_run(args: argparse.Namespace) -> int:
    settings = get_settings()
    request = DatasetExportRequest(domain=args.domain, name=args.name, min_quality_score=args.min_quality_score)
    with session_scope() as session:
        response = export_candidates(session, request=request, settings=settings)
    _json_print(response.model_dump(mode="json"))
    return 0


def cmd_exports_list(args: argparse.Namespace) -> int:
    with session_scope() as session:
        statement = select(DatasetExport).order_by(DatasetExport.created_at.desc()).limit(args.limit)
        if args.domain:
            statement = statement.where(DatasetExport.domain == args.domain)
        exports = list(session.execute(statement).scalars())
        payload = [dataset_export_payload(item) for item in exports]
    _json_print(payload)
    return 0


def cmd_datasets_import(args: argparse.Namespace) -> int:
    settings = get_settings()
    request = DatasetImportRequest(
        dataset_export_id=args.dataset_export_id,
        manifest_path=args.manifest_path,
        data_path=args.data_path,
    )
    with session_scope() as session:
        response = import_dataset(session, request=request, settings=settings)
    _json_print(response.model_dump(mode="json"))
    return 0


def cmd_datasets_imports(args: argparse.Namespace) -> int:
    with session_scope() as session:
        imports = list(session.execute(select(DatasetImport).order_by(DatasetImport.created_at.desc()).limit(args.limit)).scalars())
        payload = [dataset_import_payload(item) for item in imports]
    _json_print(payload)
    return 0


def cmd_datasets_versions(args: argparse.Namespace) -> int:
    with session_scope() as session:
        statement = select(DatasetVersion).order_by(DatasetVersion.created_at.desc()).limit(args.limit)
        if args.domain:
            statement = statement.where(DatasetVersion.domain == args.domain)
        versions = list(session.execute(statement).scalars())
        payload = [dataset_version_payload(item) for item in versions]
    _json_print(payload)
    return 0


def cmd_training_run(args: argparse.Namespace) -> int:
    settings = get_settings()
    request = TrainingRunRequest(
        dataset_version_id=args.dataset_version_id,
        base_model=args.base_model,
        training_mode=args.training_mode,
        trainer_backend=args.trainer_backend,
        epochs=args.epochs,
        learning_rate=args.learning_rate,
        adapter_name=args.adapter_name,
    )
    with session_scope() as session:
        response = create_training_run(session, request=request, settings=settings)
    _json_print(response.model_dump(mode="json"))
    return 0


def cmd_training_list(args: argparse.Namespace) -> int:
    with session_scope() as session:
        runs = list_training_runs(session)
        payload = [
            {
                "id": run.id,
                "dataset_version_id": run.dataset_version_id,
                "base_model": run.base_model,
                "training_mode": run.training_mode,
                "trainer_backend": str(run.training_config_json.get("trainer_backend", "custom")),
                "status": run.status,
                "artifact_path": run.artifact_path,
            }
            for run in runs
        ]
    _json_print(payload)
    return 0


def cmd_training_show(args: argparse.Namespace) -> int:
    with session_scope() as session:
        run = session.get(TrainingRun, args.training_run_id)
        if run is None:
            raise ValueError(f"Training run '{args.training_run_id}' not found.")
        _json_print(training_run_payload(run))
    return 0


def cmd_evaluation_run(args: argparse.Namespace) -> int:
    settings = get_settings()
    request = EvaluationRunRequest(
        training_run_id=args.training_run_id,
        frontier_baseline_name=args.frontier_baseline_name,
    )
    with session_scope() as session:
        response = create_evaluation_run(session, request=request, settings=settings)
    _json_print(response.model_dump(mode="json"))
    return 0


def cmd_evaluation_list(args: argparse.Namespace) -> int:
    with session_scope() as session:
        runs = list_evaluation_runs(session)
        payload = [
            {
                "id": run.id,
                "training_run_id": run.training_run_id,
                "domain": run.domain,
                "frontier_baseline_name": run.frontier_baseline_name,
                "status": run.status,
                "overall_score": run.overall_score,
                "promotion_status": run.promotion_status,
            }
            for run in runs
        ]
    _json_print(payload)
    return 0


def cmd_evaluation_show(args: argparse.Namespace) -> int:
    with session_scope() as session:
        run = session.get(EvaluationRun, args.evaluation_run_id)
        if run is None:
            raise ValueError(f"Evaluation run '{args.evaluation_run_id}' not found.")
        _json_print(evaluation_run_payload(run))
    return 0


def cmd_kpis_show(args: argparse.Namespace) -> int:
    settings = get_settings()
    with session_scope() as session:
        report = generate_kpi_report(session, settings=settings)
    _json_print(report.model_dump(mode="json"))
    return 0


def cmd_jobs_list(args: argparse.Namespace) -> int:
    with session_scope() as session:
        jobs = list(session.execute(select(JobQueueRecord).order_by(JobQueueRecord.created_at.desc())).scalars())
        payload = [job_payload(job) for job in jobs]
    _json_print(payload)
    return 0


def cmd_jobs_show(args: argparse.Namespace) -> int:
    with session_scope() as session:
        job = session.get(JobQueueRecord, args.job_id)
        if job is None:
            raise ValueError(f"Job '{args.job_id}' not found.")
        _json_print(job_payload(job))
    return 0


def cmd_jobs_retry(args: argparse.Namespace) -> int:
    with session_scope() as session:
        job = session.get(JobQueueRecord, args.job_id)
        if job is None:
            raise ValueError(f"Job '{args.job_id}' not found.")
        job.status = "pending"
        job.claimed_at = None
        job.completed_at = None
        job.last_error = None
        if args.reset_attempts:
            job.attempts = 0
        if args.available_now:
            job.available_at = datetime.now(timezone.utc)
        _json_print({"retried": True, "job_id": job.id, "status": job.status, "attempts": job.attempts})
    return 0


def cmd_jobs_cancel(args: argparse.Namespace) -> int:
    with session_scope() as session:
        job = session.get(JobQueueRecord, args.job_id)
        if job is None:
            raise ValueError(f"Job '{args.job_id}' not found.")
        job.status = "cancelled"
        job.completed_at = datetime.now(timezone.utc)
        _json_print({"cancelled": True, "job_id": job.id, "status": job.status})
    return 0


def cmd_jobs_run_once(args: argparse.Namespace) -> int:
    processed = run_worker_iteration()
    _json_print({"processed": processed})
    return 0


def cmd_events_list(args: argparse.Namespace) -> int:
    with session_scope() as session:
        statement = select(IntegrationEvent).order_by(IntegrationEvent.occurred_at.desc()).limit(args.limit)
        if args.event_type:
            statement = statement.where(IntegrationEvent.event_type == args.event_type)
        if args.unprocessed:
            statement = statement.where(IntegrationEvent.processed_at.is_(None))
        events = list(session.execute(statement).scalars())
        payload = [event_payload(event) | {"payload_json": event.payload_json if args.verbose else None} for event in events]
    _json_print(payload)
    return 0


def cmd_events_show(args: argparse.Namespace) -> int:
    with session_scope() as session:
        event = session.get(IntegrationEvent, args.event_id)
        if event is None:
            raise ValueError(f"Event '{args.event_id}' not found.")
        _json_print(event_payload(event))
    return 0


def cmd_events_process(args: argparse.Namespace) -> int:
    settings = get_settings()
    with session_scope() as session:
        response = process_pending_events(session, settings=settings)
    _json_print(response.model_dump(mode="json"))
    return 0


def cmd_events_replay(args: argparse.Namespace) -> int:
    settings = get_settings()
    with session_scope() as session:
        event = session.get(IntegrationEvent, args.event_id)
        if event is None:
            raise ValueError(f"Event '{args.event_id}' not found.")
        event.processed_at = None
        session.flush()
        response = process_pending_events(session, settings=settings)
        _json_print(
            {
                "replayed": True,
                "event_id": event.id,
                "event_type": event.event_type,
                "processed_count": response.processed_count,
                "imported_count": response.imported_count,
            }
        )
    return 0


def cmd_scheduler_run_once(args: argparse.Namespace) -> int:
    run_scheduler_iteration()
    _json_print({"scheduled": True})
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="llmproxy-admin", description="Operate and inspect llmProxy.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    health = subparsers.add_parser("health")
    health.set_defaults(func=cmd_health)

    config = subparsers.add_parser("config")
    config_sub = config.add_subparsers(dest="config_command", required=True)
    config_show = config_sub.add_parser("show")
    config_show.set_defaults(func=cmd_config_show)
    config_validate = config_sub.add_parser("validate")
    config_validate.set_defaults(func=cmd_config_validate)
    config_set = config_sub.add_parser("set")
    config_set.add_argument("key")
    config_set.add_argument("value")
    config_set.add_argument("--env-file", default=".env")
    config_set.set_defaults(func=cmd_config_set)

    proxy = subparsers.add_parser("proxy")
    proxy_sub = proxy.add_subparsers(dest="proxy_command", required=True)
    proxy_chat = proxy_sub.add_parser("chat")
    proxy_chat.add_argument("--model", default="proxy-auto")
    proxy_chat.add_argument("--message", action="append", required=True, help="Message in role:content format. Repeat per message.")
    proxy_chat.add_argument("--session-id", required=True)
    proxy_chat.add_argument("--domain-hint")
    proxy_chat.add_argument("--task-type-hint")
    proxy_chat.add_argument("--temperature", type=float, default=0.2)
    proxy_chat.add_argument("--max-tokens", type=int, default=1024)
    proxy_chat.set_defaults(func=cmd_proxy_chat)
    proxy_ensemble = proxy_sub.add_parser("ensemble")
    proxy_ensemble.add_argument("--model", default="proxy-ensemble")
    proxy_ensemble.add_argument("--message", action="append", required=True, help="Message in role:content format. Repeat per message.")
    proxy_ensemble.add_argument("--session-id", required=True)
    proxy_ensemble.add_argument("--domain-hint")
    proxy_ensemble.add_argument("--task-type-hint")
    proxy_ensemble.add_argument("--temperature", type=float, default=0.2)
    proxy_ensemble.add_argument("--max-tokens", type=int, default=1024)
    proxy_ensemble.set_defaults(func=cmd_proxy_ensemble)
    proxy_embeddings = proxy_sub.add_parser("embeddings")
    proxy_embeddings.add_argument("model")
    proxy_embeddings.add_argument("input", nargs="+")
    proxy_embeddings.set_defaults(func=cmd_proxy_embeddings)
    proxy_requests = proxy_sub.add_parser("requests")
    proxy_requests_sub = proxy_requests.add_subparsers(dest="proxy_requests_command", required=True)
    proxy_requests_list = proxy_requests_sub.add_parser("list")
    proxy_requests_list.add_argument("--limit", type=int, default=20)
    proxy_requests_list.add_argument("--session-id")
    proxy_requests_list.add_argument("--domain")
    proxy_requests_list.add_argument("--task-type")
    proxy_requests_list.set_defaults(func=cmd_proxy_requests_list)
    proxy_requests_show = proxy_requests_sub.add_parser("show")
    proxy_requests_show.add_argument("request_id")
    proxy_requests_show.set_defaults(func=cmd_proxy_requests_show)

    models = subparsers.add_parser("models")
    models_sub = models.add_subparsers(dest="models_command", required=True)
    models_list = models_sub.add_parser("list")
    models_list.add_argument("--proxy", action="store_true")
    models_list.set_defaults(func=cmd_models_list)
    models_local = models_sub.add_parser("local")
    models_local.set_defaults(func=cmd_models_local)
    models_register = models_sub.add_parser("register")
    models_register.add_argument("model_registry_id")
    models_register.add_argument("model_alias")
    models_register.add_argument("base_model")
    models_register.add_argument("adapter_type")
    models_register.add_argument("adapter_path")
    models_register.add_argument("runtime")
    models_register.add_argument("endpoint_url")
    models_register.add_argument("--domain", dest="domains", action="append", required=True)
    models_register.add_argument("--task-type", dest="task_types", action="append", required=True)
    models_register.add_argument("--status", default="approved")
    models_register.set_defaults(func=cmd_models_register)

    deploy = subparsers.add_parser("deploy")
    deploy_sub = deploy.add_subparsers(dest="deploy_command", required=True)
    deploy_activate = deploy_sub.add_parser("activate")
    deploy_activate.add_argument("model_alias")
    deploy_activate.add_argument("deployment_mode", choices=["shadow", "canary", "production"])
    deploy_activate.add_argument("--domain", dest="domains", action="append")
    deploy_activate.add_argument("--task-type", dest="task_types", action="append")
    deploy_activate.add_argument("--canary-percent", type=float, default=0.0)
    deploy_activate.set_defaults(func=cmd_deploy_activate)
    deploy_rollback = deploy_sub.add_parser("rollback")
    deploy_rollback.add_argument("model_alias")
    deploy_rollback.set_defaults(func=cmd_deploy_rollback)
    deploy_policies = deploy_sub.add_parser("policies")
    deploy_policies.set_defaults(func=cmd_deploy_policies)

    candidates = subparsers.add_parser("candidates")
    candidates_sub = candidates.add_subparsers(dest="candidates_command", required=True)
    candidates_list = candidates_sub.add_parser("list")
    candidates_list.set_defaults(func=cmd_candidates_list)
    candidates_approve = candidates_sub.add_parser("approve")
    candidates_approve.add_argument("candidate_id")
    candidates_approve.set_defaults(func=cmd_candidates_approve)
    candidates_reject = candidates_sub.add_parser("reject")
    candidates_reject.add_argument("candidate_id")
    candidates_reject.set_defaults(func=cmd_candidates_reject)

    exports = subparsers.add_parser("exports")
    exports_sub = exports.add_subparsers(dest="exports_command", required=True)
    exports_run = exports_sub.add_parser("run")
    exports_run.add_argument("domain")
    exports_run.add_argument("--name")
    exports_run.add_argument("--min-quality-score", type=float, default=0.0)
    exports_run.set_defaults(func=cmd_exports_run)
    exports_list = exports_sub.add_parser("list")
    exports_list.add_argument("--limit", type=int, default=20)
    exports_list.add_argument("--domain")
    exports_list.set_defaults(func=cmd_exports_list)

    datasets = subparsers.add_parser("datasets")
    datasets_sub = datasets.add_subparsers(dest="datasets_command", required=True)
    datasets_import = datasets_sub.add_parser("import")
    datasets_import.add_argument("dataset_export_id")
    datasets_import.add_argument("manifest_path")
    datasets_import.add_argument("data_path")
    datasets_import.set_defaults(func=cmd_datasets_import)
    datasets_imports = datasets_sub.add_parser("imports")
    datasets_imports.add_argument("--limit", type=int, default=20)
    datasets_imports.set_defaults(func=cmd_datasets_imports)
    datasets_versions = datasets_sub.add_parser("versions")
    datasets_versions.add_argument("--limit", type=int, default=20)
    datasets_versions.add_argument("--domain")
    datasets_versions.set_defaults(func=cmd_datasets_versions)

    training = subparsers.add_parser("training")
    training_sub = training.add_subparsers(dest="training_command", required=True)
    training_run = training_sub.add_parser("run")
    training_run.add_argument("dataset_version_id")
    training_run.add_argument("base_model")
    training_run.add_argument("training_mode", choices=["lora", "qlora"])
    training_run.add_argument("--trainer-backend", choices=["custom", "unsloth"], default="custom")
    training_run.add_argument("--epochs", type=int, default=3)
    training_run.add_argument("--learning-rate", type=float, default=0.0002)
    training_run.add_argument("--adapter-name")
    training_run.set_defaults(func=cmd_training_run)
    training_list = training_sub.add_parser("list")
    training_list.set_defaults(func=cmd_training_list)
    training_show = training_sub.add_parser("show")
    training_show.add_argument("training_run_id")
    training_show.set_defaults(func=cmd_training_show)

    evaluation = subparsers.add_parser("evaluation")
    evaluation_sub = evaluation.add_subparsers(dest="evaluation_command", required=True)
    evaluation_run = evaluation_sub.add_parser("run")
    evaluation_run.add_argument("training_run_id")
    evaluation_run.add_argument("--frontier-baseline-name")
    evaluation_run.set_defaults(func=cmd_evaluation_run)
    evaluation_list = evaluation_sub.add_parser("list")
    evaluation_list.set_defaults(func=cmd_evaluation_list)
    evaluation_show = evaluation_sub.add_parser("show")
    evaluation_show.add_argument("evaluation_run_id")
    evaluation_show.set_defaults(func=cmd_evaluation_show)

    kpis = subparsers.add_parser("kpis")
    kpis_sub = kpis.add_subparsers(dest="kpis_command", required=True)
    kpis_show = kpis_sub.add_parser("show")
    kpis_show.set_defaults(func=cmd_kpis_show)

    jobs = subparsers.add_parser("jobs")
    jobs_sub = jobs.add_subparsers(dest="jobs_command", required=True)
    jobs_list = jobs_sub.add_parser("list")
    jobs_list.set_defaults(func=cmd_jobs_list)
    jobs_show = jobs_sub.add_parser("show")
    jobs_show.add_argument("job_id")
    jobs_show.set_defaults(func=cmd_jobs_show)
    jobs_retry = jobs_sub.add_parser("retry")
    jobs_retry.add_argument("job_id")
    jobs_retry.add_argument("--reset-attempts", action="store_true")
    jobs_retry.add_argument("--available-now", action="store_true")
    jobs_retry.set_defaults(func=cmd_jobs_retry)
    jobs_cancel = jobs_sub.add_parser("cancel")
    jobs_cancel.add_argument("job_id")
    jobs_cancel.set_defaults(func=cmd_jobs_cancel)
    jobs_run_once = jobs_sub.add_parser("run-once")
    jobs_run_once.set_defaults(func=cmd_jobs_run_once)

    events = subparsers.add_parser("events")
    events_sub = events.add_subparsers(dest="events_command", required=True)
    events_list = events_sub.add_parser("list")
    events_list.add_argument("--limit", type=int, default=20)
    events_list.add_argument("--event-type")
    events_list.add_argument("--unprocessed", action="store_true")
    events_list.add_argument("--verbose", action="store_true")
    events_list.set_defaults(func=cmd_events_list)
    events_show = events_sub.add_parser("show")
    events_show.add_argument("event_id")
    events_show.set_defaults(func=cmd_events_show)
    events_process = events_sub.add_parser("process")
    events_process.set_defaults(func=cmd_events_process)
    events_replay = events_sub.add_parser("replay")
    events_replay.add_argument("event_id")
    events_replay.set_defaults(func=cmd_events_replay)

    scheduler = subparsers.add_parser("scheduler")
    scheduler_sub = scheduler.add_subparsers(dest="scheduler_command", required=True)
    scheduler_run_once = scheduler_sub.add_parser("run-once")
    scheduler_run_once.set_defaults(func=cmd_scheduler_run_once)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
