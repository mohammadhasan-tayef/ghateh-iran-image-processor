#!/usr/bin/env python3
"""Print side-by-side paths for manual scoring vs goldens; write scorecard stub."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "golden" / "spike_out" / "spike_manifest.json"
SCORECARD = ROOT / "docs" / "spike-scorecard.md"

CHECKS = [
    "white_bg",
    "identity",
    "lighting",
    "shadow",
    "framing",
    "logos_text",
    "no_artifacts",
]


def main() -> int:
    if not MANIFEST.exists():
        print("No spike_manifest.json — run scripts/run_spike.py first (needs FAL_KEY).")
        print("Writing empty scorecard template anyway.")
        entries = [
            {"id": s}
            for s in (
                "hose",
                "bosch_nozzle",
                "parskazar_bags",
                "samsung_brush",
            )
        ]
        status = "PENDING_SPIKE"
    else:
        entries = json.loads(MANIFEST.read_text(encoding="utf-8"))
        status = "AWAITING_HUMAN_SCORE"

    lines = [
        "# PBI-010 — Spike scorecard vs golden edited",
        "",
        f"**Status:** `{status}`",
        "",
        "Score each check: PASS / FAIL. Overall pair pass requires all PASS.",
        "",
        "| ID | white_bg | identity | lighting | shadow | framing | logos_text | no_artifacts | overall | notes |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for e in entries:
        eid = e["id"]
        cells = " | ".join(["_"] * len(CHECKS))
        lines.append(f"| {eid} | {cells} | _ | |")

    lines.extend(
        [
            "",
            "## Paths",
            "",
        ]
    )
    for e in entries:
        eid = e["id"]
        lines.append(f"### {eid}")
        if "spike_jpg" in e:
            lines.append(f"- Spike: `{e['spike_jpg']}`")
            lines.append(f"- Golden: `{e['edited_golden']}`")
            lines.append(f"- Raw: `{e['raw']}`")
        else:
            lines.append(f"- Raw: `golden/raw/{eid}_raw.png`")
            lines.append(f"- Golden: `golden/edited/{eid}_edited.png`")
            lines.append("- Spike: _(run spike)_")
        lines.append("")

    lines.extend(
        [
            "## Freeze gate",
            "",
            "- [ ] All four pairs PASS (or documented waivers)",
            "- [ ] `prompt_version` frozen in `docs/prompt-v1.md`",
            "- [ ] Proceed to Windows app (PBI-015+)",
            "",
        ]
    )
    SCORECARD.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {SCORECARD}")
    for e in entries:
        print(e.get("id"), e.get("spike_jpg", "(no spike yet)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
