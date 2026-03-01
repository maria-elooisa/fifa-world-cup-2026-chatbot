"""
Observability helpers:
- Structured JSON logs (python-json-logger)
- Optional Arize Phoenix tracing (OpenTelemetry)
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager, nullcontext
from typing import Any, Dict, Iterator, Optional

try:
    from pythonjsonlogger import jsonlogger
except Exception:  # pragma: no cover - fallback when dependency is missing
    jsonlogger = None

try:
    from opentelemetry import metrics as otel_metrics
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
        OTLPMetricExporter,
    )
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource

    _METRICS_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    otel_metrics = None
    OTLPMetricExporter = None
    MeterProvider = None
    PeriodicExportingMetricReader = None
    Resource = None
    SERVICE_NAME = "service.name"
    _METRICS_AVAILABLE = False

logger = logging.getLogger(__name__)

_LOGGING_CONFIGURED = False
_OBSERVABILITY_MANAGER: Optional["ObservabilityManager"] = None
_RESERVED_LOG_RECORD_KEYS = set(logging.makeLogRecord({}).__dict__.keys())
_METRICS_CONFIGURED = False


def configure_structured_logging() -> None:
    """
    Configure root logger with JSON formatter.
    Safe to call multiple times.
    """
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return

    log_level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Avoid duplicated handlers and mixed formats.
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    stream_handler = logging.StreamHandler()
    if jsonlogger is not None:
        log_format = (
            "%(asctime)s %(levelname)s %(name)s %(message)s "
            "%(event)s %(component)s %(worker_id)s %(worker_type)s "
            "%(source)s %(query_scope)s %(task_count)s %(duration_ms)s"
        )
        formatter = jsonlogger.JsonFormatter(log_format)
    else:  # pragma: no cover
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s"
        )

    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)
    _LOGGING_CONFIGURED = True

    logger.info(
        "structured_logging_configured",
        extra={
            "event": "structured_logging_configured",
            "component": "observability",
            "source": "logging",
        },
    )


def _parse_otel_headers(raw: Optional[str]) -> Dict[str, str]:
    """
    Parse OTEL headers from env string like:
    "k1=v1,k2=v2" or "k1=v1\nk2=v2"
    """
    if not raw:
        return {}
    pairs = []
    for chunk in raw.replace("\n", ",").split(","):
        item = chunk.strip()
        if not item:
            continue
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key and value:
            pairs.append((key, value))
    return dict(pairs)


class ObservabilityManager:
    """
    Central point for tracing and structured event logging.

    Arize Phoenix is optional and enabled via:
    - PHOENIX_ENABLED=true
    - PHOENIX_PROJECT_NAME=<name> (optional)
    - PHOENIX_COLLECTOR_ENDPOINT=<url> (optional, default local)
    """

    def __init__(self) -> None:
        self.phoenix_enabled = os.getenv("PHOENIX_ENABLED", "false").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.metrics_enabled = os.getenv("METRICS_ENABLED", "true").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.project_name = os.getenv(
            "PHOENIX_PROJECT_NAME", "fifa-world-cup-chatbot"
        )
        self.collector_endpoint = os.getenv(
            "PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006/v1/traces"
        )
        self._tracer = None
        self._meter = None
        self._metrics: Dict[str, Any] = {}

        if self.phoenix_enabled:
            self._tracer = self._init_phoenix_tracer()
        else:
            logger.info(
                "phoenix_disabled",
                extra={
                    "event": "phoenix_disabled",
                    "component": "observability",
                    "source": "phoenix",
                },
            )
        if self.metrics_enabled:
            self._init_metrics()

    def _init_phoenix_tracer(self):
        try:
            from phoenix.otel import register
            from opentelemetry import trace

            try:
                register(
                    project_name=self.project_name,
                    endpoint=self.collector_endpoint,
                )
            except TypeError:
                # Backward compatibility for older signatures.
                register(project_name=self.project_name)

            tracer = trace.get_tracer("fifa_world_cup_chatbot")
            logger.info(
                "phoenix_enabled",
                extra={
                    "event": "phoenix_enabled",
                    "component": "observability",
                    "source": "phoenix",
                },
            )
            return tracer
        except Exception as exc:
            logger.warning(
                "phoenix_unavailable",
                extra={
                    "event": "phoenix_unavailable",
                    "component": "observability",
                    "source": "phoenix",
                    "error": str(exc),
                },
            )
            return None

    def _init_metrics(self) -> None:
        """Inicializa métricas OTEL (opcional)."""
        global _METRICS_CONFIGURED
        if _METRICS_CONFIGURED:
            return
        if not _METRICS_AVAILABLE:
            logger.info(
                "metrics_unavailable",
                extra={
                    "event": "metrics_unavailable",
                    "component": "observability",
                    "source": "metrics",
                },
            )
            return

        endpoint = os.getenv(
            "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
            "http://localhost:6006/v1/metrics",
        )
        interval_raw = os.getenv("OTEL_EXPORTER_OTLP_METRICS_INTERVAL_MS", "15000")
        try:
            export_interval_ms = max(1000, int(interval_raw))
        except Exception:
            export_interval_ms = 15000
        headers = _parse_otel_headers(
            os.getenv("OTEL_EXPORTER_OTLP_METRICS_HEADERS")
            or os.getenv("OTEL_EXPORTER_OTLP_HEADERS")
        )
        if not headers:
            phoenix_api_key = os.getenv("PHOENIX_API_KEY")
            if phoenix_api_key:
                headers = {"Authorization": f"Bearer {phoenix_api_key}"}
        try:
            reader = PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=endpoint, headers=headers or None),
                export_interval_millis=export_interval_ms,
            )
            provider = MeterProvider(
                resource=Resource.create({SERVICE_NAME: "fifa-world-cup-chatbot"}),
                metric_readers=[reader],
            )
            otel_metrics.set_meter_provider(provider)
            self._meter = otel_metrics.get_meter("fifa_world_cup_chatbot")
            self._metrics["requests_total"] = self._meter.create_counter(
                "requests_total", unit="1", description="Total de tarefas processadas"
            )
            self._metrics["requests_failed_total"] = self._meter.create_counter(
                "requests_failed_total",
                unit="1",
                description="Total de tarefas com falha",
            )
            self._metrics["requests_by_scope_total"] = self._meter.create_counter(
                "requests_by_scope_total",
                unit="1",
                description="Total de tarefas por escopo",
            )
            self._metrics["scope_rejected_total"] = self._meter.create_counter(
                "scope_rejected_total",
                unit="1",
                description="Total de tarefas rejeitadas por escopo",
            )
            self._metrics["fallback_total"] = self._meter.create_counter(
                "fallback_total",
                unit="1",
                description="Total de fallbacks executados",
            )
            self._metrics["task_latency_ms"] = self._meter.create_histogram(
                "task_latency_ms",
                unit="ms",
                description="Latência por tarefa (ms)",
            )
            self._metrics["worker_latency_ms"] = self._meter.create_histogram(
                "worker_latency_ms",
                unit="ms",
                description="Latência por worker (ms)",
            )
            self._metrics["llm_tokens_used"] = self._meter.create_histogram(
                "llm_tokens_used",
                unit="1",
                description="Tokens usados por resposta do LLM",
            )
            self._metrics["response_chars"] = self._meter.create_histogram(
                "response_chars",
                unit="1",
                description="Tamanho da resposta (caracteres)",
            )
            self._metrics["response_source_total"] = self._meter.create_counter(
                "response_source_total",
                unit="1",
                description="Contagem de respostas por fonte",
            )
            self._metrics["quality_flags_total"] = self._meter.create_counter(
                "quality_flags_total",
                unit="1",
                description="Indicadores simples de qualidade (ex: has_source, ambiguous)",
            )
            _METRICS_CONFIGURED = True
            logger.info(
                "metrics_enabled",
                extra={
                    "event": "metrics_enabled",
                    "component": "observability",
                    "source": "metrics",
                    "endpoint": endpoint,
                    "interval_ms": export_interval_ms,
                    "headers_configured": bool(headers),
                },
            )
        except Exception as exc:
            logger.warning(
                "metrics_init_failed",
                extra={
                    "event": "metrics_init_failed",
                    "component": "observability",
                    "source": "metrics",
                    "error": str(exc),
                },
            )
            self._meter = None
            self._metrics = {}

    @contextmanager
    def span(
        self,
        name: str,
        attributes: Optional[Dict[str, Any]] = None,
        span_kind: Optional[str] = None,
    ) -> Iterator[Any]:
        """
        Create a tracing span when Phoenix/OTel is available.
        Falls back to a no-op context manager.
        """
        if self._tracer is None:
            with nullcontext():
                yield None
            return

        try:
            from opentelemetry.trace import Status, StatusCode
        except Exception:  # pragma: no cover - defensive fallback
            Status = None
            StatusCode = None

        with self._tracer.start_as_current_span(name) as span:
            if span_kind:
                try:
                    # Compatibilidade com diferentes versões do Phoenix/OpenInference
                    span.set_attribute("openinference.span.kind", span_kind)
                    span.set_attribute("openinference.span_kind", span_kind)
                    span.set_attribute("span.kind", span_kind)
                except Exception:
                    pass
            if attributes:
                for key, value in attributes.items():
                    try:
                        span.set_attribute(key, value)
                    except Exception:
                        # Keep tracing non-blocking.
                        pass
            try:
                yield span
                if StatusCode is not None and Status is not None:
                    span.set_status(Status(StatusCode.OK))
            except Exception as exc:
                if StatusCode is not None and Status is not None:
                    try:
                        span.record_exception(exc)
                        span.set_status(Status(StatusCode.ERROR, str(exc)))
                    except Exception:
                        pass
                raise

    def log_event(
        self,
        log: logging.Logger,
        event: str,
        level: int = logging.INFO,
        **fields: Any,
    ) -> None:
        """Emit structured log event with safe extra fields."""
        payload = {"event": event}
        for key, value in fields.items():
            safe_key = f"field_{key}" if key in _RESERVED_LOG_RECORD_KEYS else key
            payload[safe_key] = value
        log.log(level, event, extra=payload)

    def record_task_metrics(
        self,
        worker_type: str,
        duration_ms: float,
        ok: bool,
        query_scope: str | None = None,
    ) -> None:
        """Registra métricas customizadas por tarefa."""
        if not self._metrics:
            return
        attrs = {"worker_type": worker_type}
        if query_scope:
            attrs["query_scope"] = query_scope
        try:
            self._metrics["requests_total"].add(1, attrs)
            if not ok:
                self._metrics["requests_failed_total"].add(1, attrs)
            self._metrics["task_latency_ms"].record(duration_ms, attrs)
        except Exception:
            # Não deve quebrar a execução caso métrica falhe.
            pass

    def record_scope_metrics(self, query_scope: str) -> None:
        """Registra contagem por escopo."""
        if not self._metrics:
            return
        try:
            self._metrics["requests_by_scope_total"].add(1, {"query_scope": query_scope})
        except Exception:
            pass

    def record_worker_latency(self, worker_type: str, duration_ms: float) -> None:
        """Registra latência do worker."""
        if not self._metrics:
            return
        try:
            self._metrics["worker_latency_ms"].record(duration_ms, {"worker_type": worker_type})
        except Exception:
            pass

    def record_scope_rejection(self, reason: str = "out_of_scope") -> None:
        """Registra rejeição por escopo."""
        if not self._metrics:
            return
        try:
            self._metrics["scope_rejected_total"].add(1, {"reason": reason})
        except Exception:
            pass

    def record_fallback(self, fallback_type: str, worker_type: str | None = None) -> None:
        """Registra ocorrências de fallback."""
        if not self._metrics:
            return
        attrs = {"type": fallback_type}
        if worker_type:
            attrs["worker_type"] = worker_type
        try:
            self._metrics["fallback_total"].add(1, attrs)
        except Exception:
            pass

    def record_llm_metrics(
        self, worker_type: str, tokens_used: int | None, response_text: str | None
    ) -> None:
        """Registra métricas relacionadas à resposta do LLM."""
        if not self._metrics:
            return
        attrs = {"worker_type": worker_type}
        try:
            if tokens_used is not None:
                self._metrics["llm_tokens_used"].record(int(tokens_used), attrs)
            if response_text is not None:
                self._metrics["response_chars"].record(len(str(response_text)), attrs)
        except Exception:
            pass

    def record_response_source(
        self, source: str | None, context_source: str | None = None
    ) -> None:
        """Registra contagem por fonte de resposta (simulada vs real)."""
        if not self._metrics:
            return
        if not source:
            source = "unknown"
        attrs = {"source": source}
        if context_source:
            attrs["context_source"] = context_source
        try:
            self._metrics["response_source_total"].add(1, attrs)
        except Exception:
            pass

    def record_quality_flag(
        self,
        flag: str,
        value: bool = True,
        context_source: str | None = None,
    ) -> None:
        """Registra indicadores simples de qualidade (booleanos)."""
        if not self._metrics:
            return
        if not flag:
            return
        attrs = {"flag": str(flag), "value": "true" if value else "false"}
        if context_source:
            attrs["context_source"] = context_source
        try:
            self._metrics["quality_flags_total"].add(1, attrs)
        except Exception:
            pass

    @staticmethod
    def elapsed_ms(start_time: float) -> float:
        return round((time.perf_counter() - start_time) * 1000, 2)


def get_observability_manager() -> ObservabilityManager:
    global _OBSERVABILITY_MANAGER
    if _OBSERVABILITY_MANAGER is None:
        _OBSERVABILITY_MANAGER = ObservabilityManager()
    return _OBSERVABILITY_MANAGER


def init_observability() -> ObservabilityManager:
    """
    Initialize structured logs + optional Phoenix tracing.
    """
    configure_structured_logging()
    return get_observability_manager()
