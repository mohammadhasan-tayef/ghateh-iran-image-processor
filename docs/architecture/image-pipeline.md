# Image Pipeline

This document is authoritative for processing stages, contracts, authenticity controls, artifact production, and reproducibility. The pipeline is non-generative: it may select pixels, transform them conservatively, and composite them; it must not synthesize missing product content.

## Pipeline Context

`PipelineContext` is an immutable-per-stage data contract assembled for one `ProcessingRun`. It contains:

- run, batch-image, asset, storage-root, preset-revision, engine, model-installation, and correlation identifiers;
- source logical key, expected SHA-256/size/format, and an authorized storage reader;
- pipeline code version, stage graph version, model name/version/checksum, device and deterministic settings;
- bounded parameters for segmentation, refinement, framing, correction, denoise, sharpening, encoding, and QC;
- stage artifact descriptors, measurements, warnings, timings, and cancellation/deadline signals.

Stages do not open arbitrary paths or write database state. A stage consumes a typed context/artifact and returns a new artifact descriptor plus facts. Large pixel arrays may be mutable within a worker for efficiency but are never shared between runs; ownership and cleanup are explicit.

## Stage Contract

Every stage declares input/output media type, parameter schema/version, memory estimate, deterministic expectation, failure categories, and produced metrics. It must validate prerequisites, check cancellation at safe points, bound allocations, avoid hidden global state, and never overwrite an input. Failures are typed as validation, source integrity, resource exhaustion, engine/model, quality gate, cancellation, or transient I/O.

## Default Pipeline

1. **Verify source:** open through storage, stream/check expected bytes and SHA-256, reject mutation, and enforce decode limits.
2. **Decode/orient:** decode the actual signature, apply EXIF orientation, normalize to a documented color space, and preserve the untouched source.
3. **Segment:** run the configured engine Strategy. BiRefNet is primary; rembg is fallback only through explicit policy or reprocess selection, not silent result blending.
4. **Refine mask:** bounded morphology/edge feathering and hole preservation. Retain the raw and refined mask descriptors for diagnosis when policy enables them.
5. **Authenticity gates:** detect likely clipping, lost internal holes, disconnected fine structures, excessive transparent area, uncertain foreground, or a material mask change. Unsafe cases route to review with warnings; severe invalid output fails the run.
6. **Crop geometry:** calculate the foreground bounding box without changing product proportions. Empty or boundary-clipped masks fail.
7. **Conservative correction:** bounded global/per-channel lighting and color operations applied to foreground pixels only. No inpainting, content-aware fill, generative relighting, shape warp, or local reconstruction.
8. **Mild cleanup:** optional preset-bounded denoise and unsharp mask. Disable or warn when text/edge metrics indicate damage risk.
9. **Compose:** scale uniformly into a 2000 × 2000 canvas with category/preset margins, center according to the documented anchor, and composite all background pixels to exact sRGB `#FFFFFF`.
10. **Encode candidate:** lossless PNG with controlled metadata; generate mask/preview as separate versioned artifacts.
11. **Quality checks:** validate dimensions, PNG decodability, canvas background, margins, clipping, foreground coverage, mask topology deltas, edge halos, blur/noise deltas, color deltas, and output checksum.
12. **Finalize/route:** atomically finalize artifacts, persist candidate provenance and QC facts, and route every rollout-one candidate to `needs_review`.

## Segmentation Abstraction

`SegmentationEngine.segment(input, options) -> SegmentationResult` is a Strategy port. The result includes alpha/mask, engine confidence components when meaningful, warnings, model identity/checksum, timings, and device facts. Adapters translate BiRefNet/rembg inputs and errors but cannot normalize away uncertainty. A Factory chooses only an installed, verified adapter allowed by the immutable preset revision.

BiRefNet is selected by [ADR 0008](../adr/0008-birefnet-primary-rembg-fallback.md), subject to a Sprint 3 benchmark gate. rembg is a fallback adapter for explicit retry or configured technical failure; its output receives identical QC and review.

## Authenticity and Hard Cases

Deterministically safe operations include orientation, uniform scaling, canvas placement, exact-white compositing, lossless encoding, bounded global correction, and checksum/properties validation. Segmentation, mask refinement, denoising, sharpening, and foreground/background classification are uncertain.

- **Text and geometry:** never warp or reconstruct; compare edge/text-region proxies before/after and warn on material change.
- **Internal holes:** preserve mask topology; large topology deltas or filled holes require review.
- **Thin cables:** use high-resolution masks and conservative refinement; warn on disconnected components or vanishing skeleton length.
- **Transparent/translucent materials:** default to mandatory review; exact white compositing may change appearance and confidence is not semantic proof.
- **White products:** use boundary/context-aware segmentation and warn on low contrast or lost edges.
- **Reflective metal:** cap correction/sharpening; detect highlight clipping and halos.
- **Dark products:** detect crushed shadows and foreground holes; avoid aggressive black-point changes.

If the foreground is empty, clipped, implausibly small/large, materially fragmented, or the engine/model is unverified, the pipeline stops or produces a clearly warned review candidate according to preset policy. It never fills a suspected missing part.

## Quality and Confidence

The quality result is a versioned vector of measurements and rule outcomes plus an optional calibrated routing score. Candidate factors include valid format/dimensions, foreground coverage/margins, clipping, background purity, mask uncertainty, topology, blur/noise deltas, color delta, halo indicators, and engine signals. Thresholds are preset revision data and are calibrated against labeled fixtures.

Quality score answers “did this artifact satisfy measurable technical rules?” Segmentation confidence estimates an engine/model property. Neither answers “is every product component semantically correct?” A high score cannot guarantee product accuracy and never bypasses human approval in rollout one.

## Reproducibility

Each run records source checksum; pipeline/stage versions; preset revision and full validated parameters; engine/model/checksum; dependency lock/build identity; device type; relevant library versions; random seeds; deterministic flags; stage timings/warnings; and artifact checksums. GPU operations may remain nondeterministic; the record must identify that fact and golden tests use tolerance/metrics rather than byte identity where justified.

Reprocessing always creates a new run and candidate. Previous candidates remain immutable and selectable through review policy.
