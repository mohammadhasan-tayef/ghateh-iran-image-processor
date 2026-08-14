# PBI-003 / PBI-004 — FLUX.1 Kontext Dev vs Pro + commercial license

**Decision (locked for this product):** Ship with **fal.ai FLUX.1 Kontext [pro]** only. Do **not** use Kontext [dev] weights or Dev-hosted endpoints as the sold engine.

## Variants

| Variant | Access | Typical use | Commercial for a shop-editing product? |
| --- | --- | --- | --- |
| **Kontext [pro]** | API (fal, BFL partners) | Production image editing | **Yes** — fal lists commercial use; ~$0.04/image |
| **Kontext [max]** | API | Harder multi-step edits | Yes (higher price) |
| **Kontext [dev]** | Open weights + some hosts | Research / local / non-commercial | **No** under default FLUX [dev] Non-Commercial License unless you buy a separate BFL commercial license |

## Dev license (summary)

- Source: [FLUX [dev] Non-Commercial License](https://bfl.ai/legal/non-commercial-license-terms), [BFL Kontext overview](https://docs.bfl.ai/kontext/kontext_overview), [HF LICENSE](https://huggingface.co/black-forest-labs/FLUX.1-Kontext-dev/blob/main/LICENSE.md).
- Free use is for **non-commercial / non-production** purposes.
- Selling edited catalog images to Digikala/Amazon sellers is **commercial / production**.
- Commercial use of Dev weights requires a **paid BFL commercial license** (self-serve portal at bfl.ai/licensing), separate from fal Pro API fees.

## Product rule

1. **V1 engine:** `fal-ai/flux-pro/kontext` (Pro).
2. **Do not** default to RunPod/Replicate Dev endpoints for customer batches without confirming both host ToS **and** BFL Dev commercial license.
3. Dev GGUF on a 4GB GPU remains optional learning only — not the sold pipeline.

## References

- fal Kontext Pro: https://fal.ai/models/fal-ai/flux-pro/kontext  
- BFL licensing help: https://help.bfl.ai/articles/9272590838-self-serve-dev-license-overview-pricing  
