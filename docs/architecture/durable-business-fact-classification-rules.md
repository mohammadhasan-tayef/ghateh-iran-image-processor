# Durable Business Fact Classification Rules

## Purpose and Scope

This document defines repository-wide rules for classifying information as a business fact, durable business fact, authoritative business state, derived data, ephemeral coordination state, technical observation, or artifact. The classification determines which information must remain authoritative through failure and recovery and which information may be recomputed, replaced, or lost without changing accepted business truth.

These rules are universal. They do not classify any specific aggregate, entity, workflow, module, record, artifact, or infrastructure component.

## Business Fact

A business fact is an accepted statement about the domain that has business meaning independent of its technical representation. A row, object, file, message, or cache entry is a representation and is not automatically a business fact. Technical existence alone does not make information authoritative.

A statement becomes an accepted business fact only through the responsible domain boundary and its invariants. Observation, attempted execution, transmission, persistence, or display does not by itself establish acceptance.

## Durable Business Fact

A durable business fact is an accepted business fact that must survive:

- process restarts;
- browser restarts;
- worker restarts;
- temporary infrastructure loss;
- retries; and
- ordinary recovery procedures.

Durability is required when losing the fact would:

- change accepted business history;
- make a completed decision unexplainable;
- permit an invalid duplicate action;
- prevent safe recovery;
- make an accepted result unverifiable; or
- cause the system to report a false business outcome.

Durability concerns survival and recoverability. It does not by itself require that the fact remain unchanged forever or be retained without limit.

## Authoritative Business State

Authoritative business state is the currently accepted business interpretation produced from valid durable facts and lifecycle rules. It is not determined by whichever technical representation changed most recently.

Only an authorized domain transition can establish new authoritative business state. Execution status and business status are not automatically identical, and completion of a technical operation does not by itself establish business success.

## Derived Data

Derived data is information reproducible from authoritative inputs and deterministic rules without inventing new accepted business history. It may be persisted, indexed, cached, materialized, precomputed, or regenerated.

Persistence does not automatically make derived data authoritative. Loss, replacement, or regeneration of derived data must not silently change accepted business truth. If reproduction would require an unrecorded decision, unavailable authoritative input, or non-deterministic interpretation, the information is not safely classified as derived.

## Ephemeral Coordination State

Ephemeral coordination state is temporary execution information used to schedule, lease, route, retry, throttle, coordinate, or observe work. It may disappear, be duplicated, become stale, or be reconstructed.

Ephemeral state may influence execution but must not independently establish business success or failure. It must never become the sole record of an accepted business transition.

## Technical Observation

A technical observation is measured or detected information about an input, execution, environment, or artifact. Merely measuring, detecting, or logging something does not make it authoritative.

A technical observation may become a durable business fact only when the domain requires it for identity, provenance, validation, audit, recovery, or decision-making and it is accepted through the owning boundary. Until that acceptance occurs, the observation remains evidence or input rather than accepted business truth.

## Artifact

An artifact is stored bytes or another technical output produced, observed, or retained by the system. An artifact and the business facts describing it are distinct.

Artifact existence alone does not establish approval, success, or eligibility. An artifact may later be classified as authoritative evidence, a durable output, a derived output, or temporary material, but that classification requires an explicit architecture decision. This document does not classify any specific artifact.

## Durability and Immutability

Durability and immutability are different properties. Durability describes whether accepted information must survive failure and recovery. Immutability describes whether an accepted representation or fact may be altered after creation.

A durable fact is not necessarily immutable: an authorized later transition may establish a new durable fact or authoritative state without erasing accepted history. An immutable item is not necessarily retained permanently: policy may permit its eventual removal without allowing in-place mutation while it exists.

## Classification Principles

1. Business meaning determines classification, not storage medium.
2. Persistence does not automatically create authority.
3. Immutability and durability are different properties.
4. Durable does not necessarily mean immutable.
5. Immutable does not necessarily mean permanently retained.
6. Derived data may be persisted without becoming a Source of Truth.
7. Ephemeral state may influence execution but cannot independently establish accepted business truth.
8. A successful technical step is not automatically a successful business transition.
9. A durable business fact must be accepted through an owner-controlled rule or transition.
10. A local copy, projection, read model, cache, index, log, message, or artifact does not become authoritative merely because it contains the same information.
11. Loss of ephemeral or derived information must not rewrite accepted business history.
12. Recovery must reconstruct execution from authoritative facts rather than promote temporary execution state into truth.
13. Audit information must explain accepted facts but must not become an uncontrolled second mutable source of truth.
14. Classification must remain valid if implementation technologies change.
15. Classification must remain valid if an architectural boundary is later extracted or independently scaled.

## Classification Decision Test

Future architecture decisions must apply these questions to a candidate piece of information:

1. Does the information express business meaning, or only technical execution detail?
2. Has it been accepted through a domain rule, or is it merely observed or attempted?
3. Would losing it change accepted history, eligibility, identity, provenance, recovery, or explainability?
4. Can it be reproduced exactly from authoritative inputs and deterministic rules?
5. May it safely disappear or become stale without changing business truth?
6. Is it evidence or a representation of a fact rather than the fact itself?
7. Which later ownership decision is responsible for accepting or rejecting it?

The test guides architectural classification. It is not an algorithm, code flow, database rule, state machine, or ownership assignment.

## Relationship to Domain Ownership

Classification determines the durability and authority expectations of information. Ownership determines which boundary defines meaning, invariants, lifecycle, and mutation authority. Classification does not assign ownership, and persistence location does not assign ownership.

Not every concept governed by an ownership boundary must itself be a durable business fact. Every durable business fact must ultimately be governed by one authoritative ownership boundary. A derived or ephemeral representation must not become a competing owner or Source of Truth.

## Relationship to Source of Truth

A Source of Truth is the authoritative system record from which accepted business state and history are established. Source of Truth describes authority, not merely storage.

There must not be competing mutable Sources of Truth for the same accepted fact. Queues, caches, projections, read models, logs, files, and external representations are not automatically Sources of Truth. An authoritative persistence mechanism may store business facts, but the responsible domain boundary still defines their meaning and valid transitions.

This document neither selects nor redesigns a persistence technology.

## Explicit Non-Authority Rules

None of the following becomes authoritative merely by existing:

- a UI state;
- a transport response;
- a task result;
- a queue entry;
- a lease;
- a retry counter;
- a cache entry;
- a read model;
- a search index;
- a log line;
- a metric;
- a filesystem path;
- a file's presence;
- a generated artifact;
- an ORM object; or
- an infrastructure health signal.

Any of these may represent, carry, display, measure, or provide evidence about accepted information. Authority still requires acceptance through the responsible domain boundary.

## Architectural Rationale

Clear classification enables correct recovery because the system can reconstruct execution from durable authority instead of guessing from stale coordination state. It supports idempotency and retry safety by distinguishing an accepted transition from an attempted or duplicated technical operation.

The rules improve auditability and provenance by preserving the facts required to explain accepted history and results. They provide transactional clarity by identifying which information must be committed as business truth and prevent false success when a technical operation completes without an accepted domain transition.

Separating authority from representation prevents duplicate authority and avoids cache-driven, queue-driven, ORM-driven, filesystem-driven, or artifact-driven architecture. Storage convenience, technical recency, and physical presence cannot silently redefine business meaning.

Classification supplies the information semantics needed by later decisions about persistence boundaries, transaction boundaries, algorithms, and data structures without making those decisions here. Durable, derived, and ephemeral information have different correctness, recovery, and performance requirements that later designs must respect.

These rules preserve modular-monolith boundaries by keeping accepted meaning with its authoritative owner while allowing replaceable representations and independently scaled execution. If a boundary is later extracted, its accepted facts retain the same meaning and authority instead of being reclassified according to new infrastructure.

## Scope Boundary

This document does not classify a named project concept, assign or redefine ownership, create an entity inventory, identify concrete Source of Truth records, or define persistence, retention, deletion, backup, transactions, state machines, APIs, DTOs, events, queues, caches, filesystems, artifact names, checksums, identifiers, algorithms, data structures, design patterns, source code, tests, configuration, or future Sprint work.
