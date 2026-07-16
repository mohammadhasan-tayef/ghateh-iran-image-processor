# Domain Model

This document is authoritative for entity meaning, aggregate boundaries, invariants, relationships, and business transaction boundaries. Its aggregate and relationship descriptions are interpreted under [Core Domain Ownership Rules](core-domain-ownership-rules.md): aggregate grouping, relationship cardinality, persistence relationships, foreign-key direction, and storage location do not independently assign semantic/domain ownership. Explicit module ownership decisions remain authoritative for semantic/domain ownership. All entity identifiers are UUIDs and persisted timestamps are UTC.

## Identity and Authorization

| Entity/value | Purpose | Key fields |
|---|---|---|
| `User` | Named local actor | id, username, display name, fixed role, password hash, status, session version |
| `Role` | Fixed code-defined value, not a database-managed entity | `admin`, `operator`, `reviewer`, `auditor` |
| `UserSession` | Revocable server-side browser session | id, user id, token hash, CSRF hash/metadata, created/last-seen/idle/absolute expiry, revoked at, session version, minimal client metadata, optional created-IP hash and user-agent summary |

Permissions are fixed in application code and documented in [security](security.md). The MVP has no role/permission tables and no per-root user-access table. Root-level scoping is explicitly deferred.

## Storage, Source, and Ingestion

| Entity | Purpose | Key fields |
|---|---|---|
| `StorageRoot` | Admin activation of a server-configured mount | id, config key, alias, backend type, mode, volume identity, capabilities, health, enabled |
| `ImageAsset` | Stable catalog identity for one logical source lineage | id, storage root id, normalized/current display key, created at |
| `SourceObservation` | Immutable observation of source content at a path/time | id, asset/root ids, logical/display key, size, mtime ns, optional file identity, optional SHA-256, discovery/hash times, availability |
| `SourcePreviewArtifact` | Regenerable display derivative of an observation | id, source observation id, storage key/checksum, width/height, MIME type, generation version, created at |
| `Batch` | Ingestion, processing, and reopenable review-cycle boundary | id, root/source prefix, preset revision/snapshot, state, scan cursor, derived counts, review cycle, reopen metadata, updated at |
| `BatchImage` | Exact source-observation membership and review lifecycle | id, batch id, source observation id, state, ordinal, selected candidate id, row version |

Preliminary source sameness may use logical key plus size/mtime. Streamed SHA-256 is authoritative once available. Changed content at the same path creates a new SourceObservation; existing observations and BatchImage membership never retarget. Source preview generation applies only EXIF orientation normalization and display resize, is safely repeatable, and never replaces the source.

## Processing, Review, and Export

| Entity | Purpose | Key fields |
|---|---|---|
| `ProcessingRun` | One attempt against one BatchImage/source observation | id, batch image id, engine/model, preset snapshot including SubjectMode/shadow, state, idempotency, timings/error |
| `CandidateVersion` | Immutable artifact from a processing run | UUID id, run/batch-image ids, output index, human-readable version no, image/mask keys/checksums, QC/provenance |
| `Preset` / `PresetRevision` | Named policy and immutable validated parameters | id/name; revision id/number, schema version, parameters, created by/at |
| `SubjectMode` | Fixed subject-selection policy value | `single_object`, `product_with_packaging`, `multi_component_product`, `keep_all_foreground_objects`, or `manual_subject_review_required` |
| `ReviewDecision` | Immutable human action on a candidate | id, batch image/candidate/actor ids, decision, reason, supersession, timestamp |
| `ExportJob` | Independent export request and immutable naming policy | id, root/batch optional, state, naming schema version/snapshot, requested by, counts |
| `ExportItem` | Per-candidate result inside one export job | id, job/batch-image/candidate ids, destination key/checksum, state, lease/error |
| `ProcessingEvent` | Append-only audit/diagnostic fact | id, subject, type, actor/task, correlation id, review cycle, schema/payload |
| `ModelRegistryEntry` / `ModelInstallation` | Desired model and verified local installation | model identity/license/checksum; installation ref/status/device capabilities |

`ProcessingRun` and `CandidateVersion` remain separate: failed/cancelled attempts may produce no candidate; a successful run produces one or more immutable candidates when a pipeline intentionally emits alternatives (the MVP normally emits one). Candidate UUID is identity. `output_index` identifies an idempotent output slot within a run, while `version_no` is display ordering scoped to BatchImage and is allocated under a short BatchImage row lock during finalization.

## Relationships

- A User has one fixed MVP role and many UserSessions; password reset/privilege change revokes or invalidates all sessions through `session_version`.
- A StorageRoot is resolved by server `config_key` and provides the configured source context for related ImageAssets, SourceObservations, Batches, previews, and artifacts. This relationship and its cardinality do not assign SourceObservation semantic/domain ownership; SourceObservation remains owned by Assets.
- An ImageAsset has many SourceObservations over time. A BatchImage references exactly one SourceObservation, and an observation may appear in multiple batches.
- A Batch has many BatchImages, snapshots one immutable preset revision including SubjectMode, and starts with `review_cycle = 1`.
- A BatchImage owns many ProcessingRuns, CandidateVersions, and ReviewDecisions and selects zero or one CandidateVersion from itself as the effective current selection.
- A ProcessingRun targets one BatchImage and its exact observation; it snapshots preset/engine/model inputs.
- A ProcessingRun produces zero or more CandidateVersions; failed/cancelled attempts normally produce zero and the MVP successful path normally produces one.
- A SourceObservation may have multiple preview generations but at most one active preview per generation version.
- An ExportJob has many ExportItems. Each item references one human-approved CandidateVersion belonging to the referenced BatchImage.
- One approved candidate may participate in any number of independent ExportJobs without changing BatchImage state.

See the [ER diagram](../diagrams/entity-relationship.md).

## Aggregate Boundaries and Invariants

### User aggregate

Owns User and session invalidation version. Username is unique. Role is one approved fixed value. Disabled users cannot authenticate. Session token/CSRF values are stored only as hashes; idle and absolute expiry are enforced server-side.

### Storage/source aggregate

This existing aggregate description records entity relationships and invariants without assigning SourceObservation to Storage catalog or deciding final aggregate-root status. SourceObservation semantic/domain ownership remains exclusively with Assets, whose authority controls its accepted meaning and invariants; StorageRoot operational or relational participation does not create co-ownership.

StorageRoot references a server-known config key, never a client path. SourceObservation is immutable after hash completion except availability facts. Current availability is an operational fact supplied through Storage catalog responsibilities; it does not redefine accepted SourceObservation identity or provenance and does not transfer semantic/domain ownership. A changed source creates a new observation. Preview artifacts are derived, independently replaceable by generation version, and cannot be treated as originals.

### Batch aggregate

Owns Batch scan progress and review-cycle closure, not all members in memory. When all non-cancelled members are review-resolved, Batch becomes `review_completed` if none failed/cancelled, otherwise `partially_completed`. These are closed-cycle states. They may reopen to `processing` only through `ReprocessBatchImage`; `cancelled` and `failed` remain permanently terminal for normal commands. Rejection is a valid review resolution, not a failure. Durable counters are derived/reconciled.

`review_cycle` starts at 1. Reopening a closed cycle increments it once and records `reopened_at`, `reopened_by_user_id`, and `reopen_reason`. A reprocess request while Batch is already `processing` joins that cycle without transition/increment; while `awaiting_review`, it moves Batch to `processing` without increment. Batch row locking makes concurrent reopen requests increment once. ProcessingRun, ReviewDecision, and ProcessingEvent metadata include the current cycle. Prior candidates/decisions and export history remain immutable.

### BatchImage aggregate

Owns ingestion/processing/review state and selected candidate only. Core invariants:

- membership stays bound to one SourceObservation;
- selected candidate belongs to this BatchImage;
- only a finalized candidate may be reviewed;
- human approval selects a candidate from this BatchImage;
- processing/export errors are distinct: export never moves BatchImage to `processing_failed`;
- no export state exists in BatchImage.

### ProcessingRun/Candidate finalization

One run idempotency key identifies one intended attempt in one Batch review cycle. Candidate finalization locks BatchImage briefly, checks whether the run/output slot already has a candidate, allocates `next version_no` inside the transaction, inserts the UUID candidate, completes the run when all expected outputs finalize, and transitions the BatchImage. Concurrent reprocessing attempts may run, but each finalizer serializes allocation; late/stale lease or review-cycle completion is rejected. Gaps in version numbers are acceptable; collisions are not.

### Export aggregate

ExportJob owns independent item states and a `naming_policy_schema_version` plus immutable `naming_policy_snapshot` after transition from pending. The snapshot covers source/SKU naming, sanitization, Unicode, collisions, suffix/extension, maximum length, grouping, case, and duplicate outputs. Every item snapshots an approved candidate and destination reservation. Export success/failure never mutates BatchImage review state.

## Relational Invariants

Core same-parent relationships are enforced in PostgreSQL, not only application code:

- CandidateVersion has `UNIQUE (id, batch_image_id)`, `UNIQUE (processing_run_id, output_index)`, and `UNIQUE (batch_image_id, version_no)`.
- ProcessingRun exposes `UNIQUE (id, batch_image_id)`.
- CandidateVersion `(processing_run_id, batch_image_id)` references ProcessingRun `(id, batch_image_id)`.
- BatchImage `(selected_candidate_id, id)` references CandidateVersion `(id, batch_image_id)` with a nullable selected id.
- ReviewDecision `(candidate_version_id, batch_image_id)` references CandidateVersion `(id, batch_image_id)`.
- ExportItem `(candidate_version_id, batch_image_id)` references CandidateVersion `(id, batch_image_id)`.

These constraints mean `selected_candidate_id` can reference only a candidate owned by the same BatchImage, and ReviewDecision can reference only a same-parent candidate. ExportItem has the same parent constraint and must reference the effective approved selected candidate for that BatchImage; approval eligibility is additionally enforced transactionally because a relational FK alone cannot express the latest valid human decision.

## Transaction Boundaries

| Use case | Transaction |
|---|---|
| Authenticate/rotate/logout | Verify user; create/revoke UserSession; audit; update session version when global invalidation is required |
| Activate root | Validate server config key; create/update root metadata and event; no client path persisted |
| Register scan chunk | Upsert assets, insert immutable observations/memberships, checkpoint cursor, events/outbox in a bounded chunk |
| Finish hash | Conditional observation SHA-256/hash time update after re-stat identity check |
| Reprocess BatchImage | Lock Batch then BatchImage; validate actor/root/states/idempotency; if Batch is closed increment cycle and reopen; create run in current cycle; move image to reprocess_queued; clear effective selection; event/outbox; one atomic commit |
| Finish processing run | Lock BatchImage; idempotency/lease check; allocate version; candidate/run/BatchImage/event/outbox commit |
| Review candidate | Lock BatchImage; insert decision; select/clear candidate; transition; audit/outbox |
| Create export | Job with naming snapshot plus item reservations in bounded chunks; BatchImage unchanged |
| Finish export item | Conditional item state, checksum/key/event; job roll-up later; BatchImage unchanged |

Filesystem operations cannot join a PostgreSQL transaction. Operation IDs, temporary names, hashes, conditional finalization, and reconciliation close that gap; see [storage design](storage-design.md).

## JSONB Policy

JSONB is allowed for validated preset snapshots, naming-policy snapshots, minimal session client metadata, QC facts/warnings, observed EXIF subsets, capabilities, scan cursors, structured reopen reasons, error details, and event context. SubjectMode, review cycle, role, identity/state, ownership, relationships, checksums, timestamps, routing fields, and expiry fields are typed columns. Every JSONB document is schema-versioned and size-bounded.
