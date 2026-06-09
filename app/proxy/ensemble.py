"""Teacher ensemble execution."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from time import perf_counter

from app.config import Settings
from app.proxy.candidates import capture_training_candidate
from app.proxy.judge import judge_response
from app.proxy.recorder import record_judge_critique, record_model_response
from app.services.interaction_traces import summarize_interaction_trace_protocols
from app.registry.model_registry import get_provider_registry
from app.services.cost import estimate_cost_usd
from app.services.observability import log_record
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

    async def _teacher_result(provider_key: str) -> dict[str, object]:
        provider = provider_registry[provider_key]
        if request.stream and getattr(provider, "supports_streaming", False):
            aggregated_content = ""
            prompt_tokens = 0
            completion_tokens = 0
            finish_reason = "stop"
            chunk_count = 0
            started_at = perf_counter()
            log_record(
                settings,
                level="INFO",
                component="proxy.ensemble",
                category="stream",
                message="Teacher stream started",
                data={"request_id": request_log_id, "provider": provider_key, "model": provider.model_id},
            )
            async for chunk in provider.stream_chat(request):
                chunk_count += 1
                aggregated_content += str(chunk.get("delta", ""))
                prompt_tokens = max(prompt_tokens, int(chunk.get("input_tokens", 0)))
                completion_tokens = max(completion_tokens, int(chunk.get("output_tokens", 0)))
                if chunk.get("finish_reason"):
                    finish_reason = str(chunk["finish_reason"])
            result = {
                "model": provider.model_id,
                "content": aggregated_content,
                "input_tokens": prompt_tokens,
                "output_tokens": completion_tokens or len(aggregated_content.split()),
                "latency_ms": int((perf_counter() - started_at) * 1000),
                "finish_reason": finish_reason,
                "cost_estimate": estimate_cost_usd(
                    provider_name=provider.provider_name,
                    model_id=provider.model_id,
                    input_tokens=prompt_tokens,
                    output_tokens=completion_tokens or len(aggregated_content.split()),
                ),
                "raw_response": {"streamed": True, "chunk_count": chunk_count, "ensemble": True},
                "provider": provider.provider_name,
                "provider_family": provider.provider_family,
            }
            log_record(
                settings,
                level="INFO",
                component="proxy.ensemble",
                category="stream",
                message="Teacher stream completed",
                data={"request_id": request_log_id, "provider": provider_key, "model": provider.model_id, "chunk_count": chunk_count},
            )
            return result
        return await provider.invoke(request)

    gathered_results = await asyncio.gather(*(_teacher_result(key) for key in teacher_keys), return_exceptions=True)
    results: list[dict[str, object]] = []
    for provider_key, result in zip(teacher_keys, gathered_results, strict=False):
        if isinstance(result, BaseException):
            log_record(
                settings,
                level="ERROR",
                component="proxy.ensemble",
                category="error",
                message="Teacher request failed",
                data={"request_id": request_log_id, "provider": provider_key, "error": str(result)},
            )
            continue
        results.append(result)

    if not results:
        raise RuntimeError("All teacher models failed.")

    teacher_candidates: list[TeacherCandidate] = []

    def _persist_candidates(sync_session):
        candidates: list[TeacherCandidate] = []
        for rank, result in enumerate(results, start=1):
            response_record = record_model_response(
                sync_session,
                request_log_id,
                result,
                response_role="teacher_candidate",
            )
            candidates.append(
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
        return candidates

    teacher_candidates = await session.run_sync(_persist_candidates)

    critique = judge_response(teacher_candidates, domain=request.metadata.domain_hint or "general")
    winning_candidate = next(
        (item for item in teacher_candidates if item.response_id == critique.selected_response_id),
        None,
    )
    if winning_candidate is None:
        raise RuntimeError("Judge selected a response ID that does not match any teacher candidate.")

    def _persist_judge(sync_session):
        interaction_traces = [
            {
                "trace_id": f"trace_llm_{candidate.response_id}",
                "protocol": "llm",
                "operation": "chat_completion",
                "source": "llmproxy",
                "request_id": request_log_id,
                "response_id": candidate.response_id,
                "session_id": request.metadata.session_id,
                "success": True,
                "provider": candidate.provider,
                "provider_family": candidate.provider_family,
                "model": candidate.model,
                "response_role": "teacher_candidate",
                "request_payload": {
                    "requested_model": request.model,
                    "messages": [message.model_dump(mode="json") for message in request.messages],
                    "metadata": request.metadata.model_dump(mode="json"),
                },
                "response_payload": {
                    "content": candidate.content,
                    "finish_reason": "stop",
                },
                "metrics": {},
            }
            for candidate in teacher_candidates
        ]
        interaction_traces.append(
            {
                "trace_id": f"trace_llm_judge_{request_log_id}",
                "protocol": "llm",
                "operation": "selection_judge",
                "source": "llmproxy",
                "request_id": request_log_id,
                "response_id": critique.selected_response_id,
                "session_id": request.metadata.session_id,
                "success": True,
                "provider": critique.judge_provider,
                "provider_family": critique.judge_provider,
                "model": critique.judge_model,
                "response_role": "judge",
                "request_payload": {
                    "candidate_ids": [candidate.response_id for candidate in teacher_candidates],
                    "domain": request.metadata.domain_hint or "general",
                },
                "response_payload": {
                    "selected_response_id": critique.selected_response_id,
                    "selected_provider": critique.selected_provider,
                    "selected_model": critique.selected_model,
                    "scores": critique.scores,
                    "rationale": critique.rationale,
                },
                "metrics": {},
            }
        )
        record_judge_critique(
            sync_session,
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
            sync_session,
            request_log_id=request_log_id,
            routing_decision_id=routing_decision_id,
            session_id=request.metadata.session_id,
            domain=request.metadata.domain_hint or "general",
            task_type=request.metadata.task_type_hint or "question_answer",
            quality_score=max(critique.scores.values(), default=None),
            selected_response=winning_candidate.content,
            messages=[message.model_dump(mode="json") for message in request.messages],
            provenance={
                "request_id": request_log_id,
                "source": "teacher_ensemble",
                "teacher_models": [candidate.model for candidate in teacher_candidates],
                "judge_model": critique.judge_model,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "interaction_traces": interaction_traces,
                "interaction_protocols": summarize_interaction_trace_protocols(interaction_traces),
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

    await session.run_sync(_persist_judge)

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
