"""Tests shared/logging/formatter.py's trace/span correlation - lives here
since there is no shared-level test runner configured (see other
services/*/tests for the same pattern testing shared code through a
consumer).
"""

import json
import logging

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from shared.logging.formatter import JSONFormatter


def _make_record(message: str = "hello") -> logging.LogRecord:
    return logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=1, msg=message, args=(), exc_info=None
    )


def test_no_trace_id_when_no_span_is_active():
    payload = json.loads(JSONFormatter("core").format(_make_record()))

    assert "trace_id" not in payload
    assert "span_id" not in payload


def test_includes_trace_id_and_span_id_of_the_active_span():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")

    with tracer.start_as_current_span("test-span"):
        payload = json.loads(JSONFormatter("core").format(_make_record()))
        span_context = trace.get_current_span().get_span_context()

    assert payload["trace_id"] == format(span_context.trace_id, "032x")
    assert payload["span_id"] == format(span_context.span_id, "016x")
    assert len(payload["trace_id"]) == 32
    assert len(payload["span_id"]) == 16
