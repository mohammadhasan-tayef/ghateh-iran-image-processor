# Batch Processing Sequence

Derived from [system architecture](../architecture/system-architecture.md), [state machines](../architecture/state-machines.md), and [worker design](../architecture/worker-and-queue-design.md).

```mermaid
sequenceDiagram
    actor O as Operator
    participant UI as fa-IR RTL UI
    participant API as REST API
    participant DB as PostgreSQL
    participant Q as Redis/Celery
    participant S as Scan worker
    participant W as Image worker
    participant FS as StorageBackend

    O->>UI: Select root_id + relative_path + preset
    UI->>API: POST /batches (session + CSRF + key)
    API->>DB: Create Batch with preset/SubjectMode snapshot
    API-->>UI: 201 Batch(created)
    UI->>API: POST /batches/{id}/scan
    API->>DB: Batch scanning + outbox
    DB-->>Q: Publish bounded scan chunk
    Q->>S: Deliver batch/cursor operation
    loop Bounded entries
        S->>FS: List/stat by configured root logical key
        S->>DB: SourceObservation(discovered) + BatchImage(discovered)
        S->>FS: Stream SHA-256; re-stat exact source
        S->>DB: Observation hashed + BatchImage registered + outbox
    end
    S->>DB: Batch queued
    DB-->>Q: Publish bounded ProcessingRun ids
    Q->>W: Deliver run id
    W->>DB: Claim run with fencing lease
    W->>FS: Verify exact SourceObservation
    W->>W: SubjectMode pipeline + optional deterministic shadow + QC
    W->>FS: Atomic candidate artifacts
    W->>DB: Lock BatchImage; UUID candidate/version; candidate_ready
    W->>DB: Publish review item; needs_review
    Note over DB: Batch roll-up uses processing/review only
    UI->>API: GET paginated batch/review metrics
    API->>DB: Query authoritative states + independent export counts
    API-->>UI: Current resources
```
