# Worker and Queue Design

This document is authoritative for asynchronous dispatch, queues, idempotency, candidate concurrency, retries, cancellation, backpressure, and recovery.

## Truth and Queues

PostgreSQL owns intended work, Batch/BatchImage/ProcessingRun states, SourceObservations, candidates, review, UserSessions, and independent export state. Redis carries Celery messages, short locks, cancellation hints, and disposable coordination. Celery/Redis never determine business or authentication truth.

| Queue | Work | Baseline profile |
|---|---|---|
| `scan` | Incremental list, SourceObservation creation, streamed hashing/registration, source preview generation | maintenance, bounded I/O |
| `image.cpu` | CPU pipeline and candidate creation | low concurrency, Python 3.12 Linux container |
| `image.gpu` | Deferred optional NVIDIA profile | one/few processes per verified GPU |
| `export` | Independent production RGB PNG finalization | bounded per-root I/O |
| `maintenance` | Outbox, stale lease/artifact reconciliation, roll-ups, retention | fenced singleton passes |

Tasks carry operation/resource ids and expected versions, never image bytes, mount paths, model tensors, or unbounded snapshots. A transactional outbox publishes committed intent; reconciliation republishes pending intent after Redis loss.

## Task Protocol

1. Load authoritative resource and return an equivalent completed result on duplicate delivery.
2. Claim expected state with random lease/fencing token.
3. Resolve exact SourceObservation, immutable preset/naming/model snapshot, server-configured root, and ProcessingRun review cycle.
4. Perform bounded work with heartbeat/cancellation checks.
5. Write operation-scoped temporary artifacts and validate checksum/media facts.
6. Commit completion only with the current fencing token; append event/outbox.

Idempotency keys: scan by batch/cursor epoch, hash/preview by SourceObservation/generation, reprocess command by actor/route key, process by ProcessingRun id/output slot, export by ExportItem id, and maintenance by scope/time bucket. Celery task id is trace metadata only.

## Reprocess Dispatch Guard

Only the application-layer `ReprocessBatchImage` command may create the run/outbox intent that reopens a closed Batch. It locks Batch then BatchImage, increments `review_cycle` only when leaving `review_completed`/`partially_completed`, moves `awaiting_review` to `processing` without increment, and commits run/image/batch/event/outbox atomically. Workers never transition a closed Batch.

Before claiming a reprocess task, a worker verifies that the referenced ProcessingRun exists, its `review_cycle` equals the Batch current cycle, Batch is `processing`, BatchImage is `reprocess_queued` or the expected claim state, and the outbox/command intent is durable. A task delivered for a closed Batch, stale cycle, absent run, or cancelled/failed Batch is rejected/reconciled without changing Batch. Reprocesses added while Batch is already open retain the current cycle.

## Candidate Finalization and Concurrency

Candidate identity is UUID; `version_no` is human-readable per BatchImage. After artifact verification, the worker starts a short transaction, checks run lease/idempotency/review cycle, obtains `FOR UPDATE` on BatchImage, returns the existing candidate for an already-finalized output slot, calculates/allocates the next sequence while locked, inserts CandidateVersion, completes the ProcessingRun when its expected outputs finalize, transitions BatchImage to `candidate_ready`, and emits cycle-bearing events/outbox.

Never use an unprotected `MAX(version_no) + 1`. Concurrent different reprocess runs may compute artifacts, but finalization serializes sequence allocation. Composite FKs and unique `(batch_image_id, version_no)` guard mistakes. A stale worker cannot commit. Losing after artifact write creates a reconcilable orphan; losing after DB commit makes redelivery return the existing candidate.

## Retries and Cancellation

Retry bounded transient mount unavailability, PostgreSQL/Redis interruption, lock contention, worker loss, and classified resource startup errors with exponential backoff/jitter and durable limits. Do not automatically retry path-security, corrupt/unsupported input, changed source observation, missing/unverified model, deterministic engine/decode, authenticity gate, or oversized resource failures. A terminal process retry creates a linked new ProcessingRun.

Cancellation is persisted in PostgreSQL with optional Redis hint. Workers check before claim and between chunk/stage boundaries. A short atomic finalize critical section completes or rolls back; hard termination requires lease/artifact reconciliation. Cancelling/failing an ExportItem never moves BatchImage out of `human_approved`.

## Resources and Backpressure

- CPU is mandatory; unknown hardware starts at one image process and one active task until RAM/latency benchmarks.
- Optional GPU queue is deferred and records device/model in a new run; no silent device substitution.
- Enforce byte/pixel/time/RAM/scratch limits, worker recycling, and prefetch one for large image work.
- Cap scan/hash/preview/export concurrency per root to protect USB I/O.
- Do not publish an entire massive batch. Registration and outbox dispatch use bounded chunks/watermarks and pause/resume with hysteresis.

## Crash, Mount, and Roll-Up Recovery

- Stale run leases return to pending only if no candidate exists; verified final artifacts may be adopted only through all relational/provenance checks.
- Unpublished/outstanding PostgreSQL intents rebuild queues after Redis loss.
- Late stale-token completion is rejected; orphan artifacts are quarantined/reconciled.
- Batch roll-up uses only BatchImage processing/review states and the current review cycle. ExportJob roll-up uses only ExportItem states. Export-at-least-once is a derived metric, not Batch closure; prior exports are unchanged by reopen.
- Missing mount holds work. Scan pauses; processing retries/blocks; export item retries/fails independently. A different reconnected volume identity blocks all automatic resume.
- Shutdown stops claims and allows a configured grace period.

## Baseline Risk

Celery native Windows support is not the baseline. Workers run in Linux containers under Windows 11/Docker Desktop/WSL2. Redis 7.x, Python 3.12, and exact images/patches are pinned and compatibility-tested in Sprint 1. GPU/PyTorch/CUDA remains a later profile.
