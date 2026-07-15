# Storage Design

This document is authoritative for server-configured roots, source observations, logical addressing, containment, file lifecycle, atomicity, and migration seams.

## Server-Configured Roots

Host/Docker configuration, not the frontend, defines mount mappings:

```yaml
storage_roots:
  external_images:
    container_path: /data/shared
    mode: read_write
```

An administrator may activate `{config_key: external_images, alias: هارد تصاویر قطعه ایران, enabled: true}`. StorageRoot persists the config key and observed/expected volume identity, not the host path. The backend resolves the actual container path from trusted server configuration. Absolute host paths are never accepted or returned by the REST API.

Clients select folders with `{root_id, relative_path}`. PostgreSQL stores root id plus normalized logical keys. `StorageBackend` exposes capability-focused validate/stat/stream/list/temp-write/finalize/checksum/existence operations; it never exposes a generic client-controlled absolute-path function.

## Root Availability and Volume Identity

Startup/explicit probes record mount availability, filesystem/volume identity, free space, case/Unicode behavior, rename/flush capability, and access mode.

- Missing configured mount: root health is `unavailable`; activation may remain recorded but scan/process/export commands fail/hold with a typed retryable result.
- Windows drive-letter change: update host/Docker configuration for the same config key, then re-probe; the frontend still uses the same root id.
- Disconnect during scan: persist cursor and move Batch to `scan_paused`.
- Disconnect during processing: stop I/O and retry/hold the ProcessingRun; do not classify the image semantically or immediately mark it processing-failed.
- Disconnect during export: retry/fail ExportItem only; BatchImage remains approved.
- Reconnect with another volume identity: block the root and all automatic resume until admin verifies/rebinds. A reused drive letter never silently substitutes content.

Prefer separate read-only original and writable derived mounts where operationally possible.

## Path and Unicode Security

For every operation the adapter:

1. Rejects empty, absolute, drive-qualified, UNC, device, alternate-data-stream, NUL, and traversal inputs.
2. Normalizes separators and applies a documented Unicode comparison strategy while preserving the Persian/original display filename.
3. Joins beneath the configured root and canonicalizes the existing ancestor/final path.
4. Verifies component containment with Windows case semantics, not string prefixes.
5. Rejects symlink, junction, or reparse escape at every traversed component and uses no-follow/open-then-verify controls.
6. Allows regular files/configured types only and verifies actual signature during decode.

Persian and Unicode filenames are supported. Logical keys have a normalized comparison form and a preserved display form; normalization must not create silent collisions. Directory APIs return opaque ids/logical keys, never mount paths.

## Source Observation Identity

The scanner enumerates lazily and creates immutable SourceObservation records:

- UUID id, ImageAsset/root ids, logical/display source key;
- observed size bytes, mtime nanoseconds, optional filesystem identity;
- content SHA-256 nullable until streamed hashing completes;
- discovery/hash timestamps and availability.

Same logical path plus size/mtime may identify the same preliminary observation on message redelivery, subject to filesystem timestamp capability. It does not prove equality. SHA-256 is the authoritative duplicate-content signal once available and is calculated in bounded streaming buffers; a full file is never loaded for hashing. Re-stat/identity checks bracket hashing. Changed content at the same path creates a new observation, and each BatchImage remains bound to the exact observation it used.

Duplicate content at different logical paths may be flagged/deduplicated operationally, but business policy decides whether both become batch members. Continuous filesystem watching is out of scope.

## Layout and Artifact Lifecycle

```text
inbox/                                      immutable source references
working/{operation_id}/                     restart-safe temporary workspace
source-previews/{observation_id}/{generation}.jpg
candidates/{batch_image_id}/{candidate_id}.png
masks/{batch_image_id}/{candidate_id}.png
previews/{batch_image_id}/{candidate_id}.jpg
failed/{operation_id}/                      policy-controlled diagnostics
exports/{export_job_id}/                    human-approved production RGB PNGs
models/                                     verified administrator-managed weights
temp/                                       bounded disposable scratch
```

- **Source:** referenced/streamed in place; application never writes, renames, moves, deletes, truncates, or intentionally changes content metadata.
- **Source preview:** generated from a SourceObservation using EXIF orientation normalization and display resize only. It is versioned/regenerable, never substitutes the source, and is the default raw-side review artifact.
- **Candidate:** immutable UUID artifact; internal candidate may be RGBA. Masks may be grayscale/alpha PNG.
- **Export:** independent job output flattened to PNG, exactly 2000 × 2000, 8-bit sRGB RGB, no alpha, with a pure-white canvas outside the product and any enabled bounded contact shadow.

The source mutation guarantee is content/application behavior: source SHA-256 must remain unchanged. OS/filesystem/antivirus/mount access-time changes are outside the application's guarantee and are not asserted as failures.

## Atomic Writes and Versioning

Write `.<target>.<operation_id>.partial` on the target volume, flush/close, validate checksum/media properties, then no-replace atomic rename in the same directory/volume. Cross-volume rename is never assumed atomic. Existing identical output makes retry idempotent; conflicting content follows the ExportJob naming snapshot/collision policy or raises conflict.

Candidate UUIDs address immutable artifacts. `version_no` is display-only, allocated under a short BatchImage database lock as defined in [database design](database-design.md). Temporary/orphan cleanup requires age, lease, DB-reference, and checksum checks.

Source previews may be regenerated with a new generation version. Approved/exported provenance and artifacts remain retained per policy. Retention periods for rejected candidates, previews, masks, sessions, and diagnostics remain open.

## Naming Snapshot and Export

Each ExportJob freezes a schema-versioned naming-policy snapshot before running: source/SKU naming mode, sanitization, Unicode policy, collision strategy, suffix/`.png`, maximum length, directory grouping, case behavior, and duplicate-output behavior. One approved candidate may be independently exported multiple times. ExportItem outcomes never mutate BatchImage or Batch state.

## NAS and S3-Compatible Migration

Domain/API retain root plus logical key. A NAS adapter declares weaker atomicity/locking capabilities and passes the same Unicode/security/disconnect conformance suite. A future S3-compatible adapter replaces rename with unique-key conditional object operations while preserving artifact descriptors and immutable job snapshots. Shared storage is required before multiple worker hosts.
