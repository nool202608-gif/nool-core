from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def configure_tracing(app: FastAPI, service_name: str, otlp_endpoint: str | None) -> None:
    """Wires up distributed tracing for one FastAPI app, exporting spans to
    an OTLP-compatible collector (Jaeger locally - see compose.yml).

    Tracing is optional and off by default: with no otlp_endpoint, this is
    a no-op and the service behaves exactly as it did before tracing
    existed - no dependency on Jaeger/collector availability to boot.
    Every incoming request gets a server span (via FastAPIInstrumentor),
    and shared/logging's JSONFormatter attaches that span's trace_id/
    span_id to every log line emitted during the request, so a trace and
    its logs can be cross-referenced by trace_id.
    """
    if not otlp_endpoint:
        return

    provider = TracerProvider(resource=Resource.create({SERVICE_NAME: service_name}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint)))
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app)
