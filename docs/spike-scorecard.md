# PBI-010 — Spike scorecard vs golden edited

**Status:** `PENDING_SPIKE` — tooling ready; set `FAL_KEY` and run `python scripts/run_spike.py` (~$0.16), then re-score.

Score each check: PASS / FAIL. Overall pair pass requires all PASS.

| ID | white_bg | identity | lighting | shadow | framing | logos_text | no_artifacts | overall | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| hose | _ | _ | _ | _ | _ | _ | _ | _ | |
| bosch_nozzle | _ | _ | _ | _ | _ | _ | _ | _ | |
| parskazar_bags | _ | _ | _ | _ | _ | _ | _ | _ | |
| samsung_brush | _ | _ | _ | _ | _ | _ | _ | _ | |

## Paths

### hose
- Raw: `golden/raw/hose_raw.png`
- Golden: `golden/edited/hose_edited.png`
- Spike: _(run spike)_

### bosch_nozzle
- Raw: `golden/raw/bosch_nozzle_raw.png`
- Golden: `golden/edited/bosch_nozzle_edited.png`
- Spike: _(run spike)_

### parskazar_bags
- Raw: `golden/raw/parskazar_bags_raw.png`
- Golden: `golden/edited/parskazar_bags_edited.png`
- Spike: _(run spike)_

### samsung_brush
- Raw: `golden/raw/samsung_brush_raw.png`
- Golden: `golden/edited/samsung_brush_edited.png`
- Spike: _(run spike)_

## Freeze gate

- [ ] All four pairs PASS (or documented waivers)
- [x] `prompt_version` frozen in `docs/prompt-v1.md` (`v1.0.0`)
- [ ] Proceed to production batches after visual PASS
