# Observability

This document defines local operational telemetry. PostgreSQL resources remain the workflow authority; telemetry helps diagnose and operate them.

## Structured Logs

API, dispatcher, worker, and maintenance processes emit structured JSON to stdout and rotated local files through deployment configuration. Common fields are timestamp UTC, severity, service/process, environment/build, event name, correlation ID, request/command/task/operation ID, actor/session id where appropriate, aggregate type/id, batch/BatchImage/source-observation/run/export IDs, `review_cycle`, state transition, duration, attempt, queue, engine/model, device, and normalized error category. Session identifiers are internal UUIDs only; cookie, token, CSRF, IP, and raw user-agent values are never logged.

Do not log image bytes, credentials/tokens, database URLs, host absolute paths, unrestricted logical keys, raw EXIF, or full exception payloads containing them. Development stack traces are not client responses. Log sampling must never suppress security events, state transitions, terminal failures, review decisions, or exports.

## Correlation and Audit

The edge accepts a valid correlation ID or creates one and propagates it through application commands, outbox, Celery headers, processing events, and logs. Each retry keeps the operation ID and gains an attempt/task ID. Human decisions include actor and correlation ID. `ProcessingEvent` is durable audit/operational history; logs are not a substitute for it.

## Stage Telemetry

Each pipeline stage records queue wait, source-observation verification, read/decode, inference, refinement, correction, optional deterministic shadow, compose, encode, QC, artifact write, and database-finalization durations; input/output dimensions/bytes; peak-memory estimate where obtainable; engine/model/device; and typed warnings. High-cardinality IDs belong in logs/traces, not metric labels.

## Metrics

- API request rate/latency/errors by route template/status
- DB pool saturation, transaction latency, deadlocks, outbox age/backlog
- Redis availability, queue depth/oldest age, publish failures
- Workers online/busy, claims, retries, stale leases, task duration, process recycling
- Batch scan rate, pending/processing/review/failure counts, oldest work age
- Batch approved/rejected/unresolved/processing-failed/cancelled counts and independent exported-at-least-once count
- Batch reopen count, current review cycle, reopen actor/reason category, rejected stale-cycle tasks, and oldest open-cycle age
- Pipeline stage latency, engine failure/warning rate, CPU/RAM/GPU memory/utilization where supported
- Root availability, read/write latency, free bytes, disconnects, partial/orphan files
- Review queue age, decisions/hour, rejection/reprocess reasons; never use as employee performance scoring without policy
- Export throughput, collision/failure count, verification latency
- Session login success/failure, active/revoked/expired counts, CSRF rejection, and global invalidation events without secret/cardinality-heavy labels

Quality measurement distributions are versioned by preset/model and must not be mixed across incompatible revisions.

## Failure Categories

Stable top-level categories are `authentication`, `session_expired`, `csrf`, `validation`, `authorization`, `path_security`, `source_unavailable`, `source_changed`, `volume_identity_mismatch`, `unsupported_media`, `decode_corrupt`, `model_unavailable`, `engine_failure`, `resource_exhausted`, `quality_gate`, `database`, `redis_dispatch`, `artifact_io`, `destination_collision`, `cancelled`, and `internal`. Each identifies retryability and operator guidance. Raw exceptions are mapped once at subsystem boundaries.

## Local Monitoring and Alerts

MVP uses health endpoints, structured logs, PostgreSQL operational queries, Celery/Redis inspection restricted to administrators, and a lightweight local metrics collector/dashboard selected during deployment implementation. Prometheus/Grafana are optional, not required application dependencies in Sprint 1.

Alert conditions include root disconnect/low space, database/Redis unavailable, queue oldest-age breach, no healthy worker, repeated worker loss, stale lease growth, model verification failure, unusual authentication denial, backup failure, and export integrity conflict. Thresholds require hardware/batch baselines.

## Health Semantics

Liveness reports whether a process loop is responsive. Readiness reports whether it can serve its role and includes database, required configuration, and role-specific dependencies; a disconnected optional root does not make the whole API unready. Detailed health is authenticated because it may disclose topology.

## Retention and Time

All hosts synchronize clocks; business timestamps use database/UTC time where ordering matters. Log, metrics, event, and audit retention periods are unresolved operational policy. Disk quotas and rotation prevent telemetry from exhausting processing/export storage.
