# System Architecture

This document is authoritative for system boundaries, module dependencies, runtime topology, and failure ownership. Specialized details live in the linked architecture documents.

## Style and Context

The initial system is a modular monolith: one versioned backend codebase exposes REST use cases and supplies Celery task entry points, while a separate React client consumes the API. PostgreSQL is the business-state authority. Redis is disposable coordination infrastructure. Files remain in configured storage roots behind a `StorageBackend` port.

The local-network boundary is not trusted. Browser users authenticate to the API; only administrators configure host path mappings. External engines are invoked through adapters and cannot update domain state directly.

See [system context](../diagrams/system-context.md) and [container architecture](../diagrams/container-architecture.md).

## Initial Runtime Containers

| Container/process | Responsibility | Durable state |
|---|---|---|
| React/Vite web | Operational UI; no filesystem authority | None |
| FastAPI API | Auth, validation, commands/queries, media authorization | PostgreSQL through repositories |
| Image worker | Executes one processing run at a time per assigned slot | Artifacts through storage; facts through API/application services |
| Maintenance/export worker | Scan chunks, reconciliation, previews, and exports | Same ports as image worker |
| PostgreSQL | Permanent source of truth and audit history | Database volume |
| Redis | Celery broker/result coordination, short locks, cancellation hints | None required for business recovery |
| External storage | Immutable originals and versioned derived artifacts | Filesystem |

## Backend Modules

| Module | Owns | May depend on |
|---|---|---|
| Identity/access | Users, roles, sessions, authorization policy | Shared kernel |
| Storage catalog | Root aliases, safe keys, capabilities, availability | Shared kernel |
| Ingestion/batches | Scan cursor, batch membership, registration | Storage catalog, assets |
| Assets | Original identity and immutable metadata | Storage catalog |
| Processing | Runs, candidate versions, presets, engine registry | Assets, storage catalog |
| Review | Decisions and selected candidate | Processing, identity |
| Export | Export jobs/items and final artifact records | Review, storage catalog |
| Operations | Reconciliation, health, metrics, audit queries | Read-only access to module ports |

Each module has presentation adapters, application commands/queries, domain types, and infrastructure adapters. Cross-module calls target explicit application/domain ports. Database models, Celery tasks, HTTP schemas, and engine objects do not cross into domain APIs.

## Dependency Rules

1. Domain code has no FastAPI, Celery, SQLAlchemy, Redis, OpenCV, PyTorch, or filesystem dependency.
2. Application use cases depend on domain types and ports; they define transaction boundaries through a Unit of Work.
3. Presentation and worker entry points validate input and invoke use cases; they contain no business transition logic.
4. Infrastructure implements repositories, storage, queues, clocks, hashes, and engine adapters.
5. Processing stages operate on a `PipelineContext` contract and return facts/artifact descriptors; persistence is orchestrated outside individual stages.
6. Domain events are in-process facts persisted with the transaction/outbox; they do not imply event sourcing.

## Critical Flows

- **Create/scan batch:** a short transaction creates the batch; scan tasks persist cursor and registration chunks. Dispatch uses a transactional outbox so a commit and job intent cannot diverge.
- **Process image:** claim a pending run atomically, read by storage key, produce temporary artifacts, finalize files, then commit artifact descriptors and the successful state. Orphans are reconciled.
- **Review:** lock/select the current candidate, record an immutable decision, and transition the image in one transaction.
- **Export:** reserve a destination, copy to a temporary sibling, verify checksum, atomically rename, then record completion. See [storage design](storage-design.md).

## Scaling Seams

- Stateless API instances share PostgreSQL and Redis.
- Queue routing separates CPU, optional GPU, scan/maintenance, and export workloads.
- Worker concurrency is configuration, not domain behavior.
- `StorageBackend` capabilities support local disk first, then shared NAS and a future S3-compatible adapter.
- Engine Strategy interfaces permit model replacement while preserving run/candidate records.
- Transactional outbox dispatch and idempotent consumers permit additional processes without microservice decomposition.

These are seams, not a commitment to distributed deployment. A shared filesystem with consistent logical keys is required before adding worker hosts.

## Failure Handling

| Failure | Required behavior |
|---|---|
| Browser closes | No effect on durable work; client reconnects and queries state |
| API restarts | In-flight DB transactions roll back; outbox dispatcher resumes |
| Worker dies | Lease becomes stale; reconciliation retries within policy using the same run identity or creates an explicit retry run |
| Redis is lost | Rebuild dispatch from PostgreSQL outbox/pending records; no business truth is inferred from Celery results |
| Drive disconnects | Stop reads/writes, mark operations blocked/retryable, retain cursor and state, never convert to semantic failure automatically |
| Database unavailable | Fail closed; do not process unrecorded work or finalize an untraceable export |
| Artifact write succeeds before DB commit | Reconciler identifies temporary/orphan artifact by operation ID and safely deletes or adopts only after verification |
| Model missing/corrupt | Reject dispatch to that engine, record configuration failure, and require verified installation |

## Technology Risks and Alternatives

- BiRefNet hardware demand and Windows/PyTorch compatibility require an early spike. The Strategy contract permits fallback or a later validated engine.
- Celery Windows worker support is operationally weaker than Linux. Run workers in Linux containers/WSL2 under the supported Windows deployment and test shutdown semantics.
- External USB filesystems vary in atomicity, permissions, case behavior, and disconnect handling. Capability probes and recovery tests are release gates.
- Docker Desktop licensing/availability may affect a site. A documented native-service deployment can be evaluated later without changing architecture.

## Authoritative References

Domain ownership: [domain model](domain-model.md). Transitions: [state machines](state-machines.md). Persistence: [database design](database-design.md). Queue semantics: [worker and queue design](worker-and-queue-design.md). Security: [security](security.md).
