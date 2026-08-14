# Free tier performance & quality

**Default mode: Adaptive** (recommended for large real batches)

| Mode | Behavior |
|------|----------|
| **Adaptive** | Fast u2net @ 768 → quality gate → rescue u2net @ 1024 (boosted/gentle) → BiRefNet @ 896 if still bad |
| **Fast** | u2net only (speed) |
| **Quality** | BiRefNet always (safer edges, slower / more VRAM) |

**Why bright products washed out**
- Aggressive MinFilter erosion + contrast enhance pushed silver/white into the canvas
- Fast u2net alone often under-segments low-contrast products
- No quality gate / auto-retry

**v1.6.0 fixes**
- Heuristic mask + studio gates
- Infer-only contrast boost (does not alter final product RGB)
- Gentle edges + conservative enhance for bright scenes
- Adaptive auto-fallback with `[OK][FAST]` / `[RETRY]` / `[OK][FALLBACK]` logs

**Launch**
```text
f:\ghate image final\.venv\Scripts\python run_app.py
```
