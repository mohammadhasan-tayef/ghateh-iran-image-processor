# ADR 0010: Separate Export Lifecycle from BatchImage Lifecycle

- Status: Accepted
- Date: 2026-07-15

## Context

The original state design moved BatchImage through export-ready/exported and made Batch completion depend on export. This conflated processing/review resolution with a repeatable downstream delivery action. An approved candidate can be exported multiple times to different destinations/policies, and export failure does not invalidate processing or human approval.

## Decision

BatchImage owns only discovery, registration, processing, candidate readiness/selection, review, approval/rejection/reprocess, processing failure, and cancellation. Batch closes as `review_completed` or `partially_completed` from member processing/review resolutions, never export completion.

ExportJob and ExportItem own all export states. ExportItem references a CandidateVersion and BatchImage through same-parent composite integrity and is created only after human approval validation. One candidate may participate in multiple independent jobs. Export success, failure, skip, cancellation, or retry never changes BatchImage or Batch state. ExportJob freezes a schema-versioned naming-policy snapshot before it starts.

## Consequences

- Approved/rejected/unresolved and exported-at-least-once metrics are independently derived.
- Export can be retried/repeated/audited without corrupting processing history.
- API, database, UI, diagrams, and reconciliation must maintain two explicit lifecycles.
- Approval supersession after historical export does not erase prior export facts.

## Rejected Alternatives

Embedding export states in BatchImage prevents multiple independent jobs and misclassifies destination/storage failures as processing failures. Making Batch completion wait for export couples operational review closure to optional downstream delivery.
