# Review and Export Sequence

Derived from [state machines](../architecture/state-machines.md), [ADR 0007](../adr/0007-human-review-before-final-export.md), and [ADR 0010](../adr/0010-export-lifecycle-separated-from-image-lifecycle.md).

```mermaid
sequenceDiagram
    actor R as Reviewer
    actor A as Admin
    participant UI as fa-IR RTL Review UI
    participant API as REST API
    participant DB as PostgreSQL
    participant Media as Authorized media service
    participant Q as Redis/Celery

    R->>UI: Open next review item
    UI->>API: GET /review-queue?cursor=...
    API->>DB: Query needs_review page prioritized by QC
    API-->>UI: SourceObservation, candidate, warnings
    UI->>Media: Request SourcePreviewArtifact + candidate/mask
    Media->>DB: Authorize workflow resources
    Media-->>UI: Stream display-only media
    alt Approve
        R->>UI: Approve selected candidate
        UI->>API: POST decision (session + CSRF + ETag)
        API->>DB: Lock BatchImage; composite FK; decision + selection
        API-->>UI: BatchImage human_approved
    else Reject
        R->>UI: Reject with reason
        UI->>API: POST decision
        API->>DB: Immutable rejection
        API-->>UI: BatchImage rejected
    else Reprocess
        R->>UI: Select preset/engine + reason
        UI->>API: POST /batch-images/{id}/reprocess + idempotency key
        API->>DB: Lock Batch/Image; decision + run + reprocess_queued
        API->>DB: If closed: Batch processing + review_cycle increment once
        DB-->>Q: Publish run id
        API-->>UI: Batch/Image states + run id + review_cycle
    end

    Note over DB: Batch may reach review_completed before any export
    A->>API: POST /export-jobs with approved candidate + naming snapshot
    API->>DB: Validate human approval; create independent job/items
    DB-->>Q: Publish ExportItem ids
    Q-->>DB: Export worker records item/job outcome only
    Note over DB: Reopen preserves prior decisions/exports; new candidate needs new review
    Note over DB: BatchImage remains human_approved on export success or failure
```
