# State Machines

This document is authoritative for lifecycle states and transitions. Commands perform conditional transitions in PostgreSQL; Celery task status never determines business state. Every transition emits an audit event.

## Batch

States: `created`, `scanning`, `scan_paused`, `queued`, `processing`, `awaiting_review`, `completed`, `partially_completed`, `cancelled`, `failed`.

| From | To | Trigger/guard |
|---|---|---|
| created | scanning | Start scan; root available |
| created | cancelled | Cancel before scan |
| scanning | scan_paused | Operator pause, backpressure, or drive unavailable |
| scanning | queued | Scan reached stable end; at least one member registered |
| scanning | completed | Empty batch accepted by operator |
| scanning | failed | Non-retryable scan/configuration failure |
| scanning | cancelled | Cancel scan |
| scan_paused | scanning | Resume; root and cursor valid |
| scan_paused | cancelled | Cancel batch |
| queued | processing | First processing run starts |
| queued | cancelled | Cancel undispatched work |
| processing | awaiting_review | No runnable processing remains; reviewable items exist |
| processing | partially_completed | Processing closed with terminal failed/cancelled items and no reviewable work |
| processing | failed | Batch-level invariant/configuration failure prevents all useful progress |
| processing | cancelled | Cancel remaining work; running tasks cooperate |
| awaiting_review | processing | Reprocess requested |
| awaiting_review | completed | Every eligible member exported or explicitly excluded under policy; no failures |
| awaiting_review | partially_completed | Operator closes with terminal failures/rejections/exclusions |

`completed`, `partially_completed`, `cancelled`, and `failed` are terminal for normal commands. An administrative clone/retry creates new work rather than mutating history. Batch roll-up is reconciled from membership states, so delivery order cannot regress a terminal state.

## Image Membership

The proposed `discovered` state is a scanner-local observation, not durable business state. Persistence begins at `registered`. `candidate_ready` is also removed: successful completion routes directly to `needs_review`.

States: `registered`, `queued`, `processing`, `needs_review`, `human_approved`, `rejected`, `reprocess_queued`, `export_ready`, `exported`, `failed`, `cancelled`.

| From | To | Trigger/guard |
|---|---|---|
| registered | queued | Initial processing run/outbox created |
| registered | cancelled | Batch cancelled before dispatch |
| queued | processing | Worker atomically claims current run |
| queued | cancelled | Cancellation before claim |
| queued | failed | Retry policy exhausted for dispatch/configuration |
| processing | needs_review | Run succeeds and candidate finalizes |
| processing | queued | Retryable infrastructure failure; same intended run redelivered or explicit retry attempt scheduled |
| processing | failed | Non-retryable error or retry exhaustion |
| processing | cancelled | Cooperative cancellation before candidate commit |
| needs_review | human_approved | Human approves a candidate |
| needs_review | rejected | Human rejects with reason |
| needs_review | reprocess_queued | Human requests another preset/engine |
| rejected | reprocess_queued | Human requests reprocessing |
| human_approved | export_ready | Export item reserves selected approved candidate |
| human_approved | reprocess_queued | Approval superseded explicitly; old decision retained |
| reprocess_queued | processing | Worker claims the new run |
| reprocess_queued | cancelled | Cancel pending reprocess |
| export_ready | exported | Atomic export verified and recorded |
| export_ready | human_approved | Export retry is abandoned/released; approval remains valid |
| export_ready | failed | Export policy exhausts retries; approval/candidate remain recorded |
| failed | reprocess_queued | Authorized manual retry with a new run |

`exported` and `cancelled` are terminal. Re-export creates a new export item without regressing the membership. A newer review decision may supersede an approval only before a reserved export starts, unless an administrator records an explicit corrective workflow.

## Processing Run

States: `pending`, `running`, `succeeded`, `failed`, `cancelled`.

- `pending → running`: conditional claim assigns lease owner/expiry.
- `pending → cancelled`: cancellation before claim.
- `running → succeeded`: artifacts finalized, checksums verified, candidate inserted in the same DB transaction.
- `running → failed`: typed terminal failure or exhausted retry policy.
- `running → cancelled`: cancellation observed before final commit.
- `running → pending`: only lease recovery for the same attempt when no candidate exists; increment delivery count and preserve diagnostics.
- `failed → pending` is invalid. A retry after terminal failure creates a new run linked by `retry_of_run_id`.

`succeeded`, `failed`, and `cancelled` are terminal. A late worker cannot overwrite a state because completion includes lease token and expected-state predicates.

## Review

Review is represented by immutable decisions rather than a mutable decision state machine. Allowed decision types are `approved`, `rejected`, `reprocess_requested`, and `approval_revoked`. Approval requires an eligible candidate and actor permission; rejection/reprocess requires a reason. The effective decision is the latest non-superseded decision under a row lock. Bulk approval expands to explicit per-image commands and audit records.

Rollout policy: all exports require an explicit `approved` decision by a human. A future policy may route high-confidence candidates differently, but a score alone never creates a human decision.

## Export Job and Item

Job states: `pending`, `running`, `completed`, `partially_completed`, `failed`, `cancelled`. Items use `pending`, `running`, `completed`, `failed`, `cancelled`.

- Job `pending → running` when the first item is claimed.
- Item `pending → running → completed|failed`; `pending|running → cancelled` cooperatively.
- A stale `running` item returns to `pending` only if reconciliation proves no final file exists. If the verified final exists, it becomes `completed` idempotently.
- Job becomes `completed` when all items complete, `partially_completed` for a mixture of completed and terminal failed/cancelled, `failed` when none complete and no retry remains, or `cancelled` when all unfinished items are cancelled.

## Invalid Transition Handling and Retries

Invalid, stale, or duplicate commands return the current representation when idempotently equivalent; otherwise they return a `409 state_conflict` with expected and actual states. Transient infrastructure errors use bounded exponential backoff with jitter. Data, validation, authenticity, missing-model, and path-security failures are not automatically retried. Retry details are authoritative in [worker and queue design](worker-and-queue-design.md).

See the [state diagram](../diagrams/state-machines.md).
