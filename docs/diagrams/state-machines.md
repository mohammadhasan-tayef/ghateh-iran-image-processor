# State Machines

Derived from the authoritative [state-machine specification](../architecture/state-machines.md). Terminal and exceptional details remain in that document.

## Batch

```mermaid
stateDiagram-v2
    [*] --> created
    created --> scanning
    created --> cancelled
    scanning --> scan_paused
    scan_paused --> scanning
    scanning --> queued
    scanning --> completed: accepted empty
    scanning --> failed
    scanning --> cancelled
    queued --> processing
    queued --> cancelled
    processing --> awaiting_review
    processing --> partially_completed
    processing --> failed
    processing --> cancelled
    awaiting_review --> processing: reprocess
    awaiting_review --> completed
    awaiting_review --> partially_completed
```

## Image Membership

```mermaid
stateDiagram-v2
    [*] --> registered
    registered --> queued
    registered --> cancelled
    queued --> processing
    queued --> failed
    queued --> cancelled
    processing --> needs_review
    processing --> queued: transient retry
    processing --> failed
    processing --> cancelled
    needs_review --> human_approved
    needs_review --> rejected
    needs_review --> reprocess_queued
    rejected --> reprocess_queued
    human_approved --> export_ready
    human_approved --> reprocess_queued
    reprocess_queued --> processing
    reprocess_queued --> cancelled
    export_ready --> exported
    export_ready --> human_approved: release reservation
    export_ready --> failed
    failed --> reprocess_queued: explicit retry
```

## Processing Run

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

## Export Job

```mermaid
stateDiagram-v2
    [*] --> pending
    pending --> running
    pending --> cancelled
    running --> completed
    running --> partially_completed
    running --> failed
    running --> cancelled
```
