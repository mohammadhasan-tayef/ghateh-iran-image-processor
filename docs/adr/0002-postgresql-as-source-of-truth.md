# ADR 0002: PostgreSQL Is the Source of Truth

- Status: Accepted
- Date: 2026-07-15

## Context

Long-running work must survive browser, worker, queue, and machine restarts. Review decisions, selected versions, exports, retries, and audit history require durable relational constraints and transactions.

## Decision

PostgreSQL is authoritative for all business entities, lifecycle state, intended work, leases, idempotency, outbox messages, review decisions, export facts, and audit events. Redis/Celery state is never used to infer business success. Files hold image bytes behind logical keys; PostgreSQL holds descriptors and checksums, never image blobs.

## Consequences

- Redis can be lost and reconstructed from pending/outbox records without losing accepted decisions.
- Transactional outbox and idempotent consumers are required.
- Database availability gates stateful work; workers fail closed when they cannot record provenance.
- PostgreSQL backup/restore and migration compatibility become critical operations. File backup and reconciliation remain separate because database and filesystem cannot share one transaction.

## Rejected Alternatives

Redis-only job state is too volatile. Celery result state lacks domain invariants. Event sourcing is unnecessary complexity. Image blobs would inflate backup/IO and couple artifact serving to the database.
