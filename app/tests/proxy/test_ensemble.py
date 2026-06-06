import asyncio

from app.proxy.ensemble import run_teacher_ensemble
from app.proxy.judge import judge_response
from app.schemas.ensemble import JudgeCritiquePayload, TeacherCandidate
from app.schemas.chat import ChatCompletionRequest


def test_judge_selects_highest_scored_candidate() -> None:
    candidates = [
        TeacherCandidate(
            response_id="resp_openai",
            provider="openai",
            provider_family="OpenAI",
            model="gpt-4.1-mini",
            content="Short answer.",
            score=0.90,
            rationale="candidate 1",
        ),
        TeacherCandidate(
            response_id="resp_anthropic",
            provider="anthropic",
            provider_family="Anthropic",
            model="claude-3-5-sonnet",
            content="Longer architecture answer.",
            score=0.95,
            rationale="candidate 2",
        ),
    ]

    critique = judge_response(candidates, domain="software_architecture")

    assert critique.selected_response_id == "resp_anthropic"
    assert critique.selected_provider == "anthropic"
    assert "resp_anthropic" in critique.scores


class _FakeProvider:
    def __init__(self, *, provider_name: str, model_id: str, content: str | None = None, error: Exception | None = None) -> None:
        self.provider_name = provider_name
        self.provider_family = provider_name.upper()
        self.model_id = model_id
        self._content = content
        self._error = error

    async def invoke(self, request: ChatCompletionRequest) -> dict[str, object]:
        if self._error is not None:
            raise self._error
        return {
            "model": self.model_id,
            "content": self._content or "",
            "input_tokens": 5,
            "output_tokens": 3,
            "latency_ms": 10,
            "finish_reason": "stop",
            "cost_estimate": 0.01,
            "raw_response": {},
            "provider": self.provider_name,
            "provider_family": self.provider_family,
        }


class _FakeAsyncSession:
    def __init__(self) -> None:
        self.response_counter = 0
        self.captured_quality_score = "unset"

    async def run_sync(self, fn):
        return fn(self)


def _request() -> ChatCompletionRequest:
    return ChatCompletionRequest.model_validate(
        {
            "model": "proxy-ensemble",
            "messages": [{"role": "user", "content": "Compare architecture tradeoffs."}],
            "metadata": {"session_id": "sess_ensemble", "domain_hint": "software_architecture"},
        }
    )


def test_run_teacher_ensemble_tolerates_partial_teacher_failure(monkeypatch) -> None:
    registry = {
        "anthropic": _FakeProvider(provider_name="anthropic", model_id="claude-3-5-sonnet", content="Anthropic answer."),
        "openai": _FakeProvider(provider_name="openai", model_id="gpt-5.5", error=RuntimeError("OpenAI timeout")),
        "google": _FakeProvider(provider_name="google", model_id="gemini-2.5-pro", content="Google answer."),
    }
    session = _FakeAsyncSession()

    monkeypatch.setattr("app.proxy.ensemble.get_provider_registry", lambda settings: registry)
    monkeypatch.setattr("app.proxy.ensemble.record_model_response", _fake_record_model_response)
    monkeypatch.setattr("app.proxy.ensemble.record_judge_critique", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.proxy.ensemble.capture_training_candidate", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.proxy.ensemble.log_record", lambda *args, **kwargs: None)

    response = asyncio.run(
        run_teacher_ensemble(
            request=_request(),
            request_log_id="req_ensemble",
            routing_decision_id="route_ensemble",
            session=session,
            settings=type("Settings", (), {})(),
        )
    )

    assert response.response.choices[0].message.content in {"Anthropic answer.", "Google answer."}
    assert len(response.teacher_candidates) == 2
    assert {candidate.provider for candidate in response.teacher_candidates} == {"anthropic", "google"}


def test_run_teacher_ensemble_allows_empty_judge_scores(monkeypatch) -> None:
    registry = {
        "anthropic": _FakeProvider(provider_name="anthropic", model_id="claude-3-5-sonnet", content="Anthropic answer."),
        "openai": _FakeProvider(provider_name="openai", model_id="gpt-5.5", content="OpenAI answer."),
        "google": _FakeProvider(provider_name="google", model_id="gemini-2.5-pro", content="Google answer."),
    }
    session = _FakeAsyncSession()

    monkeypatch.setattr("app.proxy.ensemble.get_provider_registry", lambda settings: registry)
    monkeypatch.setattr("app.proxy.ensemble.record_model_response", _fake_record_model_response)
    monkeypatch.setattr("app.proxy.ensemble.record_judge_critique", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.proxy.ensemble.log_record", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "app.proxy.ensemble.judge_response",
        lambda candidates, domain: JudgeCritiquePayload(
            judge_provider="rule_based_judge",
            judge_model="heuristic-v1",
            selected_response_id=candidates[0].response_id,
            selected_provider=candidates[0].provider,
            selected_model=candidates[0].model,
            rationale="fallback",
            scores={},
        ),
    )
    monkeypatch.setattr(
        "app.proxy.ensemble.capture_training_candidate",
        lambda sync_session, **kwargs: setattr(sync_session, "captured_quality_score", kwargs["quality_score"]),
    )

    asyncio.run(
        run_teacher_ensemble(
            request=_request(),
            request_log_id="req_ensemble",
            routing_decision_id="route_ensemble",
            session=session,
            settings=type("Settings", (), {})(),
        )
    )

    assert session.captured_quality_score is None


def _fake_record_model_response(sync_session, request_log_id, result, response_role="teacher_candidate"):
    sync_session.response_counter += 1
    return type("ResponseRecord", (), {"id": f"resp_{sync_session.response_counter}"})()
