"""Teacher ensemble execution."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.config import Settings
from app.proxy.candidates import capture_training_candidate
from app.proxy.judge import judge_response
from app.proxy.recorder import record_judge_critique, record_model_response
from app.registry.model_registry import get_provider_registry
from app.schemas.chat import ChatCompletionRequest, ChatCompletionResponse
from app.schemas.ensemble import EnsembleResponse, TeacherCandidate
from app.schemas.routing import FallbackTarget, RankedAlternative


async def run_teacher_ensemble(
    *,
    request: ChatCompletionRequest,
    request_log_id: str,
    routing_decision_id: str,
    session,
    settings: Settings,
) -> EnsembleResponse:
    provider_registry = get_provider_registry(settings)
    teacher_keys = ["anthropic", "openai", "google"]
    results = await asyncio.gather(
        *(provider_registry[key].invoke(request) for key in teacher_keys)
    )

    teacher_candidates: list[TeacherCandidate] = []
    response_records = []
    for rank, result in enumerate(results, start=1):
        response_record = record_model_response(
            session,
            request_log_id,
            result,
            response_role="teacher_candidate",
        )
        response_records.append(response_record)
        teacher_candidates.append(
            TeacherCandidate(
                response_id=response_record.id,
                provider=str(result["provider"]),
                provider_family=str(result["provider_family"]),
                model=str(result["model"]),
                content=str(result["content"]),
                score=round(1.0 - (rank * 0.03), 4),
                rationale=f"Teacher candidate from {result['provider']} ranked at ensemble position {rank}.",
            )
        )

    critique = judge_response(teacher_candidates, domain=request.metadata.domain_hint or "general")
    winning_candidate = next(item for item in teacher_candidates if item.response_id == critique.selected_response_id)
    record_judge_critique(
        session,
        request_log_id=request_log_id,
        routing_decision_id=routing_decision_id,
        judge_provider=critique.judge_provider,
        judge_model=critique.judge_model,
        selected_provider=critique.selected_provider,
        selected_model=critique.selected_model,
        selected_response_id=critique.selected_response_id,
        critique_json=critique.model_dump(mode="json"),
        synthesized_response=winning_candidate.content,
    )
    capture_training_candidate(
        session,
        request_log_id=request_log_id,
        routing_decision_id=routing_decision_id,
        session_id=request.metadata.session_id,
        domain=request.metadata.domain_hint or "general",
        task_type=request.metadata.task_type_hint or "question_answer",
        quality_score=max(critique.scores.values()),
        selected_response=winning_candidate.content,
        messages=[message.model_dump(mode="json") for message in request.messages],
        provenance={
            "request_id": request_log_id,
            "source": "teacher_ensemble",
            "teacher_models": [candidate.model for candidate in teacher_candidates],
            "judge_model": critique.judge_model,
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
        validation={
            "validated": True,
            "validation_type": "judge_and_rules",
            "tests_passed": None,
            "static_checks_passed": None,
            "secrets_detected": False,
        },
        metadata={
            "selected_provider": critique.selected_provider,
            "selected_model": critique.selected_model,
            "selected_response_id": critique.selected_response_id,
            "candidate_count": len(teacher_candidates),
        },
    )

    chat_response = ChatCompletionResponse.from_request(
        request,
        content=winning_candidate.content,
        response_id=request_log_id.replace("req_", "chatcmpl_"),
        resolved_model="proxy-ensemble",
    )
    return EnsembleResponse(
        response=chat_response,
        teacher_candidates=teacher_candidates,
        judge_critique=critique,
    )
