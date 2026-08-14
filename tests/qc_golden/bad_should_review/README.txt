Place human-verified BAD edited finals here.

These images must NOT silently PASS under the production QC path.

Examples:
- actual missing product regions
- large contiguous product wipe
- white-out / washed translucent parts
- fragmented foreground
- severe halo / background contamination
- destroyed edges

Pairing: matching RAW/HEIC from GHATE_RAW_DIR or E:\ghateh iran\aks kham.

Run:
  python scripts/test_qc_golden.py
  python scripts/run_qc_golden.py --dir tests/qc_golden
