from datetime import datetime, timezone

from datetime import timedelta
from decimal import Decimal

from app.db.models import ModelResponse, PromptTemplate, RequestLog, TrainingCandidate
from app.services.prompt_templates import (
    build_prompt_template_metrics,
    compare_prompt_template_versions,
    evaluate_prompt_auto_promotion,
    PromptTemplateCreateInput,
    create_prompt_template,
    promote_prompt_template_challenger,
    render_prompt_template,
    resolve_runtime_prompt_template,
    set_prompt_auto_promotion_policy,
    set_prompt_template_rollout,
    set_prompt_template_status,
)


class FakeScalarOneResult:
    def __init__(self, value):
        self._value = value

    def scalar_one(self):
        return self._value


class FakeScalarList:
    def __init__(self, items):
        self._items = items

    def all(self):
        return list(self._items)

    def first(self):
        return self._items[0] if self._items else None

    def __iter__(self):
        return iter(self._items)


class FakeResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return FakeScalarList(self._items)


class FakePromptSession:
    def __init__(self, items=None, request_rows=None, response_rows=None, candidate_rows=None):
        self.items = list(items or [])
        self.request_rows = list(request_rows or [])
        self.response_rows = list(response_rows or [])
        self.candidate_rows = list(candidate_rows or [])

    def _filtered_templates(self, statement):
        rows = list(self.items)
        for criterion in getattr(statement, "_where_criteria", ()):
            key = getattr(getattr(criterion, "left", None), "key", None)
            value = getattr(getattr(criterion, "right", None), "value", None)
            operator_name = getattr(getattr(criterion, "operator", None), "__name__", "")
            if key == "name" and operator_name == "eq":
                rows = [row for row in rows if row.name == value]
            elif key == "version" and operator_name == "eq":
                rows = [row for row in rows if row.version == value]
            elif key == "version" and operator_name == "ne":
                rows = [row for row in rows if row.version != value]
            elif key == "status" and operator_name == "eq":
                rows = [row for row in rows if row.status == value]
        order_by = tuple(getattr(statement, "_order_by_clauses", ()) or ())
        if any("version" in str(clause).lower() and "desc" in str(clause).lower() for clause in order_by):
            rows.sort(key=lambda item: item.version, reverse=True)
        limit_clause = getattr(statement, "_limit_clause", None)
        if limit_clause is not None:
            rows = rows[: int(limit_clause.value)]
        return rows

    def execute(self, statement):
        text = str(statement).lower()
        if "coalesce(max" in text:
            matching = self._filtered_templates(statement)
            max_version = max((row.version for row in matching), default=0)
            return FakeScalarOneResult(max_version)
        entity = None
        if getattr(statement, "column_descriptions", None):
            entity = statement.column_descriptions[0].get("entity")
        if entity is PromptTemplate:
            return FakeResult(self._filtered_templates(statement))
        if entity is RequestLog:
            return FakeResult(self.request_rows)
        if entity is ModelResponse:
            rows = list(self.response_rows)
            if any("desc" in str(clause).lower() for clause in tuple(getattr(statement, "_order_by_clauses", ()) or ())):
                rows.sort(key=lambda item: item.created_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
            return FakeResult(rows)
        if entity is TrainingCandidate:
            return FakeResult(self.candidate_rows)
        return FakeResult([])

    def add(self, item):
        self.items.append(item)

    def commit(self):
        return None

    def refresh(self, item):
        if getattr(item, "created_at", None) is None:
            item.created_at = datetime.now(timezone.utc)


def test_create_prompt_template_defaults_first_version_active_then_draft() -> None:
    session = FakePromptSession()

    first = create_prompt_template(
        session,
        PromptTemplateCreateInput(
            name="architecture_review",
            template_text="Review {service_name}.",
            variables=["service_name"],
        ),
    )
    second = create_prompt_template(
        session,
        PromptTemplateCreateInput(
            name="architecture_review",
            template_text="Draft review for {service_name}.",
            variables=["service_name"],
        ),
    )

    assert first.version == 1
    assert first.status == "active"
    assert second.version == 2
    assert second.status == "draft"


def test_render_prompt_template_prefers_active_version_over_newer_draft() -> None:
    session = FakePromptSession(
        [
            PromptTemplate(
                id="prompttpl_1",
                name="architecture_review",
                version=1,
                template_text="ACTIVE {service_name}",
                variables_json=["service_name"],
                model_override=None,
                status="active",
                metadata_json={},
            ),
            PromptTemplate(
                id="prompttpl_2",
                name="architecture_review",
                version=2,
                template_text="DRAFT {service_name}",
                variables_json=["service_name"],
                model_override=None,
                status="draft",
                metadata_json={},
            ),
        ]
    )

    record, rendered = render_prompt_template(
        session,
        name="architecture_review",
        variables={"service_name": "billing"},
    )

    assert record.version == 1
    assert record.status == "active"
    assert rendered == "ACTIVE billing"


def test_set_prompt_template_status_promotes_and_deprecates_previous_active() -> None:
    first = PromptTemplate(
        id="prompttpl_1",
        name="architecture_review",
        version=1,
        template_text="ACTIVE {service_name}",
        variables_json=["service_name"],
        model_override=None,
        status="active",
        metadata_json={},
    )
    second = PromptTemplate(
        id="prompttpl_2",
        name="architecture_review",
        version=2,
        template_text="DRAFT {service_name}",
        variables_json=["service_name"],
        model_override=None,
        status="draft",
        metadata_json={},
    )
    session = FakePromptSession([first, second])

    record = set_prompt_template_status(
        session,
        name="architecture_review",
        version=2,
        status="active",
    )

    assert record.version == 2
    assert record.status == "active"
    assert first.status == "deprecated"


def test_build_prompt_template_metrics_uses_resolved_versions() -> None:
    created_at = datetime.now(timezone.utc)
    request = RequestLog(
        id="req_1",
        session_id="sess_1",
        external_request_id=None,
        requested_model="proxy-auto",
        domain="general",
        task_type="analysis",
        complexity="medium",
        privacy_level="standard",
        request_json={"metadata": {"prompt_template_name": "architecture_review", "prompt_template_variables": {"service_name": "billing"}}},
        effective_request_json={"metadata": {"prompt_template_name": "architecture_review", "prompt_template_version": 2}},
        created_at=created_at,
    )
    response = ModelResponse(
        id="resp_1",
        request_log_id="req_1",
        provider="openai",
        provider_family="OpenAI",
        model="gpt-5",
        latency_ms=420,
        input_tokens=100,
        output_tokens=50,
        cost_estimate=Decimal("0.012500"),
        finish_reason="stop",
        response_json={},
        response_role="selected_response",
        created_at=created_at + timedelta(seconds=1),
    )
    candidate = TrainingCandidate(
        id="cand_1",
        request_log_id="req_1",
        routing_decision_id="route_1",
        session_id="sess_1",
        domain="general",
        task_type="analysis",
        status="approved",
        quality_score=0.9,
        approval_status="approved",
        export_eligible=True,
        selected_response="answer",
        messages_json=[],
        provenance_json={},
        validation_json={},
        metadata_json={"prompt_template_name": "architecture_review", "prompt_template_version": 2},
        created_at=created_at + timedelta(seconds=2),
    )
    session = FakePromptSession(request_rows=[request], response_rows=[response], candidate_rows=[candidate])

    metrics = build_prompt_template_metrics(session)

    assert metrics[("architecture_review", 2)] == {
        "request_count": 1,
        "successful_request_count": 1,
        "error_count": 0,
        "candidate_count": 1,
        "approved_candidate_count": 1,
        "total_cost_estimate": 0.0125,
        "error_rate_pct": 0.0,
        "candidate_yield_rate_pct": 100.0,
        "approval_rate_pct": 100.0,
        "avg_latency_ms": 420.0,
        "avg_cost_estimate": 0.0125,
    }


def test_set_prompt_template_rollout_marks_single_challenger() -> None:
    first = PromptTemplate(
        id="prompttpl_1",
        name="architecture_review",
        version=1,
        template_text="ACTIVE {service_name}",
        variables_json=["service_name"],
        model_override=None,
        status="active",
        metadata_json={},
    )
    second = PromptTemplate(
        id="prompttpl_2",
        name="architecture_review",
        version=2,
        template_text="CHALLENGER {service_name}",
        variables_json=["service_name"],
        model_override=None,
        status="draft",
        metadata_json={},
    )
    session = FakePromptSession([first, second])

    rollout = set_prompt_template_rollout(
        session,
        name="architecture_review",
        challenger_version=2,
        mode="canary",
        traffic_percentage=25,
    )

    assert rollout == {
        "name": "architecture_review",
        "active_version": 1,
        "challenger_version": 2,
        "mode": "canary",
        "traffic_percentage": 25.0,
        "auto_promotion_policy": {
            "enabled": False,
            "minimum_challenger_requests": 10,
            "min_candidate_yield_improvement_pct": 2.0,
            "max_error_rate_regression_pct": 1.0,
            "max_latency_regression_ms": 250.0,
            "max_cost_regression_usd": 0.001,
        },
    }
    assert second.metadata_json["rollout"]["mode"] == "canary"
    assert second.metadata_json["rollout"]["traffic_percentage"] == 25.0
    assert "rollout" not in (first.metadata_json or {})


def test_resolve_runtime_prompt_template_can_select_challenger() -> None:
    first = PromptTemplate(
        id="prompttpl_1",
        name="architecture_review",
        version=1,
        template_text="ACTIVE {service_name}",
        variables_json=["service_name"],
        model_override=None,
        status="active",
        metadata_json={},
    )
    second = PromptTemplate(
        id="prompttpl_2",
        name="architecture_review",
        version=2,
        template_text="CHALLENGER {service_name}",
        variables_json=["service_name"],
        model_override=None,
        status="draft",
        metadata_json={"rollout": {"mode": "canary", "traffic_percentage": 100.0}},
    )
    session = FakePromptSession([first, second])

    resolution = resolve_runtime_prompt_template(
        session,
        name="architecture_review",
        selection_key="sess_test",
    )

    assert resolution.record.version == 2
    assert resolution.selection_mode == "challenger_canary"
    assert resolution.active_version == 1
    assert resolution.challenger_version == 2
    assert resolution.rollout_percentage == 100.0


def test_compare_prompt_template_versions_uses_active_baseline_and_metrics() -> None:
    created_at = datetime.now(timezone.utc)
    active = PromptTemplate(
        id="prompttpl_1",
        name="architecture_review",
        version=1,
        template_text="ACTIVE {service_name}",
        variables_json=["service_name"],
        model_override=None,
        status="active",
        metadata_json={},
    )
    challenger = PromptTemplate(
        id="prompttpl_2",
        name="architecture_review",
        version=2,
        template_text="CHALLENGER {service_name}",
        variables_json=["service_name"],
        model_override=None,
        status="draft",
        metadata_json={"rollout": {"mode": "canary", "traffic_percentage": 15.0}},
    )
    request = RequestLog(
        id="req_1",
        session_id="sess_1",
        external_request_id=None,
        requested_model="proxy-auto",
        domain="general",
        task_type="analysis",
        complexity="medium",
        privacy_level="standard",
        request_json={"metadata": {"prompt_template_name": "architecture_review"}},
        effective_request_json={"metadata": {"prompt_template_name": "architecture_review", "prompt_template_version": 2}},
        created_at=created_at,
    )
    response = ModelResponse(
        id="resp_1",
        request_log_id="req_1",
        provider="openai",
        provider_family="OpenAI",
        model="gpt-5",
        latency_ms=300,
        input_tokens=10,
        output_tokens=5,
        cost_estimate=Decimal("0.010000"),
        finish_reason="stop",
        response_json={},
        response_role="selected_response",
        created_at=created_at + timedelta(seconds=1),
    )
    candidate = TrainingCandidate(
        id="cand_1",
        request_log_id="req_1",
        routing_decision_id="route_1",
        session_id="sess_1",
        domain="general",
        task_type="analysis",
        status="approved",
        quality_score=0.9,
        approval_status="approved",
        export_eligible=True,
        selected_response="answer",
        messages_json=[],
        provenance_json={},
        validation_json={},
        metadata_json={"prompt_template_name": "architecture_review", "prompt_template_version": 2},
        created_at=created_at + timedelta(seconds=2),
    )
    session = FakePromptSession([active, challenger], request_rows=[request], response_rows=[response], candidate_rows=[candidate])

    comparison = compare_prompt_template_versions(session, name="architecture_review")

    assert comparison["baseline"]["version"] == 1
    assert comparison["comparison"]["version"] == 2
    assert comparison["family_rollout"]["challenger_version"] == 2
    assert comparison["comparison"]["metrics"]["request_count"] == 1
    assert comparison["comparison"]["metrics"]["candidate_yield_rate_pct"] == 100.0
    assert comparison["recommendation"]["action"] == "continue_canary"
    assert comparison["recommendation"]["confidence"] == "low"


def test_prompt_auto_promotion_policy_and_guarded_promotion() -> None:
    created_at = datetime.now(timezone.utc)
    active = PromptTemplate(
        id="prompttpl_1",
        name="architecture_review",
        version=1,
        template_text="ACTIVE {service_name}",
        variables_json=["service_name"],
        model_override=None,
        status="active",
        metadata_json={},
    )
    challenger = PromptTemplate(
        id="prompttpl_2",
        name="architecture_review",
        version=2,
        template_text="CHALLENGER {service_name}",
        variables_json=["service_name"],
        model_override=None,
        status="draft",
        metadata_json={"rollout": {"mode": "canary", "traffic_percentage": 25.0}},
    )
    request_rows = []
    response_rows = []
    candidate_rows = []
    for index in range(12):
        request_id = f"req_challenger_{index}"
        request_rows.append(
            RequestLog(
                id=request_id,
                session_id=f"sess_{index}",
                external_request_id=None,
                requested_model="proxy-auto",
                domain="general",
                task_type="analysis",
                complexity="medium",
                privacy_level="standard",
                request_json={"metadata": {"prompt_template_name": "architecture_review"}},
                effective_request_json={"metadata": {"prompt_template_name": "architecture_review", "prompt_template_version": 2}},
                created_at=created_at + timedelta(minutes=index),
            )
        )
        response_rows.append(
            ModelResponse(
                id=f"resp_challenger_{index}",
                request_log_id=request_id,
                provider="openai",
                provider_family="OpenAI",
                model="gpt-5",
                latency_ms=200,
                input_tokens=10,
                output_tokens=5,
                cost_estimate=Decimal("0.001000"),
                finish_reason="stop",
                response_json={},
                response_role="selected_response",
                created_at=created_at + timedelta(minutes=index, seconds=1),
            )
        )
        candidate_rows.append(
            TrainingCandidate(
                id=f"cand_challenger_{index}",
                request_log_id=request_id,
                routing_decision_id=f"route_challenger_{index}",
                session_id=f"sess_{index}",
                domain="general",
                task_type="analysis",
                status="approved",
                quality_score=0.9,
                approval_status="approved",
                export_eligible=True,
                selected_response="answer",
                messages_json=[],
                provenance_json={},
                validation_json={},
                metadata_json={"prompt_template_name": "architecture_review", "prompt_template_version": 2},
                created_at=created_at + timedelta(minutes=index, seconds=2),
            )
        )
    for index in range(12):
        request_id = f"req_active_{index}"
        request_rows.append(
            RequestLog(
                id=request_id,
                session_id=f"sess_active_{index}",
                external_request_id=None,
                requested_model="proxy-auto",
                domain="general",
                task_type="analysis",
                complexity="medium",
                privacy_level="standard",
                request_json={"metadata": {"prompt_template_name": "architecture_review"}},
                effective_request_json={"metadata": {"prompt_template_name": "architecture_review", "prompt_template_version": 1}},
                created_at=created_at + timedelta(minutes=index),
            )
        )
        response_rows.append(
            ModelResponse(
                id=f"resp_active_{index}",
                request_log_id=request_id,
                provider="openai",
                provider_family="OpenAI",
                model="gpt-5",
                latency_ms=250,
                input_tokens=10,
                output_tokens=5,
                cost_estimate=Decimal("0.001500"),
                finish_reason="stop",
                response_json={},
                response_role="selected_response",
                created_at=created_at + timedelta(minutes=index, seconds=1),
            )
        )
    session = FakePromptSession([active, challenger], request_rows=request_rows, response_rows=response_rows, candidate_rows=candidate_rows)

    policy = set_prompt_auto_promotion_policy(
        session,
        name="architecture_review",
        enabled=True,
        minimum_challenger_requests=10,
        min_candidate_yield_improvement_pct=2.0,
        max_error_rate_regression_pct=1.0,
        max_latency_regression_ms=250.0,
        max_cost_regression_usd=0.001,
    )
    assert policy["auto_promotion_policy"]["enabled"] is True

    promotion = promote_prompt_template_challenger(
        session,
        name="architecture_review",
        challenger_version=2,
        guarded=True,
    )
    assert promotion["promoted_version"] == 2
    assert promotion["previous_active_version"] == 1
    assert promotion["family_rollout"]["mode"] == "disabled"


def test_evaluate_prompt_auto_promotion_returns_noop_when_disabled() -> None:
    active = PromptTemplate(
        id="prompttpl_1",
        name="architecture_review",
        version=1,
        template_text="ACTIVE {service_name}",
        variables_json=["service_name"],
        model_override=None,
        status="active",
        metadata_json={},
    )
    session = FakePromptSession([active])

    result = evaluate_prompt_auto_promotion(session, name="architecture_review")

    assert result["executed"] is False
    assert result["eligible"] is False
    assert "disabled" in result["summary"].lower()
