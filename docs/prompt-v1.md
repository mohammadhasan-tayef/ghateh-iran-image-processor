# PBI-005 — Frozen V1 ecommerce prompt

**prompt_version:** `v1.0.0`  
**Model:** `fal-ai/flux-pro/kontext`  
**Source of truth in code:** `src/ghate_editor/prompt.py`

## Prompt (frozen)

```
Replace the entire background with a seamless pure white (#FFFFFF) ecommerce studio backdrop. Keep the exact same product with identical shape, materials, colors, logos, printed text, and fine texture. Do not invent, remove, or reshape any product parts. Apply soft, even studio lighting; clean dust and clutter; preserve natural material detail. Add a subtle soft contact shadow under the product where it meets the surface (very light and diffuse). Center the product and keep it large in the frame (about 70-85% of the image). No props, no watermarks, no text overlays, no gradients, no floor or room visible.
```

## Acceptance (from golden pairs)

1. Seamless `#FFFFFF` — no table, floor, people, chairs, shelves.
2. Product identity preserved; logos/text readable (BOSCH, SAMSUNG, Parskazar, etc.).
3. Soft studio lighting; blacks deep but not crushed.
4. Soft contact shadow OK; Samsung may be near-shadowless — prefer subtle over harsh.
5. Product large/centered; later export square ~2000×2000 JPG.
6. No watermarks / extra props.

## Change control

Bump `prompt_version` and update `PROMPT_VERSION` in code whenever this text changes. Spike scorecard must re-run on all four golden raws after any bump.
