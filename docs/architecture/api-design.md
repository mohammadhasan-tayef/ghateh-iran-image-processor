# REST API Design

This document is authoritative for public REST resources and transport conventions. The API is rooted at `/api/v1`; JSON is UTF-8 `snake_case`, UUID strings, stable English enum/error codes, and ISO 8601 UTC timestamps. The `fa-IR` frontend maps error codes to Persian messages and renders timestamps in the user's configured timezone. Host/container absolute paths never cross the API.

## Session and Identity Endpoints

- `POST /session` — authenticate named local account, rotate a new server session/cookie, issue CSRF metadata; rate limited
- `DELETE /session` — revoke current session and clear cookie
- `GET /sessions` — list current user's active session summaries without tokens
- `DELETE /sessions` — logout/revoke all sessions for current user and advance session version
- `DELETE /sessions/{id}` — revoke one owned session; admin may revoke another user's session through an admin-scoped route
- `GET /me` — actor, fixed role, derived permissions, locale/timezone preferences
- `GET|POST /users`, `GET|PATCH /users/{id}` — admin user lifecycle; password reset/role/status change revokes sessions
- `GET /roles` — read-only fixed role/permission descriptions; no mutation endpoint

Browser authentication is PostgreSQL-backed server sessions with a random opaque cookie, not JWT. State-changing cookie-authenticated requests require CSRF proof. Session token rotation occurs after login and privilege changes; idle and absolute expiry are enforced server-side.

## Storage and Models

- `GET /storage-roots` — role-authorized aliases, enabled/health/capabilities/config key; never mount mappings
- `POST /storage-roots` — admin activates `{config_key, alias, enabled}` only; backend resolves a known server configuration entry
- `GET|PATCH /storage-roots/{id}` — label/enabled metadata; config key changes require validation
- `POST /storage-roots/{id}/verify` — probe mount and volume identity; explicit admin confirmation is required for identity change
- `GET /storage-roots/{id}/entries?relative_path=...&cursor=...` — bounded safe listing
- `POST /storage-roots/{id}/scan-preview` — bounded counts/sample
- `GET /models`, `GET /models/{id}`, `POST /models/{id}/verify` — registry/install health

Example activation request:

```json
{
  "config_key": "external_images",
  "alias": "هارد تصاویر قطعه ایران",
  "enabled": true
}
```

Folder selection continues to submit only `root_id` and `relative_path`. A missing mount returns root health `unavailable` and blocks scan/process/export with a typed retryable response. A changed Windows drive mapping is corrected in server configuration, never through a client path. A different volume identity blocks automatic resume pending admin verification.

## Presets, Batches, and Sources

- `GET /presets`, `GET /presets/{id}/revisions` — immutable revision representations
- `POST /presets`, `POST /presets/{id}/revisions` — admin-only validated parameters
- `POST /batches` — `{root_id, relative_path, preset_revision_id, name}`; response includes preset snapshot/SubjectMode summary
- `GET /batches`, `GET /batches/{id}` — pagination/detail with processing/review state plus derived approved/rejected/unresolved/failed/exported-at-least-once counts
- `POST /batches/{id}/scan`, `/pause-scan`, `/resume-scan`, `/cancel`
- `GET /batches/{id}/images` — cursor-paginated membership filters
- `GET /batch-images/{id}` — exact SourceObservation, processing state, versions, effective review, export-history summary
- `GET /source-observations/{id}` — authorized immutable observation/checksum/availability facts
- `POST /batch-images/{id}/reprocess`, `POST /batch-images/{id}/cancel`

Preset revision schema includes a required `subject_mode` and optional deterministic shadow fields: `shadow_enabled` (default false), `shadow_opacity`, `shadow_blur_ratio`, `shadow_offset_x`, `shadow_offset_y`, `shadow_color`, and `shadow_spread`. Server validation enforces bounded values and supported neutral colors; the ProcessingRun captures the validated snapshot.

## Candidates, Review, and Media

- `GET /candidates/{id}` — provenance, SubjectMode, shadow settings, QC/warnings, authorized media links
- `GET /review-queue` — cursor pagination and stable filters/sort; score may prioritize but never approve
- `POST /batch-images/{id}/review-decisions` — approve/reject/reprocess/revoke/select candidate with reason where required
- `POST /review-decisions/bulk` — explicit item/candidate pairs with per-item authorization/outcome
- `GET /media/source-previews/{source_observation_id}` — display derivative only
- `GET /media/candidates/{id}/image|mask|preview` — authorized candidate artifacts

Review uses SourcePreviewArtifact by default instead of repeatedly streaming full-resolution originals. The preview exposes no path and contains only EXIF orientation normalization plus display resize. Direct original bytes are disabled by default and require a separate permission/policy route if later needed.

The primary UI is Persian RTL. Technical values receive explicit LTR rendering. Review hotkeys are action-based and independent of direction. Unicode filenames in `Content-Disposition` use safe RFC-compatible encoding plus sanitized fallback.

## Exports and Operations

- `POST /export-jobs` — `{items, storage_root_id, naming_policy_schema_version, naming_policy_snapshot}`; every item names a BatchImage/candidate pair
- `GET /export-jobs`, `GET /export-jobs/{id}`, `GET /export-jobs/{id}/items`
- `POST /export-jobs/{id}/cancel`, `/retry-failed`
- `GET /batch-images/{id}/exports` — independent history; does not alter image state
- `GET /events`, `GET /health/live`, `GET /health/ready`

The naming snapshot validates source/SKU mode, sanitization, Unicode behavior, collision, suffix/`.png`, maximum filename length, grouping, case, and duplicate-output behavior. It becomes immutable once the job starts. Creating a job revalidates that every candidate belongs to and is currently human-approved for the supplied BatchImage. One approved candidate may appear in multiple jobs.

## Commands, Idempotency, and Concurrency

Creation returns `201`; accepted asynchronous commands return `202` with the authoritative resource. Mutations include `Idempotency-Key` and state-sensitive commands use `If-Match`. The same key/request hash returns the prior resource; reused key with different content is `409`. Candidate/export concurrency is governed by database locks and composite constraints, not client sequencing.

Clients poll resources with backoff in MVP; optional SSE may provide hints but PostgreSQL queries remain authoritative. Batch review completion never waits for exports.

## Pagination and Errors

Large collections use opaque cursors: `?limit=50&cursor=...` with `{items, next_cursor, has_more}`. Cursors bind to sort/filter and include UUID tie-breakers. Allowlisted filters include state, batch, warning, date, engine, reviewer, and export job.

```json
{
  "error": {
    "code": "state_conflict",
    "message": "The resource is not valid for this operation.",
    "details": {"current_state": "processing"},
    "correlation_id": "UUID"
  }
}
```

Codes stay English and stable; `message` is not the primary localized UI copy. Use `400`, `401`, `403`, `404`, `409`, `413`, `415`, `422`, `429`, `503`, and `500` consistently. Errors never disclose mount paths, token/CSRF data, stack traces, or sensitive filename metadata.

## API Security

The opaque session cookie is `HttpOnly`, production `Secure`, and uses the reviewed SameSite policy; CSRF protects state changes. CORS is an exact origin allowlist. Fixed-role permission checks run in application use cases. Rate limits cover login, session operations, scans, model verification, bulk review, and export. See [security](security.md).
