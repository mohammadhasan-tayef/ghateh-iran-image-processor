# ADR 0003: Use Redis and Celery for Background Coordination

- Status: Accepted
- Date: 2026-07-15

## Context

Scanning, inference, and export must continue without a browser and require bounded asynchronous work, queue routing, retry delivery, and worker concurrency. The planned Python stack favors mature local tooling.

## Decision

Use Celery for task delivery and Redis as broker/temporary coordination store. Separate scan, CPU image, optional GPU image, export, and maintenance queues. Tasks contain identifiers only, claim durable operations in PostgreSQL, use fencing leases/idempotency, and report completion there. Redis may hold short locks, cancellation hints, and ephemeral results; it does not hold permanent business truth.

## Consequences

- Queue loss is recoverable through the PostgreSQL outbox and reconciliation.
- At-least-once delivery and duplicates are normal and must be tested.
- Native Windows Celery limitations make Linux containers/WSL2 the baseline worker environment.
- Queue depth/backpressure, graceful shutdown, task size, and worker memory require explicit operation.

## Rejected Alternatives

In-process jobs do not survive API restart and cannot scale workers. PostgreSQL polling alone is possible but would require building scheduling/worker controls now. Kafka is disproportionate for the MVP.
