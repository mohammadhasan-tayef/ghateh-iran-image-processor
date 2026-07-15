# Worker and Queue Design

This document is authoritative for asynchronous dispatch, Celery queues, idempotency, retries, cancellation, concurrency, backpressure, and recovery.

## Responsibilities

PostgreSQL owns intended work, lifecycle state, leases, candidates, review decisions, and export facts. Redis carries Celery messages, short-lived locks, cancellation hints, and disposable result/coordination data. A missing Redis key never means a business operation succeeded, failed, or was cancelled.

A transactional outbox row is committed with state that requires work. A dispatcher publishes it to Celery and marks publication idempotently. Periodic reconciliation republishes unpublished/stale intents and repairs roll-ups.

## Queues

| Queue | Tasks | Default worker profile |
|---|---|---|
| `scan` | Incremental directory chunks, hashing/registration | maintenance, low I/O concurrency |
| `image.cpu` | CPU segmentation and pipeline | image worker, small configured concurrency |
| `image.gpu` | Optional GPU pipeline | one/few processes per GPU with memory guard |
| `export` | Verified copy/finalize | maintenance/export, bounded per-volume concurrency |
| `maintenance` | Outbox dispatch, stale lease and artifact reconciliation, roll-ups, retention | single/fenced periodic execution |

Queue names are routing concerns, not domain concepts. Tasks carry IDs and logical references, not images, model tensors, absolute paths, or full parameter documents.

## Task Protocol and Idempotency

1. Receive `{operation_id, resource_id, expected_version}`.
2. Load authoritative rows and return success for an already equivalent terminal result.
3. Claim using expected state and a random lease/fencing token.
4. Resolve immutable preset/model/storage descriptors.
5. Perform bounded work with cancellation and heartbeat checks.
6. Finalize artifacts using operation-scoped names.
7. Commit completion only if the lease token is current; append event/outbox.

Celery `task_id` aids tracing but is not the idempotency key. Scan chunks key by batch/cursor epoch; processing attempts by `processing_run.id`; exports by `export_item.id`; maintenance jobs by scope/time bucket. `acks_late` and worker-lost rejection are considered only with idempotent behavior and verified Celery transport semantics.

## Retries

Automatically retry bounded transient failures: storage temporarily unavailable, network interruption to PostgreSQL/Redis, lock contention, worker loss, and explicitly classified engine resource startup errors. Use exponential backoff with jitter and a maximum attempt/elapsed-time policy stored with the operation.

Do not auto-retry path-security violations, unsupported/corrupt inputs, source checksum change, missing/unverified model, deterministic decode/model errors, authenticity/quality gates, or resource needs exceeding configured limits. These require configuration, operator review, or an explicit new run. A terminal processing retry creates a linked `ProcessingRun`; redelivery before terminal completion continues the same run.

## Cancellation

The API persists `cancel_requested_at`/intent in PostgreSQL and may set a Redis hint. Workers check before claim, between stages, and during chunkable operations. Cancellation cannot safely interrupt a final rename/DB completion critical section; it completes that short section and records whether the result was committed. Hard termination is a last resort, followed by lease/artifact reconciliation. Exported files are not automatically deleted on later cancellation.

## Concurrency and Resources

- CPU concurrency is derived from measured RAM per run and core availability, not CPU count alone; default conservatively to one image process on unknown hardware.
- GPU workers route only compatible verified model installations; default one process per GPU until memory benchmarks permit more.
- Set hard input pixel/byte limits, per-task time limits, process recycling, prefetch of one for large image tasks, and local scratch quotas.
- Scan and export concurrency is capped per storage root to avoid saturating a USB drive.
- Maintenance tasks use PostgreSQL advisory locks/fencing so multiple schedulers cannot perform the same singleton pass.

## Backpressure

Do not enqueue an entire massive batch at once. Registration writes chunks and creates durable pending intents. A dispatcher maintains queue-depth and pending-work watermarks, pauses scan dispatch or processing publication when Redis depth, database latency, disk free space, storage errors, or worker memory crosses thresholds, and resumes with hysteresis. The UI derives progress from database counts.

## Crash and Redis Recovery

- Stale leases are inspected after expiry. If a matching final artifact verifies, completion is adopted conditionally; otherwise safe temporary artifacts are removed and the task returns to pending or fails by policy.
- Unpublished outbox messages are republished. Published-but-unconsumed work is reconstructed from nonterminal rows after a Redis loss.
- Late completions with stale fencing tokens are rejected and their unreferenced artifacts quarantined/reconciled.
- Batch/job roll-ups recompute from member/item state, making missed notifications repairable.
- Shutdown stops new claims, signals cancellation only when requested, and allows a configured grace period.

## Operational Risks

Celery on native Windows has limitations; the supported baseline runs Linux worker containers under the Windows host deployment. GPU passthrough, PyTorch/CUDA versions, and Docker/WSL compatibility need a dedicated spike. Redis result backend data is optional and short-lived because operational status comes from PostgreSQL.
