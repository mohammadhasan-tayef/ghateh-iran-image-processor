# Security

This document is authoritative for the initial threat model, authentication, fixed-role authorization, storage/media controls, and audit requirements. Network locality, including loopback-only access, is not an authentication or authorization boundary.

## Threats and Protected Assets

Protected assets include immutable source photos, approved/exported images, account/session/CSRF secrets, server mount mappings, models, naming/preset snapshots, review decisions, and audit records. Threats include unauthorized access/export, session theft/fixation, CSRF, credential guessing, path/reparse escape, malicious image decode, Unicode/case collisions, model/supply-chain tampering, resource exhaustion, and audit alteration.

Public internet exposure remains unsupported. For the Internal Pilot, browser access to web/API entry points is restricted to loopback/local-host access on the same Windows computer. LAN exposure is unsupported for this profile; PostgreSQL/Redis are not client-accessible. Local-only exposure does not weaken named authentication, PostgreSQL-backed sessions, CSRF protection, fixed-role authorization, path containment, configured-root controls, or secure secret handling. Any future network-accessible profile requires a separate reviewed security and deployment decision.

## Authentication Decision

MVP authentication is named local accounts, Argon2id password hashes, PostgreSQL-backed server-side UserSessions, an opaque secure cookie, and CSRF protection. Browser JWT and OAuth are excluded.

On successful login the server rotates a cryptographically random session token, stores only `token_hash`, stores hashed/equivalent CSRF metadata, and sends the token in an `HttpOnly` cookie. The cookie uses a reviewed `SameSite` policy (default `Lax` unless deployment/testing proves `Strict` compatible), a narrow Path, and `Secure` in production. TLS is required for production credential/session transport; local development exceptions are explicit.

UserSession stores UUID id/user id, token/CSRF hashes, created/last-seen times, idle/absolute expiry, optional revocation, copied session version, minimal bounded client metadata, optional IP hash, and summarized user agent. Avoid raw IP/user-agent retention unless required.

Required behavior:

- enforce idle and non-extendable absolute timeout server-side;
- update `last_seen_at` at a throttled interval, not every request;
- revoke current session on logout and clear cookie;
- support logout-all and individual session revocation;
- rotate after login and privilege changes;
- increment User `session_version`/revoke all sessions after password reset, role/status change, or security response;
- reject disabled users, stale session versions, expiry, revoked sessions, and missing/invalid CSRF on state changes;
- rate-limit/audit authentication and session management without logging tokens.

See [ADR 0009](../adr/0009-server-side-session-authentication.md).

## Fixed Roles and Permission Matrix

Permissions are fixed in application code. No UI/API/database table edits role permissions.

| Capability | admin | operator | reviewer | auditor |
|---|:---:|:---:|:---:|:---:|
| Manage users/sessions | Yes | No | No | No |
| Activate/label configured roots | Yes | No | No | No |
| Browse enabled roots | Yes | Yes | No | Read-only batch references only |
| Manage presets/models | Yes | No | No | Read-only history |
| Create/start/pause/cancel batches | Yes | Yes | No | No |
| View batches/results | Yes | Yes | Review-scoped | Yes, read-only |
| Request reprocessing | Yes | Yes | Yes | No |
| Approve/reject/select candidate | Yes | No | Yes | No |
| Create/cancel/retry exports | Yes | No | No | No |
| View export/audit history | Yes | Own operational scope | Review-related history | Yes, read-only |

Every permission is enforced in application use cases and per resource, not just UI/routes. The MVP deliberately defers root-level per-user scoping; admin/operator access all enabled roots consistent with their capabilities. Adding `UserStorageRootAccess` requires a later decision. Worker identities receive only task-specific DB/mount privileges.

## Storage Root and Path Controls

Server/Docker configuration maps `config_key` to container path/mode. Admin activation sends only config key, alias, and enabled state. Unknown keys are rejected. Host paths are never returned or logged to clients. A missing mount is unavailable; a changed volume identity blocks automatic resume until admin verification. Drive-letter change is handled in server configuration.

All operations accept root id plus relative path/logical key and apply the containment/reparse/Unicode rules in [storage design](storage-design.md). Original mounts are read-only where possible. Workers run non-root and never construct shell commands from filenames.

## Image and Media Controls

- Decode signature-verified regular files in isolated/bounded worker processes with byte/pixel/frame/time/RAM limits.
- Reject archives/nested containers; quarantine any later browser upload before validation.
- SourcePreviewArtifact is the normal raw-side review media. It permits only EXIF orientation and resize, has an opaque authorized route, and never exposes the original path.
- Candidate/mask/export media routes authorize each object, set `nosniff`, constrained types/CSP headers, and safe Unicode Content-Disposition.
- No storage directory is served as unrestricted static content; original download remains disabled by default.

## Web, Localization, and API Controls

CORS allowlists exact origins and never combines wildcard with credentials. CSP restricts scripts/connect/media and denies framing. Backend error codes are stable English identifiers without secrets/paths; the `fa-IR` frontend maps them to Persian messages. Technical values render LTR in the RTL UI. Validate schemas, SubjectMode/shadow/naming bounds, cursor sizes, state commands, and idempotency hashes. Parameterized SQL and bounded schema-versioned JSONB are mandatory.

## Secrets, Dependencies, and Infrastructure

Secrets remain outside Git/images in restricted files or approved local secret storage. Logs redact password/session/CSRF values, DB URLs, mount paths, and sensitive EXIF. Dependencies/container images/model weights are pinned and verified by source/version/checksum; avoid unsafe untrusted pickle deserialization.

Windows 11/Docker Desktop/WSL2 runs Linux containers as non-root with explicit mounts, limits, health checks, no Docker socket, and minimal capabilities. PostgreSQL 17 and Redis 7.x remain internal; exact patches/images are selected and pinned in Sprint 1.

## Audit and Security Gates

Audit login outcome, session create/revoke/expiry/global invalidation, user/role/status changes, configured-root activation/identity confirmation, lifecycle/review/export, authorization denials, model/preset/naming changes, and retention actions with UTC time, subject, actor/task, correlation, prior/new state, and reason—never secret values.

Release gates: Argon2id/session/CSRF review; fixation/rotation/idle/absolute/logout-all/password-reset tests; fixed permission matrix tests; Windows containment/reparse/Unicode tests; decode bombs; CORS/CSP; secret/model/dependency scans; container privileges; and backup restore.
