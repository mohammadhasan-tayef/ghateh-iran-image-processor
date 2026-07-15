# Storage Design

This document is authoritative for storage addressing, containment, file lifecycle, atomicity, and migration seams.

## Model and Addressing

Clients address files with `{root_id, relative_path}`. PostgreSQL stores `root_id` plus a normalized logical storage key such as `inbox/vendor-a/photo.png`; API responses may expose that logical key only when the caller is authorized. Host/container absolute paths are configuration secrets and never accepted from or returned to the frontend.

`StorageBackend` defines capability-focused operations: validate key, stat, stream read, incremental list, create temporary writer, finalize/rename, checksum, existence, and delete eligible derived artifacts. `LocalStorageBackend` is first. It must not provide a generic caller-controlled absolute-path escape hatch.

## Configured Roots

A root maps a stable UUID/alias to an environment-specific location such as host `E:\GhatehIran-Images` mounted read/write at `/data/shared`. Startup probes record availability, filesystem identity, free space, case sensitivity, atomic-rename support, and read/write capability. A changed volume identity requires administrator confirmation to prevent a reused drive letter from addressing the wrong disk.

Original subtrees are opened read-only by policy and ideally by mount permission. Derived-output subtrees are separately writable where deployment permits.

## Path Security

For every operation the backend:

1. Rejects empty, absolute, drive-qualified, UNC, device, alternate-data-stream, NUL-containing, and traversal paths.
2. Normalizes separators and Unicode according to a documented platform policy while preserving the stored display name.
3. Joins the key to the configured root and obtains the canonical existing ancestor/final path.
4. Verifies containment using path components, not string prefixes, with Windows case behavior respected.
5. Opens files with no-follow/reparse-point checks and rejects symlink, junction, or reparse escape at every traversed component.
6. Revalidates identity after opening to reduce time-of-check/time-of-use risk.
7. Allows only regular files and configured extensions, then verifies format from file signature during decode.

Directory enumeration returns opaque entry identifiers/logical keys, never host paths. See [security](security.md) for threat controls.

## Logical Layout and Lifecycle

```text
inbox/                         immutable source references
working/{operation_id}/        restart-safe temporary workspace
candidates/{asset_id}/{version_id}.png
masks/{asset_id}/{version_id}.png
previews/{asset_id}/{version_id}.jpg
review/                        optional materialized views, not authority
approved/                      optional selected-version materialization
failed/{operation_id}/         quarantined diagnostic artifacts by policy
exports/{batch_id}/            human-approved final outputs
models/                        administrator-managed verified weights
temp/                          disposable bounded scratch data
```

- **Original:** referenced in place and streamed; never copied for routine processing and never changed.
- **Working:** worker writes a unique operation directory. It may use local fast scratch if configured, but finalization must copy to a temporary file on the destination volume.
- **Candidate/mask/preview:** immutable, content-checked, and versioned by UUID. No in-place update.
- **Approved:** approval is a database fact. A materialized approved file is optional and must be reproducible from the selected candidate.
- **Export:** only a human-approved selected candidate is copied. Destination naming policy remains an open product decision.

## Atomic Writes

Write `.<target>.<operation_id>.partial` in the target directory, flush file buffers, close, calculate/verify SHA-256 and PNG properties, then perform a no-replace atomic rename on the same volume. Where directory flush is supported, flush the parent. Commit the final logical key/checksum to PostgreSQL using the operation id. Existing matching output makes a retry succeed idempotently; conflicting content produces a collision requiring policy resolution.

No design assumes rename across volumes is atomic. Copy to the target volume first. Temporary files are never served and are removed only by a reconciler after lease/age and database-reference checks.

## Versioning and Retention

Candidate artifacts are immutable and addressed by candidate UUID, not a mutable filename. Database rows record source and output checksums, byte sizes, media properties, creating run, and timestamps. Approved/exported candidates and their audit chain cannot be removed. Retention for rejected candidates, masks, previews, and failed workspace data is unresolved; deletion must be a scheduled, audited policy operation.

## Scanning, Duplicates, and Change Detection

The scanner enumerates lazily, checkpoints a backend-specific cursor plus last logical key, streams hashes in bounded buffers, and inserts chunks. Uniqueness on `(root_id, normalized_source_key, observed_version)` prevents duplicate registration on redelivery. SHA-256 plus byte length identifies equal content; policy decides whether equal content at different keys creates separate assets/memberships. A source that changes between stat/hash/open is retried and eventually flagged unstable.

The baseline assumes a batch source tree is operationally stable during scanning. Continuous filesystem watching is out of scope.

## Disconnection and Recovery

I/O errors are classified as unavailable, missing, permission, corruption, capacity, or unknown. On volume loss, scanning pauses and processing/export tasks back off without marking image semantics failed. The root health record changes to unavailable. Reconnection must match the configured volume identity; tasks re-stat originals and verify expected size/checksum before continuing. Partial files are reconciled before new writes.

If an original is missing or changed, the affected image is blocked/failed with an explicit source-integrity reason and requires operator action. The system never substitutes another file by name.

## NAS and S3-Compatible Migration

Domain and API code retain logical keys. A NAS backend may implement local-style operations but must declare weaker locking/rename capabilities and pass the same conformance suite. A future S3-compatible backend replaces rename with write-to-unique-key plus conditional copy/put and immutable object versions. Database artifact descriptors remain authoritative; URL generation stays inside an authorized media service. Shared storage is a prerequisite for workers on separate hosts.
