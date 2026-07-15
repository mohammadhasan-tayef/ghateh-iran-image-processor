# Entity Relationship Diagram

Derived from [domain model](../architecture/domain-model.md) and [database design](../architecture/database-design.md). `Role` is a fixed User value, not a table.

```mermaid
erDiagram
    USER ||--o{ USER_SESSION : owns
    USER ||--o{ REVIEW_DECISION : makes
    USER ||--o{ EXPORT_JOB : requests
    USER |o--o{ BATCH : reopens
    STORAGE_ROOT ||--o{ IMAGE_ASSET : catalogs
    STORAGE_ROOT ||--o{ SOURCE_OBSERVATION : observes
    STORAGE_ROOT ||--o{ BATCH : contains
    IMAGE_ASSET ||--o{ SOURCE_OBSERVATION : has
    SOURCE_OBSERVATION ||--o{ SOURCE_PREVIEW_ARTIFACT : previews
    PRESET ||--|{ PRESET_REVISION : versions
    PRESET_REVISION ||--o{ BATCH : configures
    BATCH ||--o{ BATCH_IMAGE : includes
    BATCH_IMAGE }o--|| SOURCE_OBSERVATION : uses_source
    BATCH_IMAGE ||--o{ PROCESSING_RUN : attempts
    PROCESSING_RUN ||--o{ CANDIDATE_VERSION : produces
    PRESET_REVISION ||--o{ PROCESSING_RUN : snapshots
    MODEL_REGISTRY_ENTRY ||--o{ MODEL_INSTALLATION : installed_as
    MODEL_INSTALLATION ||--o{ PROCESSING_RUN : executes
    BATCH_IMAGE ||--o{ CANDIDATE_VERSION : owns
    BATCH_IMAGE |o--o| CANDIDATE_VERSION : selects
    BATCH_IMAGE ||--o{ REVIEW_DECISION : records
    CANDIDATE_VERSION ||--o{ REVIEW_DECISION : receives
    EXPORT_JOB ||--o{ EXPORT_ITEM : contains
    BATCH_IMAGE ||--o{ EXPORT_ITEM : export_history
    EXPORT_ITEM }o--|| CANDIDATE_VERSION : exports
```

The ownership and selected-candidate relationships are intentionally separate. `batch_images.selected_candidate_id` must reference a CandidateVersion owned by that same BatchImage. ReviewDecision must reference a CandidateVersion belonging to its BatchImage. ExportItem must reference the exact human-approved selected CandidateVersion for its BatchImage. Mermaid cannot fully express those conditional same-parent rules, so PostgreSQL enforces them with the composite keys/FKs defined in [database design](../architecture/database-design.md), plus transactional approval validation.
