# REST API Design

This document is authoritative for public REST resources and transport conventions. The API is rooted at `/api/v1`; JSON uses UTF-8, `snake_case`, ISO 8601 UTC timestamps, UUID strings, and explicit enum values. Host absolute paths never appear in requests, responses, logs intended for users, or media URLs.

## Resources and Endpoints

### Session and identity

- `POST /session` — authenticate; rate limited
- `DELETE /session` — sign out/revoke current session
- `GET /me` — actor, roles, permissions
- `GET|POST /users`, `GET|PATCH /users/{id}` — admin lifecycle
- `GET /roles` — role catalog

### Storage and models

- `GET /storage-roots` — authorized aliases, availability, capabilities; never mappings
- `POST /storage-roots` — admin creates a root referencing server-side configuration
- `GET|PATCH /storage-roots/{id}` — status/configuration metadata
- `GET /storage-roots/{id}/entries?relative_path=...&cursor=...` — bounded directory listing
- `POST /storage-roots/{id}/scan-preview` — bounded counts/sample, not full ingestion
- `GET /models`, `GET /models/{id}` — registry/install health
- `POST /models/{id}/verify` — admin verification command

### Batches and images

- `POST /batches` — `{root_id, relative_path, preset_revision_id, name}`
- `GET /batches`, `GET /batches/{id}` — paginated list/detail
- `POST /batches/{id}/scan`, `/pause-scan`, `/resume-scan`, `/cancel`
- `GET /batches/{id}/images` — cursor-paginated memberships with filters
- `GET /batch-images/{id}` — source metadata, state, versions, effective review
- `POST /batch-images/{id}/reprocess` — engine/preset selection and reason
- `POST /batch-images/{id}/cancel`

### Candidates and review

- `GET /candidates/{id}` — provenance, QC, warnings, authorized media links
- `GET /review-queue` — cursor pagination and stable filters/sort
- `POST /batch-images/{id}/review-decisions` — approve/reject/reprocess/revoke with candidate and reason
- `POST /review-decisions/bulk` — explicit item/candidate pairs; returns per-item outcome

### Exports and operations

- `POST /export-jobs` — selected batch images/candidates and naming policy revision
- `GET /export-jobs`, `GET /export-jobs/{id}`
- `POST /export-jobs/{id}/cancel`, `/retry-failed`
- `GET /events` — authorized audit query
- `GET /health/live`, `GET /health/ready` — process and dependency health

## Commands, Responses, and Concurrency

Creation returns `201`; asynchronous commands return `202` with the authoritative resource and an operation link; successful idempotent repeats return the existing resource. Mutation requests include `Idempotency-Key` and, for state-sensitive operations, `If-Match` with a version/ETag. Server-side UUIDs are used unless a specific client command id is accepted.

Command responses do not promise task completion. Clients poll resources using backoff in MVP; optional Server-Sent Events may later deliver hints, with PostgreSQL-backed queries remaining authoritative.

## Pagination and Filtering

Large collections use opaque cursor pagination: `?limit=50&cursor=...`, response `{items, next_cursor, has_more}`. Limits are capped. Cursors bind to canonical sort/filter and include a tie-breaker UUID. Offset pagination is reserved for small administrative catalogs. Filters use allowlisted fields such as state, batch, warnings, date range, engine, and assignee.

## Error Envelope

```json
{
  "error": {
    "code": "state_conflict",
    "message": "The image is not reviewable in its current state.",
    "details": {"current_state": "processing"},
    "correlation_id": "UUID"
  }
}
```

Codes are stable and messages avoid host paths/secrets. Use `400` malformed semantics, `401` unauthenticated, `403` unauthorized, `404` absent/concealed, `409` state/idempotency/destination conflict, `413` upload/size limit, `415` unsupported media, `422` field validation, `429` throttling, `503` dependency/root unavailable, and `500` unexpected failure.

## Idempotency

The server stores actor, route/command type, key, canonical request hash, status, and response reference in PostgreSQL. The same key and hash returns the prior result; the same key with different content is `409`. Keys have a retention period longer than maximum command retry windows. Worker idempotency is separately defined in [worker and queue design](worker-and-queue-design.md).

## Media Serving

The UI requests opaque routes such as `GET /media/assets/{asset_id}/source`, `/media/candidates/{id}/image`, `/mask`, or `/preview`. The API authorizes each request, resolves storage internally, sets safe content headers, supports bounded ranges where appropriate, and streams without loading entire files. A deployment may use short-lived signed opaque tokens to an internal media proxy, but never exposes absolute paths or unrestricted static mounts.

Original downloads are disabled by default; review receives a display representation unless permission/policy requires original bytes. Content disposition filenames are sanitized.

## API Security

Browser auth uses secure, HttpOnly, SameSite cookies plus CSRF protection, or another approved local identity mechanism documented before implementation. CORS is an explicit origin allowlist; credentials and wildcard origins are incompatible. Rate limits protect login, scans, model verification, bulk review, and exports. See [security](security.md).
