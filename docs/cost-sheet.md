# PBI-011 — Cost sheet (fal Kontext Pro)

**Model:** `fal-ai/flux-pro/kontext`  
**Published unit price (verify live):** **$0.04 / image**  
**Source:** https://fal.ai/models/fal-ai/flux-pro/kontext  
**prompt_version:** `v1.0.0`

## Volume math (API only)

| Volume | Unit | Estimate |
| --- | --- | --- |
| 4 (golden spike) | $0.04 | **$0.16** |
| 50 (pilot) | $0.04 | **$2.00** |
| 100 (pilot+) | $0.04 | **$4.00** |
| 5,000 | $0.04 | **$200** |
| 10,000 | $0.04 | **$400** |

Plus retries (budget ~5–10% extra on hard failures).

## Concurrency / rate limits

- App default concurrency: **2** (safe start); raise to **4** after observing 429s.
- On HTTP 429 / 5xx: exponential backoff, max 3 retries per image.
- fal enterprise volume discounts: contact fal sales if > enterprise thresholds.

## Comparison (not V1 defaults)

| Path | ~$/img | 5k | Note |
| --- | --- | --- | --- |
| fal Kontext Pro | 0.04 | $200 | **V1 engine** |
| Kontext Dev hosts | ~0.025 | ~$125 | License risk for resale |
| Photoroom Basic | ~0.02 | ~$100+ | Cutout; may miss remake quality |
| Photoroom Plus | ~0.10 | ~$500 | More expensive |

## Spike run checklist

1. Create fal account + API key → put in `.env` as `FAL_KEY=...`
2. `pip install -r requirements.txt`
3. `python scripts/run_spike.py`
4. `python scripts/score_spike.py` then fill `docs/spike-scorecard.md`
5. Update this sheet if live price differs
