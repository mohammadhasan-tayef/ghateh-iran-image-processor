# Calibration set (NOT used in production batches)

Place representative examples here to tune QualityGateConfig:

calibration/good/   — known-excellent ecommerce outputs (or source→expect Approve)
calibration/bad/    — known-broken / disappearing-product sources (expect Review)

Then run:
  python scripts/score_calibration.py

Scores include source↔output structure_loss. Do not point production Input Folder at this directory.
