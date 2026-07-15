# Review Sequence

Derived from [state machines](../architecture/state-machines.md) and [ADR 0007](../adr/0007-human-review-before-final-export.md).

```mermaid
sequenceDiagram
    actor R as Reviewer
    participant UI as Review UI
    participant API as REST API
    participant DB as PostgreSQL
    participant Media as Authorized media service
    participant Q as Redis/Celery

    R->>UI: Open next review item
    UI->>API: GET /review-queue?cursor=...
    API->>DB: Query needs_review page
    API-->>UI: Source/candidate IDs, QC, warnings
    UI->>Media: Request source, candidate, optional mask
    Media->>DB: Authorize referenced resources
    Media-->>UI: Stream safe media
    alt Approve
        R->>UI: Approve candidate
        UI->>API: POST review decision (candidate, ETag, key)
        API->>DB: Lock membership; decision + selected candidate
        API-->>UI: human_approved
    else Reject
        R->>UI: Reject with reason
        UI->>API: POST review decision
        API->>DB: Record immutable rejection
        API-->>UI: rejected
    else Reprocess
        R->>UI: Choose preset/engine and reason
        UI->>API: POST review decision
        API->>DB: Decision + new pending run + outbox
        DB-->>Q: Publish new run intent
        API-->>UI: reprocess_queued
    end
```
