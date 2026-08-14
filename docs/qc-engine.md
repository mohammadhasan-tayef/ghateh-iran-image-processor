# QC Engine v3 (free-v1.14.0) — RAW-aware integrity

## Audit summary

| Item | Detail |
|------|--------|
| Entry | `classify_quality` → `build_qc_report` |
| Routing | PASS→Approved (`high_good`), SECOND_PASS→Adaptive rescue, REVIEW→Review |
| Old false PASS | Structure prior was **mask-dependent**; wiped light product never entered loss; clean white bg + dark remnant → PASS |
| Old false REVIEW | Hard caps (frag@54, structure_warn@72), multi-object kits |

## v3 core change

Independent **RAW vs FINAL** comparison via `qc_raw_final.compute_raw_final_integrity`:

1. Estimate product prior from RAW **without** trusting the processing mask
2. Measure how much of that prior survives in the cutout alpha
3. Detail / edge / white-out scores inside that prior
4. These scores dominate **core** (blend 0.85)

## Core formula

```
core = weighted(
  structure_preservation  0.18
  detail_retention        0.14
  foreground_overexposure 0.14
  object_completeness     0.14
  raw_final_edge_consist. 0.12
  edge_integrity          0.10
  segmentation_confidence 0.08
  background_purity       0.06
  color_preservation      0.04
) ⊕ halo(8%)

aesthetic = weighted(composition, exposure, sharpness, shadow)
final = 0.85 * core + 0.15 * aesthetic
```

PASS requires integrity floors:

- `raw_final_integrity >= 62`
- `structure_preservation >= 58`
- `foreground_overexposure >= 55`

Destruction tags (`product_structure_destroyed`, `product_whiteout`, …) **block PASS**.

## Fatal rejects

empty / washed / faded / whiteout / structure destroyed / detail destroyed /
tiny foreground / integrity collapse ≤ 28

## Tests

```powershell
.\.venv\Scripts\python scripts\test_qc_golden.py
```

Place verified samples in:

- `tests/qc_golden/good_should_pass/`
- `tests/qc_golden/bad_should_review/`

## Tune

`src/ghate_editor/qc_config.py` only.
