# Database Design

This document is authoritative for the proposed PostgreSQL schema, relational constraints, indexes, JSONB, retention, and audit storage. Physical names use `snake_case`; UUID primary keys are application- or database-generated UUIDv7 where support is validated, otherwise UUIDv4. All mutable rows include `created_at`, `updated_at`, and integer `row_version` where optimistic concurrency is useful.

## Tables

| Table | Selected typed fields and relationships |
|---|---|
| `users` | id, username CITEXT unique, display_name, credential_hash/reference, status, last_login_at |
| `roles` | id, name unique, description |
| `user_roles` | user_id, role_id; composite PK |
| `storage_roots` | id, alias unique, backend_type, config_ref, enabled, volume_identity, health_status, capabilities JSONB |
| `presets` | id, name unique, description |
| `preset_revisions` | id, preset_id, revision, schema_version, parameters JSONB, created_by; unique(preset_id, revision) |
| `batches` | id, storage_root_id, name, source_prefix, source_prefix_normalized, preset_revision_id, state, scan_cursor JSONB, counts, requested_by |
| `image_assets` | id, storage_root_id, source_key/display_key, normalized_source_key, observed_version, sha256, bytes, media_type, width, height, observed_metadata JSONB |
| `batch_images` | id, batch_id, image_asset_id, ordinal, state, selected_candidate_id nullable, row_version |
| `processing_runs` | id, batch_image_id, retry_of_run_id, attempt_no, state, idempotency_key, preset_revision_id, engine/model refs, lease token/expiry, timings, error_code/details JSONB |
| `candidate_versions` | id, processing_run_id unique, batch_image_id, version_no, image/mask/preview keys, checksums/sizes, qc_schema_version, qc_data JSONB |
| `review_decisions` | id, batch_image_id, candidate_version_id, actor_id, decision, reason_code/text, supersedes_id, correlation_id, created_at |
| `export_jobs` | id, storage_root_id, batch_id nullable, state, naming_policy_revision, requested_by, counts |
| `export_items` | id, export_job_id, batch_image_id, candidate_version_id, destination_key, normalized_destination_key, state, checksum, lease data, error fields |
| `model_registry_entries` | id, engine, name, version, expected_sha256, source/license metadata, requirements JSONB; unique(engine,name,version) |
| `model_installations` | id, registry_entry_id, installation_ref, actual_sha256, status, verified_at, capabilities JSONB |
| `processing_events` | id, occurred_at, subject_type, subject_id, event_type, actor_id nullable, task_id nullable, correlation_id, schema_version, payload JSONB |
| `outbox_messages` | id, topic, aggregate_type/id, payload JSONB, available_at, attempts, claimed_until, published_at |
| `idempotency_records` | id, actor_id, command_type, key, request_hash, resource_type/id, status, expires_at |

State columns use PostgreSQL enums only if migration ergonomics are accepted in Sprint 1; constrained text is a valid alternative. The state names and transitions remain owned by [state machines](state-machines.md).

## Constraints and Uniqueness

- `image_assets`: unique `(storage_root_id, normalized_source_key, observed_version)`; `sha256` is exactly 32 bytes (or 64 lowercase hex by a single consistent choice) and bytes are nonnegative.
- `batch_images`: unique `(batch_id, image_asset_id)` and `(batch_id, ordinal)`.
- `processing_runs`: unique `idempotency_key`; unique `(batch_image_id, attempt_no)`.
- `candidate_versions`: unique `(batch_image_id, version_no)`; selected candidate FK is deferrable or enforced through command ordering and must belong to the membership.
- `review_decisions`: reason required for reject/reprocess/revoke; candidate must belong to the membership (enforced in the use case and preferably a composite FK/schema design).
- `export_items`: unique `(storage_root_id via job, normalized_destination_key)` requires denormalization or a reservation table; exact implementation is selected in migration design. One candidate can appear in multiple explicitly requested exports.
- `idempotency_records`: unique `(actor_id, command_type, key)`.

CHECK constraints cover sizes/dimensions, timestamps, counters, required fields by state, and supported subject/decision types. Deletion defaults to restrict, not cascade, for audit-bearing data.

## Indexes

- Batch operations: `(state, created_at, id)`, `(storage_root_id, created_at)`.
- Scan/member work: `batch_images(batch_id, state, ordinal, id)` and partial indexes for queued/review/export states.
- Worker claims: partial `processing_runs(state, available_at, id)` plus `(lease_expires_at)` for running rows.
- Review queue: `(state, updated_at, id)` with selective indexes for batch/warning routing; QC JSONB is not generically GIN-indexed until a real query requires it.
- Exports: `export_items(export_job_id, state, id)` and partial lease/destination indexes.
- Events: `(subject_type, subject_id, occurred_at, id)`, `(correlation_id)`, and time partitioning only after measured volume warrants it.
- Outbox: partial `(available_at, id) WHERE published_at IS NULL`.

## JSONB Rules

JSONB is appropriate for versioned preset parameters, bounded scan cursors, engine/model capabilities, QC measurement vectors/warnings, error context, selected EXIF metadata, event payloads, and outbox payloads. Each has a schema version and application validation. Relationships, workflow state, ownership, checksums, logical keys, idempotency, searchable routing facts, and core timestamps remain columns.

## Transaction and Locking Notes

Use short transactions. Scan ingestion upserts bounded chunks. Work claiming uses `FOR UPDATE SKIP LOCKED` or a conditional update with lease token. Review locks one membership and validates the candidate. Filesystem operations occur outside long-held locks, with an operation reservation before I/O and conditional completion afterward. The Unit of Work writes domain changes and outbox messages atomically.

## Retention, Backup, and Audit

Users, decisions, exported candidate provenance, source/checksum records, model identities, and events needed to explain exports are retained for the operational/legal period, which is unresolved. Credentials may rotate while actor identity remains. Candidate rows are deleted only after artifact retention eligibility and reference checks; audit events are append-only to the application. Outbox and expired idempotency rows may be purged after safe windows.

PostgreSQL backups include schema and data, are encrypted/access-controlled, and are restore-tested. Files are backed up separately; reconciliation reports missing artifacts after restoration. No image bytes are stored in PostgreSQL.
