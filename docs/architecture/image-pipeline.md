# Image Pipeline

This document is authoritative for processing stages, SubjectMode, authenticity controls, deterministic contact shadow, artifact formats, quality checks, and reproducibility. The pipeline is non-generative: it may select/transform real pixels and derive a shadow from the real mask; it never synthesizes missing product content.

## PipelineContext and Preset Snapshot

`PipelineContext` is assembled for one ProcessingRun and contains run/BatchImage/SourceObservation/root identifiers; expected logical key/size/SHA-256; authorized storage reader; immutable preset revision/snapshot; SubjectMode; engine/model/checksum; code/stage versions; device/determinism facts; bounded stage parameters; artifacts/measurements/warnings/timings; and cancellation/deadline signals.

The validated preset snapshot includes:

- `subject_mode`: `single_object`, `product_with_packaging`, `multi_component_product`, `keep_all_foreground_objects`, or `manual_subject_selection_required`;
- framing, segmentation, mask-refinement, correction, denoise, sharpening, encoding, and QC settings;
- `shadow_enabled` (default false), `shadow_opacity`, `shadow_blur_ratio`, `shadow_offset_x`, `shadow_offset_y`, `shadow_color`, and `shadow_spread`.

Stages do not open arbitrary paths or persist business state. Each declares typed inputs/outputs, parameter/version schema, resource estimate, deterministic expectation, cancellation points, failure categories, and metrics. Pixel buffers have one run owner and bounded cleanup.

## Default Candidate Pipeline

1. **Verify source observation:** open through StorageBackend; re-stat and stream/check exact size/SHA-256; reject mutation/substitution; enforce decode limits.
2. **Decode/orient:** verify signature, apply EXIF orientation, normalize to documented sRGB working space; source remains unchanged.
3. **Evaluate SubjectMode:** establish expected subject composition. `manual_subject_selection_required` always records a manual-review requirement. No mode can recover absent/cropped components.
4. **Segment:** use BiRefNet Strategy primary; rembg only by explicit fallback/reprocess policy. Never silently blend engines.
5. **Refine mask:** bounded morphology/edge feathering and hole preservation; retain raw/refined mask facts.
6. **Subject/authenticity gates:** compare component count/topology/coverage with SubjectMode and detect clipping, lost holes, disconnected fine structures, uncertain foreground, or unintended hands/tools/background objects. Ambiguity routes to review; invalid/empty output fails processing.
7. **Crop geometry:** derive foreground bounds without warping proportions; boundary-clipped/empty masks fail.
8. **Conservative correction:** bounded global/per-channel foreground-only lighting/color. No inpainting, content-aware fill, generative relighting, local reconstruction, or geometry warp.
9. **Mild cleanup:** optional bounded denoise/unsharp mask; disable/warn when text/edge proxies show damage risk.
10. **Place geometry:** uniformly scale the real foreground/mask into the 2000 × 2000 coordinate system using preset margins/anchor.
11. **Deterministic contact shadow (optional):** derive shadow only from the placed real mask, then render it behind the product onto the white canvas.
12. **Compose candidate:** composite the unchanged placed product above optional shadow. Internal candidate may be RGBA when provenance/review needs it; display preview is white-backed.
13. **Encode artifacts:** lossless candidate PNG plus optional grayscale/alpha mask and display preview; finalize atomically.
14. **Quality checks:** validate format/geometry/background, subject-mode consistency, mask topology, clipping/margins, edge/blur/noise/color deltas, shadow limits, and checksums.
15. **Finalize/route:** lock BatchImage briefly, insert CandidateVersion UUID/safe display sequence, commit provenance/QC, transition `candidate_ready`, then publish to `needs_review`.

## DeterministicContactShadowStage

The optional stage is non-generative and disabled by default until benchmark acceptance. It takes only the transformed real product mask and preset values. It creates a neutral-gray, low-opacity silhouette with bounded spread, soft blur, and small offset. It has no directional-light model and cannot sample/invent product content.

Constraints:

- product RGB/alpha pixels are never modified; the product composites above the shadow;
- opacity, blur ratio, offsets, spread, and neutral color are strictly bounded;
- the shadow cannot obscure product detail, exceed canvas bounds silently, form a strong directional cast, or create a floating appearance;
- products/packaging for which a derived shadow reduces authenticity use `shadow_enabled: false`;
- QC records mask-to-shadow geometry, opacity/extent, clipping, and a floating/overlap warning signal;
- every shadow parameter is captured in the immutable ProcessingRun preset snapshot.

## Subject Selection and Hard Cases

Background segmentation answers foreground likelihood, not which foreground objects belong to the SKU. SubjectMode supplies the business policy:

- `single_object`: one connected sellable object expected; disconnected components warn/fail routing.
- `product_with_packaging`: product and its intended packaging may remain; unrelated labels/tools do not.
- `multi_component_product`: multiple physically present components are expected and preserved.
- `keep_all_foreground_objects`: preserve all real foreground objects; still warn about photography-policy violations.
- `manual_subject_selection_required`: no automatic subject completeness claim; human review is mandatory.

Input should show one SKU and all required real parts. Hidden/cropped parts are never reconstructed. Thin cables, internal holes, transparent/white/dark products, reflective metal, packaging, and multiple disconnected objects receive specialized topology/contrast/highlight warnings. Text and geometry are never warped.

## Quality, Confidence, and Review

Technical quality is a versioned vector: decodability/dimensions, foreground coverage/margins, clipping, exact background where applicable, mask uncertainty/topology, SubjectMode signals, edge halos, blur/noise/color deltas, shadow bounds, engine signals, and provenance completeness. A calibrated routing score may prioritize the review queue.

Quality asks whether measurable rules passed. Engine confidence estimates model behavior. Neither guarantees semantic/product correctness. Every rollout-one candidate requires explicit human approval before any production export; no score or rule creates approval.

## Production Export Encoding

Export is a downstream workflow, not a BatchImage pipeline state. The exporter reads an approved immutable candidate, composites any remaining alpha over exact `#FFFFFF`, converts using the documented color profile, strips hidden transparency/unsafe metadata, and validates:

- PNG;
- exactly 2000 × 2000 pixels;
- 8-bit per channel;
- sRGB;
- RGB color type with no alpha channel;
- pure white `#FFFFFF` canvas outside the real product and any explicitly enabled bounded contact shadow.

It writes a separate ExportItem artifact and never mutates the candidate or BatchImage state.

## Source Preview

Review uses SourcePreviewArtifact to avoid repeated full-resolution source streaming. Generation reads the exact SourceObservation and applies only EXIF orientation normalization and bounded display resize. It performs no background removal, correction, crop, shadow, denoise, sharpening, or product editing. Generation/version/checksum/dimensions/MIME are recorded, host paths are never exposed, and regeneration is safe.

## Reproducibility

Each run records source-observation/checksum; SubjectMode; pipeline/stage/preset versions and validated values; shadow parameters; engine/model/checksum; dependency/build identity; device/library facts; seeds/deterministic flags; stage timings/warnings; and artifact checksums. GPU nondeterminism is recorded and tested with approved tolerances. Reprocessing creates a new run/candidate; prior versions remain immutable/selectable.
