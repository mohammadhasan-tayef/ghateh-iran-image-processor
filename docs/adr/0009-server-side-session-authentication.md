# ADR 0009: Use PostgreSQL-Backed Server-Side Browser Sessions

- Status: Accepted
- Date: 2026-07-15

## Context

The local-network web application needs named accountability, immediate revocation after password/role/status changes, CSRF protection, idle/absolute expiry, and durable audit. Browser-held self-contained credentials would complicate immediate revocation and are unnecessary for the MVP.

## Decision

Use named local accounts with Argon2id password hashing and PostgreSQL-backed UserSession records. The browser receives a random opaque token only in an `HttpOnly`, production `Secure`, reviewed-SameSite cookie. PostgreSQL stores only token/CSRF hashes plus created/last-seen, idle/absolute expiry, revocation, session version, and minimal client metadata.

Rotate the session after login and privilege changes. Support logout, individual revocation, logout-all, idle expiry, absolute expiry, and global invalidation after password reset or role/status change. State-changing cookie-authenticated requests require CSRF proof. Browser JWT and OAuth are excluded from MVP.

## Consequences

- Revocation and session audit are immediate and durable across API restarts/instances.
- PostgreSQL availability is required to authenticate requests; session lookup/index/cleanup load must be monitored.
- TLS/cookie/CSRF configuration and secret-safe logging are release gates.
- Fixed roles remain application-code policy; session records do not carry editable permission documents.

## Rejected Alternatives

JWT browser authentication makes immediate revocation/versioning more complex and moves sensitive credential state to the client. OAuth adds external identity/deployment scope not required for local MVP. In-memory sessions fail across restart/instances.
