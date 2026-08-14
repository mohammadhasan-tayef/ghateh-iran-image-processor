# Ghate Image Editor (Digikala batch)

Windows batch product-photo editor using **fal.ai FLUX.1 Kontext [pro]** (~$0.04/image).

## Quick start

1. Copy `.env.example` → `.env` and set `FAL_KEY` from https://fal.ai/dashboard/keys  
2. Install: `pip install -r requirements.txt`  
3. UI: `python run_app.py` — **Free** (local BiRefNet) or **Pro** (fal); dark/light theme  
4. Golden spike Pro: `python scripts/run_spike.py` then `python scripts/score_spike.py`  
5. Pilot: `python scripts/run_pilot.py --input PATH --limit 50`  

Free tier details: [`docs/free-tier.md`](docs/free-tier.md).  

## Layout

| Path | Purpose |
| --- | --- |
| `golden/raw` | Four raw reference photos |
| `golden/edited` | Target edited goldens |
| `golden/spike_out` | Spike API outputs |
| `docs/` | License, prompt, cost, specs, pricing, ToS |
| `src/ghate_editor/` | Prompt, fal client, export, batch, UI |

## Frozen prompt

See `docs/prompt-v1.md` (`prompt_version` **v1.0.0**).

## License note

Sold engine = **Kontext Pro via fal** only. Dev weights are non-commercial without a separate BFL license — see `docs/license-kontext.md`.
