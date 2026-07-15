# Domain Model

This document is authoritative for entity meaning, aggregates, invariants, relationships, and business transaction boundaries. All identifiers are UUIDs; timestamps are UTC instants.

## Entities

| Entity | Purpose | Key fields |
|---|---|---|
| `User` | Authenticated actor | id, username, display name, status, credential metadata |
| `Role` | Named permission set | id, name, permissions |
| `StorageRoot` | Admin-approved storage boundary | id, alias, backend type, host mapping reference, capabilities, enabled |
| `Batch` | Ingestion and operational progress boundary | id, root id, source prefix, preset revision id, state, scan cursor, counts |
| `ImageAsset` | Immutable identity and metadata for one source file | id, root id, source key, SHA-256, bytes, format, dimensions, observed metadata |
| `BatchImage` | Membership of an asset in a batch | id, batch id, asset id, state, ordinal, selected candidate id |
| `ProcessingRun` | One execution attempt against one batch image | id, engine/model/preset revisions, state, idempotency key, timings, error |
| `CandidateVersion` | Immutable artifact produced by a successful run | id, run id, version number, image/mask/preview keys and checksums, QC facts |
| `Preset` / `PresetRevision` | Named policy and immutable processing parameters | id/name; revision id, schema version, parameters, active dates |
| `ReviewDecision` | Immutable human action on a candidate | id, batch image id, candidate id, actor id, decision, reason, timestamp |
| `ExportJob` / `ExportItem` | Requested export and per-image result | job id/state; item id, candidate id, destination key, checksum, state |
| `ProcessingEvent` | Append-only audit/diagnostic fact | id, subject type/id, event type, actor/task, correlation id, payload |
| `ModelRegistryEntry` / `ModelInstallation` | Desired model identity and verified local availability | engine/name/version/license/source checksum; installation path reference/status/device compatibility |

`ProcessingRun` and `CandidateVersion` are separate. A run records an attempt, including failure or cancellation; a candidate exists only when immutable artifacts were finalized. This preserves failed-attempt history and allows one selected candidate among multiple attempts.

## Relationships

- Users and roles are many-to-many.
- A storage root owns many assets and batches; root deletion is prohibited while referenced.
- A batch has many `BatchImage` memberships; an asset may appear in multiple batches.
- A batch image has many runs and candidate versions, at most one selected candidate, and many review decisions.
- A run targets exactly one batch image and references immutable preset, engine, and model revisions.
- A candidate belongs to exactly one successful run.
- An export item references exactly one human-approved candidate and one export job.
- Events reference subjects polymorphically through validated subject type/id fields; they do not replace relational state.

See the [ER diagram](../diagrams/entity-relationship.md).

## Aggregate Boundaries and Invariants

### Batch aggregate

Owns `Batch` and scan progress, not all memberships in memory. Invariants: source key is contained by the root; preset revision is fixed at creation; terminal batches cannot accept newly discovered members except via an explicit resume/reopen operation; durable counters are derived/reconciled, not blindly incremented.

### Batch image aggregate

Owns one `BatchImage`, its transition, selected candidate, and review eligibility. Invariants: selected candidate belongs to that membership; only a successful finalized candidate can be reviewed; export readiness requires a valid human approval for that selected candidate; rejection clears export eligibility but not history.

### Processing run aggregate

Owns run lifecycle and immutable candidate creation. One idempotency key identifies one intended attempt. A succeeded run has exactly one candidate; a failed/cancelled run has none. Candidate fields and artifacts never mutate after finalization.

### Export aggregate

Owns an export job and independently committed items. Every item references an approved selected candidate at reservation time. A destination key is reserved uniquely within its root. Partial completion is explicit.

### Storage root, identity, preset, and model aggregates

Configuration updates create audit records. Preset revisions and model identities referenced by runs are immutable. Storage mappings and secrets are configuration references and are never returned through public DTOs.

## Cross-Aggregate Consistency

Strong consistency is used for a command's decisive invariant: review plus selected candidate, run success plus candidate descriptor, and export destination reservation. Progress counters, batch roll-ups, event consumers, and dispatch are eventually consistent and repairable from authoritative rows.

An outbox row is written in the same transaction as a command that requires asynchronous follow-up. Consumers use unique idempotency keys. No domain invariant relies on a Redis result or filesystem directory listing alone.

## Transaction Boundaries

| Use case | Transaction |
|---|---|
| Create batch | Batch row, initial event, outbox intent |
| Register scan chunk | Asset upserts, membership inserts, cursor/checkpoint, events in a bounded chunk |
| Claim run | Conditional run state/lease update and event |
| Finish run | Verify finalized descriptor; create candidate; mark run succeeded; route membership; event/outbox |
| Review candidate | Lock membership; insert decision; select/clear candidate; transition; event/outbox |
| Create export | Job and item reservations in bounded chunks |
| Finish export item | Conditional item transition, checksum/final key, event; roll-up later |

Filesystem writes cannot share an ACID transaction with PostgreSQL. Operation IDs, temporary names, checksums, and reconciliation close that gap; see [storage design](storage-design.md).

## JSONB Policy

JSONB is allowed for versioned engine parameters, QC measurements/warnings, observed EXIF subsets, device capabilities, error details, and event context. Frequently queried identity, state, ownership, relationships, checksums, timestamps, and routing fields are typed columns. Every JSONB document has an application schema version and bounded size.
