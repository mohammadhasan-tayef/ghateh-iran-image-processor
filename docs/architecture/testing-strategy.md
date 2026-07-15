# Testing Strategy

Testing prioritizes original safety, path containment, lifecycle correctness, idempotency, recovery, and product authenticity warnings. Tests are layered so domain behavior does not require models, Docker, or real external drives.

## Unit Tests

- Domain transition tables, invariants, review supersession, export eligibility, and batch roll-ups
- Use-case commands with fake repositories/clock/storage/queue and Unit of Work rollback
- Logical-key normalization and containment across Windows/POSIX cases
- Preset validation, score components, routing rules, and stage contracts
- Idempotency request hashing, error mapping, pagination cursors, and authorization policies
- Pipeline geometry, uniform scaling, exact-white composition, color bounds, and QC functions using small fixtures

Property-based tests generate path traversal/case/Unicode/separator inputs, state-command sequences, duplicate deliveries, image dimensions, and framing geometry.

## Integration and Contract Tests

- PostgreSQL migrations, constraints, transaction isolation, concurrent claims/reviews, outbox, indexes, and restore compatibility
- Redis/Celery publish/redelivery/loss behavior without treating backend results as truth
- `StorageBackend` conformance for local Windows semantics and simulated NAS capability differences
- Real filesystem symlink/junction/reparse, disconnect, low-space, permissions, and atomic-finalize behavior
- Engine adapter contracts with pinned small models where licensing/resources permit
- REST schemas, cookies/CSRF/CORS, authorization matrix, media streaming, rate/size limits, and no absolute-path leakage

## Pipeline Fixtures

Maintain a licensed/consented fixture manifest with SHA-256, category, challenge labels, expected invariants, and approved masks/outputs where available. It covers text/labels, internal holes, thin cables, transparent/translucent materials, white/dark products, reflective metal, shadows, clutter, clipping, multiple objects, corrupt files, huge dimensions, EXIF orientation, and unusual color profiles.

`samples/raw` and `samples/reference-output` remain local/ignored until redistribution rights and repository-size policy are approved. CI may download an internal versioned fixture package by checksum or generate synthetic fixtures.

## Golden-Image and Authenticity Tests

Golden tests never assert that aesthetic pixel identity proves correctness. They combine exact properties (format, dimensions, background, checksum when deterministic), perceptual/color/edge/mask/topology metrics with documented tolerances, and human-approved semantic labels. Changes to a model, preset, library, hardware mode, or thresholds create a comparison report and require explicit baseline approval; golden files are not silently regenerated.

Hard cases must route warnings/review. Tests verify the pipeline does not inpaint or add foreground pixels outside bounded mask/refinement rules. Manual evaluation tracks false removal/addition separately from visual quality.

## Hardware Variance

Run a mandatory CPU suite on the supported Windows deployment. GPU suites are tagged by GPU/CUDA/model build and compare tolerance metrics unless deterministic byte equality is proven. Record device and dependency versions. Differences outside calibrated bounds block promotion rather than being normalized away.

## End-to-End Tests

Exercise root setup, incremental scan, process stub/real test adapter, review, reprocess/version selection, export, audit lookup, pagination, keyboard review flows, cancellation, and reconnect. Verify browser closure does not stop work and no host path appears in UI/network payloads.

## Performance and Capacity

On named baseline hardware, scan synthetic 10k/100k-entry trees, hash representative sizes, bulk-register, page review queues, and process a licensed representative subset. Measure peak memory, DB/queue/storage throughput, stage latency, GPU memory, and UI response. Validate watermarks, per-root I/O caps, disk quotas, and that no full batch list is retained in memory. Targets are set after the Sprint 3 baseline rather than invented in Sprint 0.

## Recovery and Destructive-Scenario Tests

Kill API/worker/Redis/PostgreSQL at controlled points; disconnect/remount the drive; reuse a drive letter with a different volume; leave partial files; fill the disk; duplicate/reorder messages; expire leases; and race review/export/cancel commands. Assert originals remain byte-identical, final files are never partial, durable states recover, stale workers are fenced, and every export remains explainable.

## Quality Gates

Sprint gates include formatting/lint/type checks, unit/integration tests, migration up/down policy checks, security scans, documentation link/diagram validation, and a no-unapproved-golden-change rule. Operational release additionally requires path-security testing on Windows, backup restore, restart/disconnect recovery, model provenance, baseline capacity, and manual acceptance on the reference set.
