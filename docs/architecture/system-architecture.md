# System Architecture

This document is authoritative for system boundaries, module dependencies, runtime topology, and failure ownership. Specialized behavior is authoritative in the linked documents.

## Style and Context

The initial system is a modular monolith: one versioned Python backend exposes FastAPI REST use cases and Celery task entry points, while a React/TypeScript client consumes the API. PostgreSQL is the permanent business and session authority. Redis holds only queues, locks, cancellation hints, and temporary coordination. Files remain behind a `StorageBackend` addressed by configured root plus logical key.

The local network is not trusted. Users authenticate through named local accounts and PostgreSQL-backed server sessions. The primary UI is `fa-IR`/RTL; the API retains stable English technical codes and UTC timestamps. Only server/Docker configuration maps storage `config_key` values to container paths; administrators activate/label those existing keys and never submit host paths.

See [system context](../diagrams/system-context.md) and [container architecture](../diagrams/container-architecture.md).

## Baseline Runtime

The baseline is Windows 11 with Docker Desktop and WSL2, using Linux containers. Exact patch/image versions are pinned during Sprint 1 after official-image and compatibility verification.

| Container/process | Direction/version baseline | Responsibility | Durable state |
|---|---|---|---|
| React web | TypeScript, Node.js 22 LTS build | Persian RTL operational UI; no filesystem authority | None |
| FastAPI API | Python 3.12 | Sessions, authorization, validation, commands/queries, media authorization | PostgreSQL via repositories |
| Image worker | Python 3.12, CPU required | Executes processing runs and candidate finalization | Artifacts via storage; facts in PostgreSQL |
| Maintenance/export worker | Python 3.12 | Scan/hash/preview, reconciliation, and independent exports | Storage plus PostgreSQL |
| PostgreSQL | 17 | Permanent source of truth, including UserSession | Database volume |
| Redis | 7.x | Celery broker, short locks, cancellation hints, temporary state | No required business durability |
| External storage | Server-configured mount | Immutable sources and versioned derived artifacts | Filesystem |

NVIDIA GPU execution is optional and deferred. Native Windows services are not the supported baseline.

## Backend Modules

| Module | Owns | May depend on |
|---|---|---|
| Identity/access | Users, fixed roles/permissions, UserSessions | Shared kernel |
| Storage catalog | Configured root activation, safe keys, source observations/previews, availability | Shared kernel |
| Ingestion/batches | Scan cursor, Batch/BatchImage registration and review-resolution roll-up | Storage catalog, assets |
| Assets | ImageAsset and immutable SourceObservation identity | Storage catalog |
| Processing | Runs, candidates, preset/SubjectMode/shadow snapshots, engine/model registry | Assets, storage catalog |
| Review | Immutable decisions and selected candidate | Processing, identity |
| Export | Independent jobs/items, naming snapshots, production RGB artifacts | Review, storage catalog |
| Operations | Reconciliation, health, metrics, audit queries | Read-only module ports |

Image/Batch state never contains export state. Export reads an approved selected candidate through a Review port, creates its own durable job/item lifecycle, and does not transition BatchImage or Batch.

## Dependency Rules

1. Domain code has no FastAPI, Celery, SQLAlchemy, Redis, imaging library, or filesystem dependency.
2. Application use cases depend on domain types/ports and define Unit of Work boundaries.
3. HTTP and Celery entry points validate/translate only; state transition and permission logic remains in use cases.
4. Infrastructure implements persistence, storage, queue, hashing, clock, password/session, and engine adapters.
5. Processing stages use `PipelineContext`; no stage opens arbitrary paths or writes business state.
6. Domain events are persisted facts/outbox inputs, not event sourcing.

## Critical Flows

- **Session:** login verifies Argon2id, rotates opaque token/CSRF metadata, stores hashes and expiry in UserSession, and sends a secure cookie. Logout, logout-all, password reset, user disable, and role change revoke/invalidate server state.
- **Root activation:** admin submits a server-known config key/alias; backend resolves/probes the configured mount and records expected volume identity. Client paths never configure roots.
- **Scan:** a short transaction creates Batch; scan tasks insert SourceObservations and BatchImages in chunks and stream hashes. Changed same-path content creates a new observation.
- **Process:** claim a run, read its exact observation, execute non-generative stages, atomically finalize artifacts, then lock BatchImage briefly to allocate candidate `version_no` and commit candidate/run/image state.
- **Review:** use SourcePreviewArtifact plus candidate/mask; lock BatchImage, record human decision, and select candidate. Automated scoring only orders work.
- **Batch closure and controlled reopen:** reconcile member processing/review resolutions to a closed-cycle `review_completed` or `partially_completed`. Only the authorized `ReprocessBatchImage` use case may atomically create a run, move the image to `reprocess_queued`, reopen Batch to `processing`, increment `review_cycle` once, and record actor/reason/event. Reprocess commands while already `processing` retain state/cycle; `awaiting_review` returns to `processing` in the same cycle. Workers cannot reopen a Batch.
- **Export:** snapshot naming policy, reserve approved candidate/destination, flatten to production PNG (2000 × 2000, 8-bit sRGB RGB, no alpha, white), atomically finalize, and update ExportItem/Job only.

## Scaling Seams

- Stateless APIs share PostgreSQL/Redis; sessions are not process-local.
- Queue routing separates CPU, deferred GPU, scan/maintenance, and export.
- StorageBackend supports local disk first, shared NAS later, and a future S3-compatible adapter.
- Engine Strategy and immutable preset snapshots preserve run meaning across engine versions.
- Outbox/idempotent consumers permit process scaling without microservices.

Shared logical storage is required before adding worker hosts. Root-level user scoping is deferred; adding it requires an explicit relational/access-policy change.

## Failure Handling

| Failure | Required behavior |
|---|---|
| Browser/API restarts | Server session remains valid unless expired/revoked; DB transaction rolls back and outbox resumes |
| Worker dies | Stale lease reconciliation retries/fails the ProcessingRun within its recorded review cycle; stale candidate finalizer is fenced |
| Redis is lost | Rebuild publish intent from PostgreSQL; no business/session truth is lost |
| Configured mount missing | Root is unavailable; new scans/reads/writes are blocked with typed retryable status |
| Drive disconnects during scan | Batch moves to `scan_paused`; cursor/observations persist |
| Drive disconnects during processing | Run becomes retryable/blocked; BatchImage is not immediately processing-failed |
| Drive disconnects during export | ExportItem retries/fails independently; approved BatchImage is unchanged |
| Different volume reconnects | Root remains blocked until admin validates/rebinds expected identity; no automatic resume |
| Database unavailable | Fail closed; do not create unrecorded work, sessions, candidates, decisions, or exports |
| File write precedes DB commit | Reconcile by operation ID/checksum; adopt only after invariant verification |
| Model missing/corrupt | Prevent dispatch and record typed configuration failure |
| Task targets closed Batch without valid reopen | Reject/reconcile the task; do not create a run intent or change Batch/review cycle |

## Risks and References

BiRefNet CPU demand and Windows/PyTorch compatibility require the planned benchmark. Linux containers mitigate native-Windows Celery limitations. External USB atomicity, reparse, case, Unicode, capacity, and disconnect behavior are release gates. A high image-quality score remains unable to guarantee semantic authenticity.

Domain: [domain model](domain-model.md). States: [state machines](state-machines.md). Storage: [storage design](storage-design.md). Persistence: [database design](database-design.md). Queues: [worker design](worker-and-queue-design.md). Security: [security](security.md).
