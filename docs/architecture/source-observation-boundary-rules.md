# SourceObservation Boundary Rules

## Purpose and Scope

This document defines only the architectural responsibility boundaries of SourceObservation. It establishes what SourceObservation is responsible for, what it is explicitly not responsible for, and how adjacent concerns must remain outside its boundary.

This document does not assign ownership or define aggregates, fields, lifecycle, state machines, persistence, APIs, schemas, identifiers, algorithms, data structures, design patterns, or implementation.

## SourceObservation Responsibilities

SourceObservation is responsible only for:

1. expressing the accepted historical meaning of an exact observed source input;
2. establishing the trust boundary for the accepted source identity and provenance represented by that observation;
3. providing a stable historical source reference that downstream domain work may use without relying on a mutable location;
4. preserving the distinction between accepted source identity and the current state of a path, file, technical measurement, or execution mechanism; and
5. limiting its authority to source identity and provenance so that unrelated outcomes cannot be inferred from it.

These responsibilities describe architectural meaning only. They do not prescribe how any responsibility is represented, stored, validated, or executed.

## SourceObservation Non-Responsibilities

SourceObservation is not responsible for:

- storage concerns;
- processing concerns;
- review concerns;
- export concerns;
- execution state;
- queue state;
- worker state;
- infrastructure state;
- human decisions;
- filesystem state;
- artifact lifecycle;
- task lifecycle;
- business workflow transitions;
- retry management; or
- transaction management.

It is also not responsible for coordinating adjacent concerns, calculating their outcomes, enforcing their policies, or acting as their shared state container.

## Adjacent Concern Boundaries

Adjacent concepts must own their own responsibilities. Referring to SourceObservation does not transfer those responsibilities into SourceObservation, and SourceObservation must not absorb them merely because they use its accepted identity or provenance.

| Adjacent concern | Boundary rule |
| --- | --- |
| Storage and source access | May use the accepted source reference, but current availability, byte access, location resolution, retention, and storage health remain outside SourceObservation responsibility. |
| Processing | May identify the source input through SourceObservation, but processing configuration, execution, results, failures, and completion remain outside its responsibility. |
| Review and human action | May use source provenance for context, but human decisions, approval, rejection, and review status remain outside its responsibility. |
| Export | May rely on historical provenance, but eligibility, destination behavior, execution, and completion remain outside its responsibility. |
| Execution and coordination | May carry or refer to SourceObservation, but tasks, queues, leases, workers, retries, scheduling, and progress remain outside its responsibility. |
| Artifacts | May be related to the observed source, but artifact creation, validity, location, retention, replacement, and lifecycle remain outside its responsibility. |
| Workflow and transactions | May include operations that refer to SourceObservation, but business transitions, orchestration, transaction management, and concurrency remain outside its responsibility. |
| Infrastructure | May host or transport representations, but infrastructure availability, health, capacity, and topology remain outside its responsibility. |

This table separates responsibilities only. It does not define, classify, name, or assign ownership to any adjacent domain concept.

## Facts That Must Never Enter the Responsibility Boundary

The following facts must never become part of SourceObservation responsibility:

- whether source bytes are currently available;
- whether a filesystem path currently exists or what bytes it currently addresses;
- whether storage, a mount, a service, a worker, or other infrastructure is healthy;
- whether a task is queued, leased, running, retried, failed, cancelled, or completed;
- whether processing started, succeeded, failed, or produced a valid result;
- whether a human reviewed, approved, rejected, or otherwise decided something;
- whether anything is eligible for export or whether export succeeded;
- whether an artifact exists, is valid, is retained, or has completed its lifecycle;
- whether a business workflow may transition or has transitioned;
- whether a retry should occur or has exhausted its policy;
- whether a transaction committed, rolled back, or must be coordinated;
- how source bytes are located, read, written, copied, retained, or removed; or
- how adjacent responsibilities are implemented.

Including these facts would expand SourceObservation beyond its accepted identity-and-provenance boundary and create competing responsibility for concerns that must remain separate.

## Boundary Principles

1. SourceObservation must remain narrowly scoped to accepted source identity and provenance.
2. SourceObservation must never become a God Object or a general container for source-related, workflow, operational, or technical state.
3. Its responsibilities must remain stable even when implementation technologies change.
4. Adjacent concepts must own their own responsibilities and may not relocate them into SourceObservation for convenience.
5. A reference to SourceObservation grants no authority to redefine its meaning or expand its responsibility.
6. Technical co-location does not combine architectural responsibilities.
7. Responsibility boundaries must remain valid if execution is independently scaled or an architectural boundary is later extracted.

## Architectural Rationale

Narrow responsibility improves maintainability because changes to storage, execution, processing, review, export, or infrastructure do not force SourceObservation to change. It improves modularity by keeping accepted source identity and provenance distinct from the concerns that consume or operate around them.

The boundary strengthens auditability because SourceObservation retains one explainable meaning instead of mixing historical provenance with mutable operational outcomes. This clarity gives future aggregate design a stable responsibility seam without deciding aggregate structure here.

Explicit separation informs future transaction and persistence boundaries by showing which concerns must not be combined merely for technical convenience. It also allows later DSA decisions and design pattern decisions to follow the semantics of each concern rather than compensate for a broad, coupled model.

Stable boundaries preserve implementation flexibility. Storage mechanisms, execution topology, interfaces, and internal representations may change without redefining SourceObservation. The same separation supports future extraction or scaling while preserving its architectural meaning.

## Explicit Non-Decisions

This document does not decide:

- ownership;
- aggregate structure or membership;
- fields or metadata inventory;
- lifecycle or state transitions;
- state machines;
- persistence or storage design;
- database or transport schemas;
- APIs or DTOs;
- identifier design;
- transaction or concurrency design;
- retry or task design;
- algorithm selection;
- DSA selection;
- Design Pattern selection; or
- implementation or source code.

## Scope Boundary

Only SourceObservation responsibility boundaries are defined here. Adjacent concerns are mentioned solely to exclude them from SourceObservation responsibility; they are not designed or assigned by this document.
