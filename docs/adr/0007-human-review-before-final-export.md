# ADR 0007: Require Human Review Before Final Export

- Status: Accepted
- Date: 2026-07-15

## Context

Automated dimensions, mask, background, and image-quality checks cannot prove that no product text, cable, hole, reflection, or transparent component was removed. The cost of an authentic-looking but incorrect catalog image is high.

## Decision

For the first operational rollout, every production ExportItem must reference a CandidateVersion explicitly approved by an authorized human for the same BatchImage. Automated checks may prioritize/sort and warn but cannot create an approval or production-final artifact. Bulk approval requires an explicit selected set and produces one human decision per image. Rejection, reprocessing, approval revocation, and selecting an earlier version remain auditable. Future auto-approval requires a new ADR plus benchmark/calibration and risk evidence; configuration alone cannot enable it.

## Consequences

- Final output has clear human accountability and the safest authenticity policy.
- Review throughput is an operational bottleneck that needs keyboard navigation, pagination, and measured staffing.
- Batch review resolution remains independent from export completion; one approved candidate may be used by multiple export jobs.
- A high quality/confidence score is never labeled a semantic guarantee.

## Rejected Alternatives

Automatic export after QC conflates measurable quality with correctness. Review-only-when-uncertain depends on unproven calibration and is unsafe for rollout one.
