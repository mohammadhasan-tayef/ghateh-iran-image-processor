# Testing Strategy

Testing prioritizes source safety, path/session authorization, lifecycle separation, relational integrity, candidate concurrency, deterministic output, RTL operation, idempotency, and recovery. Domain tests require no models, Docker, or real drive.

## Unit and Property Tests

- Batch/BatchImage transition tables: `review_completed`/`partially_completed` depend only on processing/review; exports never change them.
- ExportJob/ExportItem transitions including `skipped`, multiple jobs per approved candidate, and failure leaving BatchImage approved.
- Fixed-role permission matrix and resource checks; no dynamic permission behavior.
- UserSession idle/absolute expiry, session-version invalidation, rotation, logout, logout-all, password reset/role/status revocation, CSRF decisions.
- SourceObservation preliminary identity, streamed hash state, same-path changed content, and exact BatchImage binding.
- Composite same-BatchImage candidate/review/export invariants and candidate sequence allocation policy.
- SubjectMode rules and preset schema, including all shadow parameter bounds/default disabled.
- Pipeline geometry, exact-white composition, source-preview permitted transforms, contact-shadow non-interference, and final RGB PNG validation.
- Unicode/Persian path normalization/collision and logical/display key preservation.

Property tests generate traversal/case/Unicode/separator inputs, state sequences, duplicate deliveries, concurrent finalization orders, subject component shapes, filename/naming snapshots, and framing/shadow geometry.

## Integration and Contract Tests

- PostgreSQL 17 constraints: all composite FKs, unique candidate sequence, session lookup/revocation, concurrent locks/claims/reviews/finalizers, outbox, and restore compatibility.
- Redis 7.x/Celery redelivery/loss with PostgreSQL authoritative.
- StorageBackend on Windows 11/Docker Desktop/WSL2: server config-key activation, missing mount, drive-letter remap, disconnect at scan/process/export, different volume identity, reparse, Unicode, low space, and atomic finalize.
- API: no host-path root creation/exposure; session cookie flags, fixation/rotation, CSRF/CORS, permission matrix, pagination, stable English codes, Persian mapping contract, media authorization, naming snapshot immutability.
- SourcePreviewArtifact: only EXIF orientation/resize, exact observation reference, regeneration, no path leakage.
- Engine/pipeline contracts and final export encoder: PNG 2000 × 2000, 8-bit sRGB RGB, no alpha; `#FFFFFF` outside product and any enabled bounded shadow.

## Pipeline Fixtures and Golden Tests

Licensed fixture manifest records source checksum, SubjectMode, challenge labels, required real components, expected invariants, and approved masks/outputs. Cover single objects, packaging, valid multi-component products, unrelated objects/hands/tools/rulers, cropped/hidden parts, thin cables, transparent/white/dark products, reflective metal, text, holes, shadows, corrupt/huge files, EXIF, and color profiles.

Golden tests combine exact media properties with perceptual/color/edge/mask/topology metrics and human semantic labels. They never treat aesthetic equality as authenticity. Shadow fixtures assert low opacity/neutrality/bounds, product-pixel identity with shadow on/off, no detail occlusion, and disabled-by-default behavior. Baselines never regenerate silently.

## Source Immutability Tests

Capture source content SHA-256 and application-visible content metadata, execute scan/process/review/retry/export/recovery, and assert no application write/rename/move/delete/truncate and unchanged SHA-256. Do not fail on filesystem access-time changes caused by OS, filesystem, antivirus, or mount behavior. Use read-only mount/permission assertions where supported and instrument storage calls to prove no write handle targets source keys.

## Concurrency and Recovery Tests

Run simultaneous distinct reprocess finalizers for one BatchImage and duplicate finalizers for one run. Assert UUID identity, idempotent same-run return, unique `(batch_image_id, version_no)`, composite FK enforcement, and stale-fence rejection. Kill after artifact write/before DB commit and after commit/before acknowledgement; reconcile without duplicate candidates.

Kill API/worker/Redis/PostgreSQL, disconnect/remount/reuse drive letter, fill disk, reorder messages, expire leases, and race review/export/cancel. Assert SourceObservation remains exact, no partial final, Batch/BatchImage never adopt export failure, and every export remains explainable.

## Localization, Accessibility, and Browser Tests

Run primary `fa-IR` RTL flows for login, root/batch, review, export, and errors. Verify Persian font asset loading in its implementation sprint; LTR isolation for hashes, UUIDs, paths, filenames/extensions, model/version values; Persian Unicode filename round-trip; timezone display from UTC; focus order; screen labels; and direction-independent hotkeys. Test English technical error code to Persian message mapping.

## Performance and Hardware Variance

On named baseline Windows 11/Docker Desktop/WSL2 CPU hardware, scan synthetic 10k/100k trees, stream hashes, generate bounded previews, bulk-register, page RTL review queues, and benchmark representative pipeline/shadow on/off. Record peak memory, DB/queue/storage rates, stage latency, and UI response. GPU is separately tagged/deferred. Targets are set from the Sprint 3 benchmark.

## Quality Gates

Require formatting/link/diagram checks; no implementation in documentation sprints; unit/integration/security tests; migration checks when implementation starts; no unapproved golden change; source/path/session/role/RTL/output/recovery suites; model/dependency provenance; and backup restore. Mandatory human approval is asserted end-to-end: no score can create approval or production export.
