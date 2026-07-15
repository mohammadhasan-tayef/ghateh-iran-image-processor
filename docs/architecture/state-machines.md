# State Machines

This document is authoritative for lifecycle states and transitions. PostgreSQL conditional transitions own business state; Celery status does not. BatchImage covers ingestion, processing, candidate selection, review, and approval only. ExportJob/ExportItem exclusively own export state.

## Batch

States: `created`, `scanning`, `scan_paused`, `queued`, `processing`, `awaiting_review`, `review_completed`, `partially_completed`, `cancelled`, `failed`.

| From | To | Trigger/guard |
|---|---|---|
| created | scanning | Start scan; configured root and expected volume are available |
| created | cancelled | Cancel before scan |
| scanning | scan_paused | Operator pause, backpressure, or mount unavailable |
| scanning | queued | Stable end reached and registered members exist |
| scanning | review_completed | Stable end reached with zero members |
| scanning | failed | Batch-level non-retryable configuration/invariant failure |
| scanning | cancelled | Cancel scan and undispatched work |
| scan_paused | scanning | Resume with valid cursor and matching volume identity |
| scan_paused | cancelled | Cancel batch |
| queued | processing | First processing run is claimed |
| queued | cancelled | Cancel queued items |
| processing | awaiting_review | No runnable work remains and at least one item needs review |
| processing | review_completed | All non-cancelled items resolved; none processing-failed/cancelled |
| processing | partially_completed | Operational closure; at least one item processing-failed/cancelled |
| processing | failed | Batch-level failure prevents meaningful item resolution |
| processing | cancelled | Cancel batch/remaining items |
| awaiting_review | processing | Reprocessing creates runnable work |
| awaiting_review | review_completed | All non-cancelled items are approved/rejected; no failed/cancelled items |
| awaiting_review | partially_completed | All remaining items resolved and at least one is processing-failed/cancelled |
| awaiting_review | cancelled | Cancel unresolved items and close batch |
| review_completed | processing | Explicit authorized `ReprocessBatchImage` command reopens a closed review cycle |
| partially_completed | processing | Explicit authorized `ReprocessBatchImage` command reopens a closed review cycle |

Resolution set for a non-cancelled BatchImage: `human_approved`, `rejected`, or `processing_failed`. Roll-up precedence is: while unresolved work exists, use an active state; when resolved, any `processing_failed` or `cancelled` member yields `partially_completed`, otherwise `review_completed`. Rejection is a successful review resolution.

`review_completed` and `partially_completed` are closed-cycle states, not permanently terminal records. They reopen only through the explicit authorized reprocess command, which atomically locks Batch and BatchImage; validates permissions, root availability, and reprocess eligibility; creates/registers the new ProcessingRun request; moves BatchImage to `reprocess_queued`; moves Batch to `processing`; increments `review_cycle`; records actor/time/reason; emits an audit/domain event containing the new cycle; and commits the outbox intent. A worker delivery alone cannot perform either reopen transition.

If Batch is already `processing`, a valid reprocess command joins the current open cycle without a Batch transition or cycle increment. If it is `awaiting_review`, the command moves it to `processing` but keeps the current cycle. Multiple reprocess requests in that open cycle likewise do not increment it. Concurrent requests serialize on the Batch row: only the first command that observes a closed-cycle state increments the cycle. `cancelled` and `failed` are permanently terminal for normal operations and reject this command. Each newly produced CandidateVersion requires a new human ReviewDecision before the reopened Batch can close again.

Export has no effect on Batch state. The UI derives approved, rejected, unresolved, failed/cancelled, and exported-at-least-once counts independently.

## BatchImage

States: `discovered`, `registered`, `queued`, `processing`, `candidate_ready`, `needs_review`, `human_approved`, `rejected`, `reprocess_queued`, `processing_failed`, `cancelled`.

| From | To | Trigger/guard |
|---|---|---|
| discovered | registered | Exact SourceObservation is validated and hashing completes |
| discovered | processing_failed | Source validation/hash fails non-retryably |
| discovered | cancelled | Batch cancelled before registration |
| registered | queued | Initial ProcessingRun/outbox created |
| registered | cancelled | Cancel before dispatch |
| queued | processing | Worker claims current run with lease |
| queued | processing_failed | Dispatch/configuration retry policy exhausted |
| queued | cancelled | Cancel before claim |
| processing | queued | Recover same nonterminal run after retryable worker/storage failure |
| processing | candidate_ready | Run finalizes its one-or-more expected immutable CandidateVersion outputs (normally one in MVP) |
| processing | processing_failed | Non-retryable processing failure or retry exhaustion |
| processing | cancelled | Cooperative cancellation before candidate commit |
| candidate_ready | needs_review | QC/provenance complete and review item published |
| needs_review | human_approved | Human approves/selects a candidate |
| needs_review | rejected | Human rejects with reason |
| needs_review | reprocess_queued | Human requests another run |
| rejected | reprocess_queued | Human requests reprocessing |
| human_approved | reprocess_queued | Human explicitly supersedes approval and requests a new run |
| reprocess_queued | processing | Worker claims new run |
| reprocess_queued | cancelled | Cancel queued reprocessing |
| processing_failed | reprocess_queued | Authorized explicit retry creates a new run |

`human_approved`, `rejected`, and `processing_failed` are review resolutions but may leave only through the documented `ReprocessBatchImage` command. That command clears the effective current selection/approval for the new cycle while preserving immutable CandidateVersions and ReviewDecisions. `cancelled` is permanently terminal. Export reservation, completion, failure, skip, cancellation, and re-export never change BatchImage or reopen Batch. Historical completed ExportJobs and previously exported approved versions remain immutable facts.

## ProcessingRun

States: `pending`, `running`, `succeeded`, `failed`, `cancelled`.

- `pending → running`: conditional claim with lease/fencing token.
- `pending → cancelled`: cancellation before claim.
- `running → succeeded`: all expected output slots finalize under short BatchImage locks with UUID CandidateVersions/safe version numbers, then run/BatchImage transition commits; MVP normally has one slot.
- `running → failed|cancelled`: typed terminal outcome before candidate commit.
- `running → pending`: stale-lease recovery only when no candidate exists.
- A retry after terminal failure creates a new run linked by `retry_of_run_id`; terminal states never reopen.

Concurrent finalizers for the same run return the existing equivalent candidate idempotently. Concurrent distinct runs serialize `version_no` allocation on BatchImage; stale lease tokens cannot commit.

## Review Decisions

Review decisions are immutable records: `approved`, `rejected`, `reprocess_requested`, and `approval_revoked`. Approval requires an eligible candidate and authorized human. Reject/reprocess/revoke requires a reason. The effective decision is the latest valid non-superseded record under a BatchImage lock. Bulk approval expands into explicit per-item decisions.

Initial rollout policy is mandatory human review for every production export. Automated scores may sort/prioritize only; they never create approval. A future auto-approval policy requires a later ADR and benchmark evidence.

## ExportJob and ExportItem

ExportJob states: `pending`, `running`, `completed`, `partially_completed`, `failed`, `cancelled`.

ExportItem states: `pending`, `running`, `completed`, `failed`, `skipped`, `cancelled`.

| Subject | Transition | Guard |
|---|---|---|
| Job | pending → running | Naming snapshot frozen; first item claimed |
| Job | pending → cancelled | Cancel before work |
| Item | pending → running | Approved candidate and destination reservation revalidated |
| Item | pending → skipped | Explicit naming/duplicate policy says no output is required |
| Item | pending → cancelled | Job/item cancellation before claim |
| Item | running → completed | Final RGB PNG atomically written and checksum recorded |
| Item | running → failed | Non-retryable/export retry exhaustion |
| Item | running → pending | Reconciliation proves no final exists and retry remains |
| Item | running → cancelled | Cooperative cancellation before final commit |
| Job | running → completed | All items completed or policy-skipped; at least one completed unless empty job policy allows otherwise |
| Job | running → partially_completed | Mixture includes completed and terminal failed/cancelled |
| Job | running → failed | No item completed and terminal failure remains |
| Job | running → cancelled | All unfinished items cancelled and none running |

A verified existing final lets redelivery complete idempotently. `skipped` is a deliberate snapshot-policy result, not a failure. One candidate can be used by multiple jobs. Export outcomes never create processing failure or alter batch closure.

## Invalid Transitions and Retries

An idempotently equivalent duplicate returns the current resource; a conflicting stale command returns `409 state_conflict` with expected/current state. Only classified transient infrastructure failures receive bounded exponential retry with jitter. Path-security, source-integrity, validation, deterministic model/decode, authenticity, and missing-model failures require explicit action. Retry mechanics are authoritative in [worker and queue design](worker-and-queue-design.md).

Reprocess validation rejects cancelled/failed Batches, cancelled or otherwise ineligible BatchImages, duplicate outstanding requests, unauthorized actors, and unavailable required storage. An identical idempotency key returns the original ProcessingRun and review cycle without another transition/event. Any task delivered for a closed Batch without a committed matching reprocess intent/current cycle is rejected or reconciled without changing Batch state.

See the [state diagrams](../diagrams/state-machines.md).
