# Studio Processing Pipeline (free-v1.12.0)

Local, offline post-segmentation engine that upgrades cutout quality without rewriting the GUI.

## Enable / disable

| Env var | Effect |
|---------|--------|
| *(default)* | New studio engine ON |
| `GHATE_LEGACY_COMPOSE=1` | Old `compose_studio_square` / `enhance_product` path |
| `GHATE_DEBUG=1` | Write debug bundles under `GHATE_DEBUG_DIR` (default `output/debug`) |
| `GHATE_DEBUG_DIR=path` | Debug root directory |

## Modules

```
src/ghate_editor/processing/
  config.py           # ProcessingConfig knobs
  analyzer.py         # ImageAnalysis
  profiles.py         # ProductProfile heuristics
  mask_refinement.py  # confidence, refine, ensemble
  edge_refinement.py  # edges, halo, shadow strip
  color.py            # adaptive exposure/WB + ΔE guard
  enhancement.py      # adaptive denoise/sharpen
  composition.py      # shape-aware 2000² white canvas
  studio_pipeline.py  # orchestration
  report.py           # processing_report.jsonl/csv
  debug_io.py         # debug artifacts
```

## Tune parameters

Edit `ProcessingConfig` in `src/ghate_editor/processing/config.py`:

- `max_delta_e`, `max_exposure_gain`, `decontam_strength*`
- `product_fill_min/max`, `conf_second_model`, `denoise_*`, `sharpen_*`

## Tests

```powershell
.\.venv\Scripts\python tests\test_studio_processing.py
.\.venv\Scripts\python scripts\run_qc_golden.py
```

## Reports

Each batch writes:

- `output/processing_report.jsonl`
- `output/processing_report.csv`
