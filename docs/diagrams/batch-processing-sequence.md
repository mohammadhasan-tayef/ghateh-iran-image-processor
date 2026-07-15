# Batch Processing Sequence

Derived from [system architecture](../architecture/system-architecture.md), [state machines](../architecture/state-machines.md), and [worker design](../architecture/worker-and-queue-design.md).

```mermaid
sequenceDiagram
    actor O as Operator
    participant UI as Web UI
    participant API as REST API
    participant DB as PostgreSQL
    participant Q as Redis/Celery
    participant S as Scan worker
    participant W as Image worker
    participant FS as StorageBackend

    O->>UI: Choose root_id + relative_path + preset
    UI->>API: POST /batches (Idempotency-Key)
    API->>DB: Create batch + outbox
    API-->>UI: 201 batch(created)
    UI->>API: POST /batches/{id}/scan
    API->>DB: Transition scanning + outbox
    API-->>UI: 202 batch(scanning)
    DB-->>Q: Outbox dispatcher publishes scan chunk
    Q->>S: Deliver scan operation ID
    loop Bounded chunks
        S->>FS: Incremental list and streamed reads
        S->>DB: Upsert assets/memberships + cursor + outbox
    end
    S->>DB: Transition batch queued
    DB-->>Q: Publish bounded processing intents
    Q->>W: Deliver processing run ID
    W->>DB: Claim run with lease token
    W->>FS: Verify and read immutable original
    W->>W: Non-generative pipeline + QC
    W->>FS: Atomic candidate finalization
    W->>DB: Candidate + run succeeded + needs_review
    UI->>API: GET paginated batch/review state
    API->>DB: Query authoritative state
    API-->>UI: Current resources
```
