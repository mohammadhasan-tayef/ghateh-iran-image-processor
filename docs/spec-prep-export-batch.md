# PBI-012 / 013 / 014 — Prep, export, batch semantics

## PBI-012 — Local prep

| Step | V1 decision | Why |
| --- | --- | --- |
| EXIF orientation | Handled by Pillow on open | Avoid rotated wrong uploads |
| Resize before API | No aggressive downscale in V1; send original (fal accepts common formats) | Preserve detail for logos |
| rembg / BiRefNet pre-cut | **Not used** | Engine is Kontext Pro remake |
| Format | jpg/jpeg/png/webp/bmp/tiff | See `batch.IMAGE_EXTS` |

## PBI-013 — Export profile

| Setting | Value |
| --- | --- |
| Canvas | Square **2000×2000** |
| Background | RGB white `(255,255,255)` |
| Product fill | ~**85%** of canvas side |
| Format | JPEG quality **92** |
| Naming | `{stem}.jpg` matching input stem |

Digikala/Amazon main-image intent: pure white, product dominant, no watermark (enforced in prompt + export).

## PBI-014 — Start / Stop / resume / cache / logging

### Start

1. Validate input/output folders exist (create output if needed).
2. Require `FAL_KEY`.
3. Enumerate images; set progress 0%; clear stop flag.
4. Run worker pool (`concurrency` default 2).

### Stop

- Sets `stop_event`; in-flight jobs may finish; no new queue after flag.
- Cache flushed after each completed file.

### Resume / skip

- Cache file: `output/.ghate_cache.json` maps `filename → sha256(file+prompt_version)[:16]`.
- If output JPG exists and fingerprint matches → **skip**.
- Changing `prompt_version` invalidates fingerprints → reprocess.

### Logging

- UI log pane + `BatchState.log_lines`.
- Lines: start config, each attempt/retry, skip/ok/fail, final counts.

### Failure policy

- Per-image max **3** retries with backoff.
- Batch continues on single-image failure; final `failed` count reported.
