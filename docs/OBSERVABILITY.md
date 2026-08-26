# Observability

## Distributed tracing

Every request to `auth` or `core` gets an OpenTelemetry span, exported to
[Jaeger](https://www.jaegertracing.io/) (a local Compose service, pinned to
`jaegertracing/all-in-one:1.76.0`). See `shared/tracing/setup.py`.

- **UI**: `http://localhost:${JAEGER_UI_PORT_HOST:-16686}` (local dev only
  - `compose.override.yml`, not exposed by the base `compose.yml`).
- **Wiring**: each service's `main.py` calls
  `configure_tracing(app, settings.service_name, settings.otel_exporter_otlp_endpoint)`
  once, at startup. `OTEL_EXPORTER_OTLP_ENDPOINT` (set in `compose.yml` to
  `http://jaeger:4318/v1/traces`, the internal Docker-network address -
  never routed through NGINX) is the only thing that turns tracing on;
  unset, `configure_tracing` is a no-op and the service behaves exactly as
  it did before tracing existed. A service must always boot cleanly
  without Jaeger available.
- **What's instrumented**: FastAPI request/response spans only, via
  `FastAPIInstrumentor` (auto-instrumentation - no manual span code in
  route handlers). NGINX itself isn't instrumented (no OTel module in the
  base `nginx:1.27-alpine` image), so a trace starts at whichever service
  NGINX forwards to, not at the edge.
- **Log correlation**: every structured JSON log line includes `trace_id`/
  `span_id` for whatever span was active when it was emitted (see
  `shared/logging/formatter.py`) - so a trace in Jaeger and its
  corresponding log lines can be cross-referenced by `trace_id`, in either
  direction, without any extra plumbing in route handlers.

Not done: NGINX-level spans, sampling configuration (currently
always-on/always-sample - fine at local-dev traffic volumes, not something
to take to production as-is), and cross-service trace propagation for a
single logical operation that spans multiple services (there is no
request today that calls both `auth` and `core` in one chain, so this
hasn't come up - `traceparent` propagation would need explicit handling
if/when one does).

## Audit trail (authentication events)

Every token verification outcome - success or failure - emits exactly one
structured log line with an `event` field, from
`shared/auth/providers/firebase.py`:

| `event` | Meaning | Fields |
| --- | --- | --- |
| `auth.token_verified` | A token was successfully verified. | `uid` |
| `auth.token_verification_failed` | A token failed verification. | `reason` (`expired`, `revoked`, `user_disabled`, `invalid`, or `error` for anything unexpected) |

This is a log stream, not a database table - there is no `users`/audit
schema yet (root `CLAUDE.md`'s "Current Goal" excludes the full product
schema), and a structured, append-only log stream is a legitimate audit
mechanism on its own, answerable by filtering on `event` in whatever log
aggregation the deployment uses.

**Deliberately not included**: `uid` on a *failed* verification. At the
point a token fails verification, nothing in it is trustworthy enough to
attribute the attempt to a specific account - logging an unverified claim
as fact would be worse than not logging it. `reason` plus the correlated
`trace_id`/`request_id` is what's available for a failed attempt.

**Not done**: retention policy, shipping these logs anywhere queryable
beyond stdout/`docker compose logs`, and audit events for anything beyond
token verification (e.g. role changes via `scripts/set_role.py` are not
currently audit-logged - that script runs with your own Firebase Admin
credentials, outside any service, so there's no service-side log to emit
one into).
