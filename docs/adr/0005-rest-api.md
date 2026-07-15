# ADR 0005: Expose a Versioned REST API

- Status: Accepted
- Date: 2026-07-15

## Context

The React control panel needs stable commands and paginated queries for resources with explicit lifecycles. The system is a local operational application, not a public data graph.

## Decision

Expose JSON REST resources under `/api/v1` using FastAPI/Pydantic. Model long-running actions as commands returning authoritative resource representations, with idempotency keys and optimistic concurrency. Use opaque cursor pagination for large collections and authorized opaque media routes. Never accept or expose host absolute paths.

## Consequences

- HTTP semantics, error codes, versioning, and generated schemas are straightforward to test.
- Command endpoints are used where state transitions do not map cleanly to CRUD.
- Polling is the MVP status mechanism; optional SSE can later provide hints without becoming truth.
- API compatibility and deprecation need discipline.

## Rejected Alternatives

GraphQL adds resolver authorization/caching complexity without a need. Direct database access violates security and domain rules. WebSocket-only control couples durable workflow to a transient connection.
