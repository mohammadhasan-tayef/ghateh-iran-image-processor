# QC golden samples (regression)

Place files here:

tests/qc_samples/good_should_pass/
  Edited studio JPGs or source HEICs that should PASS (Approved).

tests/qc_samples/bad_should_review/
  Destroyed / incomplete cutouts that must NOT PASS.

If these folders are empty, `scripts/run_qc_golden.py` falls back to
`calibration/good` and `calibration/bad`.

Run:
  .venv\Scripts\python scripts\run_qc_golden.py
