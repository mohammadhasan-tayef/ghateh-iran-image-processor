"""Analyze E:\\final\\QC diagnostics for false-review root causes."""
from __future__ import annotations

import json
import statistics as st
from collections import Counter, defaultdict
from pathlib import Path

qc_dir = Path(r"E:\final\QC")
rows = []
for p in qc_dir.glob("*.json"):
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        d["_path"] = p.name
        rows.append(d)
    except Exception:
        continue

print("total_qc_json", len(rows))
dec = Counter(str(r.get("decision") or "?") for r in rows)
print("decisions", dict(dec))

by_dec: dict[str, Counter] = defaultdict(Counter)
bads_by: dict[str, Counter] = defaultdict(Counter)
for r in rows:
    d = str(r.get("decision") or "?")
    for t in r.get("triggered_rules") or []:
        by_dec[d][t] += 1
    for t in r.get("bads") or []:
        bads_by[d][t] += 1

for d in sorted(by_dec.keys()):
    print(f"\n=== decision={d} top triggered ===")
    for k, v in by_dec[d].most_common(18):
        print(f"  {v:4d}  {k}")
    print("--- bads ---")
    for k, v in bads_by[d].most_common(15):
        print(f"  {v:4d}  {k}")

for d in ["pass", "second_pass", "review"]:
    scores = [float(r.get("final_score") or 0) for r in rows if str(r.get("decision")) == d]
    if scores:
        print(
            f"score {d}: n={len(scores)} mean={st.mean(scores):.1f} "
            f"med={st.median(scores):.1f} min={min(scores):.1f} max={max(scores):.1f}"
        )

# Cross-tab: review with fragmentation / structure / fog
keys = [
    "mask_fragmented_bad",
    "structure_loss_hard",
    "structure_loss_soft",
    "foggy_mask",
    "mask_near_full_frame",
    "catastrophic_structure_loss",
    "edge_haze",
    "soft_alpha_edges",
]
rev = [r for r in rows if str(r.get("decision")) == "review"]
print("\n=== review rule co-occurrence ===")
for k in keys:
    n = sum(1 for r in rev if k in (r.get("triggered_rules") or []))
    print(f"  {n:4d}/{len(rev)}  {k}")

# Instant rejects
inst = [r for r in rev if float(r.get("final_score") or 0) <= 25]
print("\nlikely_instant_or_floor", len(inst))
inst_bads = Counter()
for r in inst:
    for b in r.get("bads") or []:
        inst_bads[b] += 1
print("instant bads", inst_bads.most_common(10))

# Sample high-score reviews (borderline false review candidates)
near = sorted(
    [r for r in rev if float(r.get("final_score") or 0) >= 50],
    key=lambda r: float(r.get("final_score") or 0),
    reverse=True,
)[:8]
print("\n=== high-score REVIEW samples (likely false review) ===")
for r in near:
    print(
        r.get("file") or r.get("_path"),
        "score=",
        r.get("final_score"),
        "bads=",
        r.get("bads"),
        "trig=",
        (r.get("triggered_rules") or [])[:8],
        "subs=",
        {k: round(float(v), 1) for k, v in (r.get("subscores") or {}).items()},
    )
