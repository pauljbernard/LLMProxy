"""Telemetry helpers for Prometheus metrics and OpenTelemetry spans."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Tracer
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Histogram, generate_latest

from app.config import Settings, get_settings

if TYPE_CHECKING:
    from opentelemetry.trace import Span


_PROMETHEUS_REGISTRY: CollectorRegistry | None = None
_REQUEST_COUNTER: Counter | None = None
_REQUEST_LATENCY: Histogram | None = None
_PROVIDER_ATTEMPTS: Counter | None = None
_PROVIDER_LATENCY: Histogram | None = None
_CACHE_EVENTS: Counter | None = None
_OTEL_CONFIG: tuple[bool, str, str | None] | None = None
_OTEL_INITIALIZED = False


def _initialize_prometheus_registry() -> None:
    global _PROMETHEUS_REGISTRY
    global _REQUEST_COUNTER, _REQUEST_LATENCY, _PROVIDER_ATTEMPTS, _PROVIDER_LATENCY, _CACHE_EVENTS
    _PROMETHEUS_REGISTRY = CollectorRegistry(auto_describe=True)
    _REQUEST_COUNTER = Counter(
        "llmproxy_requests_total",
        "Total proxied requests by endpoint and result status.",
        labelnames=("endpoint", "provider", "stream", "status"),
        registry=_PROMETHEUS_REGISTRY,
    )
    _REQUEST_LATENCY = Histogram(
        "llmproxy_request_latency_seconds",
        "End-to-end request latency in seconds.",
        labelnames=("endpoint", "provider", "stream", "status"),
        registry=_PROMETHEUS_REGISTRY,
    )
    _PROVIDER_ATTEMPTS = Counter(
        "llmproxy_provider_attempts_total",
        "Provider invocation attempts by provider and outcome.",
        labelnames=("provider", "stream", "outcome"),
        registry=_PROMETHEUS_REGISTRY,
    )
    _PROVIDER_LATENCY = Histogram(
        "llmproxy_provider_latency_seconds",
        "Provider invocation latency in seconds.",
        labelnames=("provider", "stream", "outcome"),
        registry=_PROMETHEUS_REGISTRY,
    )
    _CACHE_EVENTS = Counter(
        "llmproxy_cache_events_total",
        "Cache events by cache layer and outcome.",
        labelnames=("cache", "outcome"),
        registry=_PROMETHEUS_REGISTRY,
    )


_initialize_prometheus_registry()


def _normalize_labels(attributes: dict[str, object] | None) -> dict[str, str]:
    return {str(key): str(value) for key, value in (attributes or {}).items()}


def configure_telemetry(settings: Settings | None = None) -> None:
    """Initialize OTEL exporting if configured. Prometheus metrics are always local."""

    global _OTEL_CONFIG, _OTEL_INITIALIZED
    settings = settings or get_settings()
    config = (
        bool(settings.llmproxy_otel_enabled),
        settings.llmproxy_otel_service_name,
        settings.llmproxy_otel_exporter_otlp_endpoint,
    )
    if _OTEL_INITIALIZED and _OTEL_CONFIG == config:
        return
    _OTEL_CONFIG = config
    _OTEL_INITIALIZED = True
    if not settings.llmproxy_otel_enabled or not settings.llmproxy_otel_exporter_otlp_endpoint:
        return
    provider = TracerProvider(resource=Resource.create({"service.name": settings.llmproxy_otel_service_name}))
    processor = BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.llmproxy_otel_exporter_otlp_endpoint))
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)


def get_tracer(name: str) -> Tracer:
    configure_telemetry()
    return trace.get_tracer(name)


@contextmanager
def start_span(name: str, *, attributes: dict[str, object] | None = None):
    tracer = get_tracer("llmproxy")
    with tracer.start_as_current_span(name) as span:
        for key, value in (attributes or {}).items():
            span.set_attribute(key, value)
        yield span


def set_span_attributes(span: "Span | None", attributes: dict[str, object]) -> None:
    if span is None:
        return
    for key, value in attributes.items():
        span.set_attribute(key, value)


def emit_metric(name: str, value: float, *, attributes: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "metric": name,
        "value": value,
        "attributes": attributes or {},
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }


def emit_counter(name: str, *, increment: int = 1, attributes: dict[str, object] | None = None) -> dict[str, object]:
    return emit_metric(name, float(increment), attributes=attributes)


def observe_request(*, endpoint: str, provider: str, stream: bool, status: str, latency_seconds: float) -> None:
    assert _REQUEST_COUNTER is not None
    assert _REQUEST_LATENCY is not None
    labels = {
        "endpoint": endpoint,
        "provider": provider or "unknown",
        "stream": str(bool(stream)).lower(),
        "status": status,
    }
    _REQUEST_COUNTER.labels(**labels).inc()
    _REQUEST_LATENCY.labels(**labels).observe(max(0.0, latency_seconds))


def observe_provider_attempt(*, provider: str, stream: bool, outcome: str, latency_seconds: float) -> None:
    assert _PROVIDER_ATTEMPTS is not None
    assert _PROVIDER_LATENCY is not None
    labels = {
        "provider": provider,
        "stream": str(bool(stream)).lower(),
        "outcome": outcome,
    }
    _PROVIDER_ATTEMPTS.labels(**labels).inc()
    _PROVIDER_LATENCY.labels(**labels).observe(max(0.0, latency_seconds))


def observe_cache_event(*, cache: str, outcome: str) -> None:
    assert _CACHE_EVENTS is not None
    _CACHE_EVENTS.labels(cache=cache, outcome=outcome).inc()


def prometheus_metrics_payload() -> bytes:
    assert _PROMETHEUS_REGISTRY is not None
    return generate_latest(_PROMETHEUS_REGISTRY)


def prometheus_metrics_content_type() -> str:
    return CONTENT_TYPE_LATEST


def reset_telemetry_state_for_tests() -> None:
    global _OTEL_CONFIG, _OTEL_INITIALIZED
    _initialize_prometheus_registry()
    _OTEL_CONFIG = None
    _OTEL_INITIALIZED = False

