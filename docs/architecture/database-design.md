# Database Design

This document is authoritative for the proposed PostgreSQL 17 schema, relational constraints, indexes, JSONB, retention, and audit storage. Physical names use `snake_case`; entity identities are UUIDs. Persist UTC timestamps. Mutable rows include `updated_at` and `row_version` where optimistic concurrency is useful.

## Identity and Session Tables

| Table | Selected fields and relationships |
|---|---|
| `users` | id, username CITEXT unique, display_name, role constrained to admin/operator/reviewer/auditor, password_hash, status, session_version, last_login_at, timestamps |
| `user_sessions` | id, user_id FK, token_hash unique, csrf_secret_hash/equivalent, created_at, last_seen_at, idle_expires_at, absolute_expires_at, revoked_at nullable, session_version, client_metadata JSONB, created_ip_hash nullable, user_agent_summary nullable |

The MVP has no `roles`, `permissions`, `user_roles`, or editable authorization tables. Fixed permission mapping lives in application code. Root-level user grants are deferred; if later required, add a deliberately scoped `user_storage_root_access(user_id, storage_root_id, access_level)` through a new decision/migration.

Session lookup indexes token hash; active-session queries index `(user_id, revoked_at, absolute_expires_at)`. Token and CSRF secrets are never stored plaintext. A session is valid only if not revoked/expired and its `session_version` equals the User value.

## Storage, Source, and Processing Tables

| Table | Selected fields and relationships |
|---|---|
| `storage_roots` | id, config_key unique, alias unique, backend_type, mode, enabled, expected_volume_identity, observed_volume_identity, health_status, capabilities JSONB, timestamps |
| `image_assets` | id, storage_root_id, normalized_logical_key, display_logical_key, timestamps; unique(root,key) |
| `source_observations` | id, image_asset_id, storage_root_id, logical/display source key, observed_size_bytes, observed_mtime_ns, observed_file_identity nullable, content_sha256 nullable, discovered_at, hash_completed_at nullable, availability_status |
| `source_preview_artifacts` | id, source_observation_id, generation_version, storage_key, sha256, bytes, width, height, mime_type, created_at |
| `presets` | id, name unique, description |
| `preset_revisions` | id, preset_id, revision, schema_version, parameters JSONB, created_by, created_at; unique(preset_id, revision) |
| `batches` | id, storage_root_id, name, source prefix, preset revision/snapshot, state, scan cursor/counts, review_cycle integer default 1, reopened_at nullable, reopened_by_user_id nullable FK, reopen_reason text/JSONB nullable, requested_by, created_at, updated_at |
| `batch_images` | id, batch_id, source_observation_id, ordinal, state, selected_candidate_id nullable, row_version, timestamps |
| `processing_runs` | id, batch_image_id, source_observation_id, retry_of_run_id, attempt_no, review_cycle, state, idempotency_key, preset revision/snapshot, subject_mode, engine/model refs, lease token/expiry, timings, error details |
| `candidate_versions` | id UUID, processing_run_id, batch_image_id, output_index, version_no, image/mask keys/checksums/sizes, media properties, QC schema/data JSONB, created_at |
| `review_decisions` | id, batch_image_id, candidate_version_id, actor_id, review_cycle, decision, reason code/text, supersedes_id, correlation_id, created_at |

`preset_revisions.parameters` is schema-validated. It includes processing bounds and:

- `subject_mode`: one of `single_object`, `product_with_packaging`, `multi_component_product`, `keep_all_foreground_objects`, `manual_subject_review_required`;
- `shadow_enabled` (default false), `shadow_opacity`, `shadow_blur_ratio`, `shadow_offset_x`, `shadow_offset_y`, `shadow_color`, and `shadow_spread`.

The Batch and ProcessingRun snapshots preserve the exact validated values even if preset presentation metadata changes.

## Export, Model, and Operations Tables

| Table | Selected fields and relationships |
|---|---|
| `export_jobs` | id, storage_root_id, batch_id nullable, state, naming_policy_schema_version, naming_policy_snapshot JSONB, requested_by, counts, started_at nullable, timestamps |
| `export_items` | id, export_job_id, batch_image_id, candidate_version_id, destination key/normalized key, state, checksum/media facts, lease data, error fields, timestamps |
| `model_registry_entries` | id, engine/name/version, expected SHA-256, source/license metadata, requirements JSONB; unique(engine,name,version) |
| `model_installations` | id, registry id, installation ref, actual SHA-256, status, verified at, capabilities JSONB |
| `processing_events` | id, occurred_at, subject type/id, event type, actor/task/correlation, review_cycle nullable, schema version, payload JSONB |
| `outbox_messages` | id, topic, aggregate type/id, payload JSONB, available_at, attempts, claimed_until, published_at |
| `idempotency_records` | id, actor_id, command type/key/request hash, resource type/id, status, expires_at |

`naming_policy_snapshot` is validated and includes source naming mode, SKU mode, filename sanitization, Unicode normalization/preservation behavior, collision strategy, suffix and `.png` extension policy, maximum filename length, directory grouping, filesystem case behavior, and duplicate-output behavior. It becomes immutable when the job starts.

## Source Identity and Duplicate Rules

- `image_assets` identify logical path lineage, not content equality.
- `source_observations` has preliminary uniqueness on `(storage_root_id, logical_source_key, observed_size_bytes, observed_mtime_ns)` with explicit handling for filesystems whose timestamp resolution is weak; this key avoids duplicate observations on scanner redelivery but does not prove content identity.
- Content SHA-256 (stored as exactly 32 bytes) is authoritative for duplicate content after streamed hashing. An index on `(content_sha256, observed_size_bytes)` supports duplicate lookup; null hashes remain pending.
- Changed content at the same path inserts a new SourceObservation. BatchImage has unique `(batch_id, source_observation_id)` and never retargets.
- Re-stat/file-identity checks guard the window around hashing. A changed file causes the preliminary observation to be abandoned/marked changed and a new observation discovered.

## Composite Integrity and Uniqueness

PostgreSQL constraints enforce same-BatchImage relationships:

```text
processing_runs:
  UNIQUE (id, batch_image_id)

candidate_versions:
  UNIQUE (id, batch_image_id)
  UNIQUE (processing_run_id, output_index)
  UNIQUE (batch_image_id, version_no)
  FOREIGN KEY (processing_run_id, batch_image_id)
    REFERENCES processing_runs (id, batch_image_id)

batch_images:
  FOREIGN KEY (selected_candidate_id, id)
    REFERENCES candidate_versions (id, batch_image_id)

review_decisions:
  FOREIGN KEY (candidate_version_id, batch_image_id)
    REFERENCES candidate_versions (id, batch_image_id)

export_items:
  FOREIGN KEY (candidate_version_id, batch_image_id)
    REFERENCES candidate_versions (id, batch_image_id)
```

The circular nullable selected-candidate FK is created deferrable or added after table creation; a candidate delete is restricted. Candidate-to-run composite FK proves the run belongs to the same BatchImage. ReviewDecision uses the same composite parent check. ExportItem uses it and transactionally verifies that the candidate is the effective human-approved selection for that BatchImage. Cross-parent selection/review/export references are rejected by PostgreSQL even if application validation is bypassed.

Other rules:

- `processing_runs`: unique idempotency key and `(batch_image_id, attempt_no)`.
- `batches`: CHECK `review_cycle >= 1`; reopen actor/time/reason must be jointly present when a closed cycle has been reopened.
- `source_preview_artifacts`: unique `(source_observation_id, generation_version)`; checksum exactly 32 bytes; positive dimensions.
- `export_items`: destination reservation uniqueness is enforced by a root/destination reservation design selected in migrations; denormalizing root id onto the item is acceptable to support `UNIQUE(storage_root_id, normalized_destination_key)`.
- `idempotency_records`: unique `(actor_id, command_type, key)`.
- State-dependent required values, nonnegative sizes/counts, expiry ordering, and supported fixed enum values use CHECK constraints or constrained text.

## Candidate Version Allocation

Do not use unprotected `MAX(version_no) + 1`. Finalization:

1. conditionally validates the run lease/idempotency;
2. obtains a short `FOR UPDATE` lock on BatchImage;
3. returns the existing candidate if this run/output slot already finalized;
4. reads the current highest version under that lock and selects the next display number (or uses a locked counter on BatchImage);
5. inserts CandidateVersion UUID, output index, and version number; completes the run/updates BatchImage after all expected outputs; emits outbox/event in one transaction.

Concurrent distinct runs serialize at the BatchImage lock. The unique constraint is the final guard. Transaction rollback may create gaps if a counter strategy is used; display sequences are gap-tolerant.

## Controlled Reopen Transaction

`ReprocessBatchImage` uses the API idempotency record and locks Batch before BatchImage to avoid deadlocks. It validates authorization, required storage, Batch/BatchImage eligibility, and absence of an equivalent outstanding request. If Batch is `review_completed` or `partially_completed`, it increments `review_cycle`, transitions Batch to `processing`, and sets reopen actor/time/reason. If Batch is already `processing`, it retains state/cycle; if `awaiting_review`, it transitions to `processing` while retaining the cycle. It then creates ProcessingRun with that cycle, moves BatchImage to `reprocess_queued`, clears the effective selected candidate for the new cycle, inserts `batch_reopened` when applicable plus `batch_image_reprocess_requested` ProcessingEvent/outbox facts carrying the cycle, and commits atomically.

The same idempotency key/request hash returns the original run/cycle. Concurrent requests for different images serialize on Batch; after the first reopen, later requests observe `processing` and cannot increment again. `cancelled`/`failed` Batches reject the normal command. CandidateVersion, ReviewDecision, and completed ExportJob rows are never updated or deleted by reopening.

## Indexes

- Sessions: token hash unique; `(user_id, revoked_at, absolute_expires_at)`.
- Batch work: `(state, created_at, id)`, `(storage_root_id, created_at)`, and `batch_images(batch_id, state, ordinal, id)`.
- Observations: `(storage_root_id, normalized logical key, discovered_at)`, `(content_sha256, observed_size_bytes)`, and availability/hash-pending partial indexes.
- Worker claims: partial processing-run state/availability and running lease-expiry indexes.
- Review: BatchImage `needs_review` index and decision indexes by subject/created time.
- Export: item `(export_job_id, state, id)`, lease, and root/destination uniqueness/reservation indexes. Export state is never indexed on BatchImage.
- Events/outbox: subject/correlation/time indexes and partial unpublished outbox index.
- QC/naming/preset JSONB receives only measured, targeted expression indexes; no generic GIN by default.

## JSONB and Retention

JSONB is restricted to schema-versioned variable documents: validated preset/naming snapshots, minimal session client metadata, cursors, capabilities, QC facts/warnings, bounded error/event context, and selected EXIF. Relationships, state, subject mode, role, logical keys, checksums, identity, session expiry/revocation, and routing remain columns.

Users, decisions, exported provenance/naming snapshots, source observations/checksums, models, and events needed to explain exports are retained for the approved operational/legal period. Session, rejected artifact, preview, and event retention durations remain open policy. Expired/revoked sessions, outbox, and idempotency rows may be purged only after safe/audited windows. PostgreSQL contains no image bytes.
