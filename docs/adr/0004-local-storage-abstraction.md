# ADR 0004: Address Local Storage Through an Abstraction

- Status: Accepted
- Date: 2026-07-15

## Context

The first deployment reads an external Windows drive directly, while later workers may use a NAS or S3-compatible store. Browser-supplied absolute paths are unsafe and host mappings differ between Windows and containers.

## Decision

Introduce a capability-based `StorageBackend` port and implement local storage first. All business references are `{storage_root_id, logical_key}`. Root mappings are server configuration and never cross the REST boundary. The adapter enforces containment, no-follow/reparse protections, streamed I/O, operation-scoped temporary writes, checksum verification, and atomic same-volume finalization.

## Consequences

- Originals can be referenced without copying and host paths do not contaminate domain/API contracts.
- The adapter requires a rigorous Windows conformance/security suite.
- NAS/object backends can preserve logical keys but must disclose different atomicity/capability semantics.
- The abstraction must stay task-focused; it is not a generic virtual filesystem.

## Rejected Alternatives

Passing absolute paths exposes the host and enables traversal. Copying every batch internally is too expensive. Coding directly to `pathlib` throughout the application would make security inconsistent and migration costly.
