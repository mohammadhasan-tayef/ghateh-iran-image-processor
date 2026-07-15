# ADR 0007: Require Human Review Before Final Export

- Status: Accepted
- Date: 2026-07-15

## Context

Automated dimensions, mask, background, and image-quality checks cannot prove that no product text, cable, hole, reflection, or transparent component was removed. The cost of an authentic-looking but incorrect catalog image is high.

## Decision

For the first operational rollout, every final export must reference a candidate explicitly approved by an authorized human. Automated checks prioritize and warn but cannot create an approval. Bulk approval requires an explicit selected set and produces an individual decision per image. Rejection, reprocessing, approval revocation, and selecting an earlier version remain auditable.

## Consequences

- Final output has clear human accountability and the safest authenticity policy.
- Review throughput is an operational bottleneck that needs keyboard navigation, pagination, and measured staffing.
- Future confidence-based auto-approval requires a new policy decision, calibrated evidence, risk acceptance, and state/API changes; it is not enabled by a threshold configuration alone.
- A high quality/confidence score is never labeled a semantic guarantee.

## Rejected Alternatives

Automatic export after QC conflates measurable quality with correctness. Review-only-when-uncertain depends on unproven calibration and is unsafe for rollout one.
