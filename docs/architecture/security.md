# Security

This document is authoritative for the initial threat model and required controls. “Local network” is not a security boundary: compromised clients, curious users, malware, and accidental misconfiguration remain credible.

## Assets and Threats

Protected assets include original product images, approved outputs, credentials, absolute root mappings, model weights, audit records, and host resources. Principal threats are unauthorized browsing/export, path traversal or junction escape, malicious/corrupt image decompression, credential theft, CSRF/session abuse, overly broad CORS, model/supply-chain tampering, command injection, denial of service through batches/files, audit alteration, and cross-user action confusion.

Public internet exposure is unsupported. Network/firewall configuration limits access to approved LAN segments; PostgreSQL and Redis are not exposed to clients.

## Authentication and Sessions

The first implementation uses named accounts with a modern password hash (Argon2id using reviewed parameters) and server-managed sessions, unless a site identity provider is selected before Sprint 1. Session identifiers are random, rotated at login/privilege change, stored hashed server-side, and delivered in `Secure` where TLS is used, `HttpOnly`, `SameSite` cookies. State-changing browser requests require CSRF protection. Login is rate limited and audited; default credentials are forbidden.

TLS is recommended even on LAN and required if credentials cross an untrusted segment. A deployment-specific certificate approach remains to be chosen.

## Authorization

Permissions are checked in application use cases, not only UI/routes. Proposed permissions separate root/model/user administration, batch operation, review, bulk review, approval revocation, export, and audit read. Resource checks prevent access to a batch/root outside the actor's scope. Bulk actions authorize every item and return per-item results. Worker identities have only task-specific database/storage capabilities.

## Filesystem and Media Controls

- Accept only root UUID and relative logical key; apply all containment and reparse-point rules in [storage design](storage-design.md).
- Mount original locations read-only when operationally possible and separate derived write permissions.
- Run workers as non-admin users; never invoke shell commands with filenames.
- Decode by file signature in isolated worker processes with byte, pixel, dimension, frame, time, and memory limits; strip unsafe metadata from outputs.
- Reject archives and nested containers from image ingestion. Browser upload, if later enabled, writes to quarantine with randomized names before validation.
- Media routes reauthorize each object, send `nosniff`, constrained content types, CSP-compatible headers, and sanitized filenames. No directory is exposed as unrestricted static content.

## Secrets and Configuration

Secrets live outside Git and images in environment/secret files with restricted permissions or an approved local secret facility. `.env` files are development-only and ignored. Logs and errors redact passwords, session tokens, database URLs, host absolute paths, and sensitive EXIF. Rotate database, Redis, session-signing, and admin credentials with documented procedures.

Model weights and dependencies are installed from approved sources, pinned by version/checksum, scanned according to site policy, and verified before activation. Never deserialize untrusted pickle-based model/input content; PyTorch model formats and loading modes require a focused review.

## Web and API Controls

- CORS allowlists exact configured UI origins; no wildcard with credentials.
- CSP restricts scripts/connect/media; frame ancestors are denied; security headers are enabled.
- Validate request schemas, enum/state commands, pagination bounds, and idempotency payload hashes.
- Rate/size/concurrency limits cover login, listing, scan, hashing, processing, preview generation, review bulk commands, and export.
- Errors use correlation IDs and stable categories without stack traces or host paths.
- Database queries are parameterized through SQLAlchemy; JSON fields are schema-validated and size-bounded.

## Infrastructure

PostgreSQL uses authenticated encrypted connections where crossing process/host trust boundaries, least-privilege roles, backups, and no client-network listener. Redis is private, authenticated where supported, memory-bounded, and disposable. Containers use pinned images, non-root users, read-only filesystems where possible, explicit volumes, resource limits, and no Docker socket. Host drive mappings are minimal.

## Auditability and Response

Authentication, configuration, lifecycle, review, export, authorization denial, and administrative retention actions record actor/task identity, UTC time, subject, correlation ID, prior/new state, and reason without secrets. Application users cannot update/delete audit events. Database administrators remain a trusted role; backups and restricted DB access mitigate tampering rather than claiming cryptographic immutability.

On suspected compromise, administrators can disable accounts/roots, stop dispatch, preserve logs/database/artifacts, rotate secrets, verify model/checksums, and reconcile exports. Exact incident and retention policies remain operational decisions.

## Security Release Gates

Threat-model review, path containment/reparse test suite on Windows, decompression-bomb tests, authorization matrix tests, CSRF/CORS checks, dependency/model provenance verification, secret scan, container privilege review, and backup restore are required before operational use.
