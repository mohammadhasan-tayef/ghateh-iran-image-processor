# State Machines

Derived from the authoritative [state-machine specification](../architecture/state-machines.md). Batch/BatchImage processing-review lifecycles are independent from export.

## Batch

```mermaid
stateDiagram-v2
    [*] --> created
    created --> scanning
    created --> cancelled
    scanning --> scan_paused
    scan_paused --> scanning
    scan_paused --> cancelled
    scanning --> queued
    scanning --> review_completed: zero members
    scanning --> failed
    scanning --> cancelled
    queued --> processing
    queued --> cancelled
    processing --> awaiting_review
    processing --> review_completed: all resolved; no failures/cancelled
    processing --> partially_completed: resolved with failures/cancelled
    processing --> failed: batch-level failure
    processing --> cancelled
    awaiting_review --> processing: reprocess
    awaiting_review --> review_completed
    awaiting_review --> partially_completed
    awaiting_review --> cancelled
```

## BatchImage

```mermaid
stateDiagram-v2
    [*] --> discovered
    discovered --> registered
    discovered --> processing_failed
    discovered --> cancelled
    registered --> queued
    registered --> cancelled
    queued --> processing
    queued --> processing_failed
    queued --> cancelled
    processing --> queued: transient recovery
    processing --> candidate_ready
    processing --> processing_failed
    processing --> cancelled
    candidate_ready --> needs_review
    needs_review --> human_approved
    needs_review --> rejected
    needs_review --> reprocess_queued
    rejected --> reprocess_queued
    human_approved --> reprocess_queued
    processing_failed --> reprocess_queued
    reprocess_queued --> processing
    reprocess_queued --> cancelled
```

## ProcessingRun

```mermaid
stateDiagram-v2
    [*] --> pending
    pending --> running
    pending --> cancelled
    running --> pending: stale lease recovery
    running --> succeeded
    running --> failed
    running --> cancelled
```

## ExportJob

```mermaid
stateDiagram-v2
    [*] --> pending
    pending --> running: freeze naming snapshot
    pending --> cancelled
    running --> completed
    running --> partially_completed
    running --> failed
    running --> cancelled
```

## ExportItem

```mermaid
stateDiagram-v2
    [*] --> pending
    pending --> running
    pending --> skipped
    pending --> cancelled
    running --> pending: retry after reconciliation
    running --> completed
    running --> failed
    running --> cancelled
```
