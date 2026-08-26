"""Distributed request tracing (OpenTelemetry, exported to Jaeger locally
- see compose.yml). Optional: see configure_tracing's docstring.
"""

from .setup import configure_tracing

__all__ = ["configure_tracing"]
