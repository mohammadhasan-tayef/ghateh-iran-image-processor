# SourceObservation Classification

## Purpose and Scope

This document applies the repository-wide durable-business-fact classification rules to SourceObservation only. It classifies SourceObservation by business meaning, durability, authority, immutability, provenance significance, relationship to source bytes and technical observations, and recoverability requirements.

This classification does not assign ownership or define lifecycle, persistence, algorithms, data structures, design patterns, or implementation.

## Classification Decision

SourceObservation is:

1. an accepted domain observation;
2. a durable business fact;
3. an immutable historical fact after acceptance;
4. authoritative for the identity and provenance of the exact source input observed;
5. not authoritative merely because a file, path, cache entry, queue message, task result, or metadata reading exists;
6. distinct from the source bytes or artifact it describes;
7. distinct from the current state of a filesystem path;
8. not derived data;
9. not ephemeral coordination state; and
10. not itself proof of processing success, review approval, export eligibility, or export success.

## Business Meaning

SourceObservation is the accepted historical statement that a particular source input was observed and that its accepted identity and provenance facts correspond to that observation. It gives downstream domain work a stable reference to the exact observed source rather than an ambiguous mutable location.

The observation remains historically meaningful if the external path later changes, disappears, or points to different bytes. SourceObservation represents accepted source identity and provenance; it is not merely evidence that a scan or measurement was attempted.

## Durability

SourceObservation is a durable business fact because losing or silently replacing it could:

- make prior processing inputs unexplainable;
- break provenance;
- make retries or reprocessing refer to a different source;
- allow existing work to be reinterpreted against changed bytes;
- make audit and recovery unreliable; or
- make accepted historical relationships unverifiable.

An accepted SourceObservation must survive ordinary process restarts, worker restarts, retries, temporary infrastructure failure, and recovery procedures. This durability requirement does not define backup or retention policy.

## Immutability

An accepted SourceObservation is immutable. Its accepted observation identity and provenance facts are not rewritten in place.

Later source changes do not mutate or retarget the existing observation. Newly observed materially different source content requires a distinct observation. If correction of an invalid accepted observation is ever supported, it must preserve historical explainability and be designed through a separate lifecycle decision.

Immutability here applies after acceptance. This classification does not define an acceptance transition, correction command, supersession model, version number, state transition, or exact source-sameness method.

## Authority Boundary

SourceObservation is authoritative for:

- the accepted identity of the observed source input;
- the provenance facts required to identify and explain that observation; and
- the historical source reference used by downstream domain work.

SourceObservation is not authoritative for:

- the current contents of a mutable path;
- physical file availability at the present moment;
- task execution status;
- processing completion;
- candidate validity;
- human approval;
- export eligibility;
- export completion;
- storage health; or
- infrastructure health.

The presence or recency of a technical representation does not expand this authority boundary.

## Relationship to Source Bytes

Source bytes are the external or stored bytes that were observed. SourceObservation is the accepted durable fact describing the identity and provenance of that exact observed source input. The bytes and the durable facts describing them are distinct.

File existence alone does not create an accepted SourceObservation, and path equality alone does not prove source sameness. Disappearance of the bytes does not retroactively erase the historical observation, while the observation does not guarantee that the bytes remain currently accessible.

Downstream work must not silently substitute different bytes for the accepted observation. This classification does not require content-addressable storage, define byte-retention requirements, or select checksum implementation.

## Relationship to Technical Observations

Raw measurements such as size, modification time, media metadata, dimensions, detected format, a checksum result, or another observed characteristic begin as technical observations.

They become part of authoritative SourceObservation meaning only when accepted according to the responsible domain rules. Measurement alone is not authority, and logging a measurement does not establish a durable fact. Preliminary sameness evidence is not necessarily final identity authority.

This classification does not decide which measurements are mandatory, define a field inventory, or select a measurement or sameness algorithm.

## Relationship to Derived and Ephemeral Information

SourceObservation itself is not:

- derived data;
- a cache;
- a projection;
- a read model;
- a queue record;
- a task result;
- a lease;
- a retry marker; or
- transient scan progress.

Derived or ephemeral representations may refer to a SourceObservation, but they cannot replace its authority or become a competing mutable Source of Truth.

## Same-Path Change Rule

> Materially changed source content at the same path must not retarget an existing SourceObservation.

The path is a locator, not permanent content identity. An existing observation remains tied to the source identity it originally accepted. Materially different later content requires a distinct accepted observation, and historical downstream references remain attached to the original observation.

This classification consequence does not define which metadata proves material change, checksum or hashing strategy, scan or deduplication algorithms, race handling, locking, or transaction behavior.

## Classification Decision Test

| Classification question | SourceObservation answer | Architectural consequence |
| --- | --- | --- |
| Does the information express business meaning or only technical execution detail? | It expresses the accepted identity and provenance of an observed source input. | It is an accepted domain observation rather than mere scan or execution detail. |
| Has it been accepted through a domain rule, or is it merely observed or attempted? | SourceObservation exists as business authority only after acceptance through responsible domain rules. | Raw measurements and attempted observations do not independently establish it. |
| Would losing it change accepted history, eligibility, identity, provenance, recovery, or explainability? | Losing it would damage source identity, provenance, recovery, and historical explainability. | It must be durably preserved as an accepted business fact. |
| Can it be reproduced exactly from authoritative inputs and deterministic rules? | It cannot be safely reconstructed from a mutable path alone because the path or bytes may have changed or disappeared. | It is not classified as derived data. |
| May it safely disappear or become stale without changing business truth? | No. Its loss or silent replacement would change or obscure accepted historical truth. | It is not ephemeral coordination state. |
| Is it evidence or a representation of a fact rather than the fact itself? | It is the accepted fact describing observed source identity and provenance; files, paths, measurements, and records are representations or evidence. | Technical existence alone cannot establish or replace its authority. |
| Which later ownership decision is responsible for accepting or rejecting it? | Ownership remains a separate accepted or later architectural decision and is not assigned here. | Classification establishes authority and durability expectations without assigning module ownership. |

## Classification-Level Invariants

1. An accepted SourceObservation remains historically stable.
2. Existing downstream references do not silently retarget.
3. A mutable locator does not redefine accepted source identity.
4. Technical execution state cannot establish or replace SourceObservation authority.
5. Derived representations cannot become competing mutable Sources of Truth.
6. SourceObservation authority is limited to source identity and provenance.
7. SourceObservation does not imply processing, review, or export success.

These are classification invariants only. They do not define enforceable transitions, persistence constraints, or implementation mechanisms.

## Architectural Rationale

This classification preserves reproducibility by keeping downstream work connected to the exact accepted source identity rather than whichever bytes happen to occupy a location later. It preserves provenance and auditability because prior work remains explainable even after external storage changes.

Durability and immutability enable safe retries, reprocessing, and recovery without accidental source substitution. They prevent path-driven identity and filesystem-driven architecture by ensuring that a mutable locator or present file cannot silently redefine historical truth.

The limited authority boundary prevents source identity from being confused with execution, review, export, storage, or infrastructure outcomes. It also prevents temporary technical state or derived representations from becoming competing business authority.

This classification provides information semantics for later transaction-boundary, persistence-boundary, algorithm, and data-structure decisions without selecting them. It supports modular-monolith boundaries by making the durable source reference explicit while leaving ownership and implementation to their authoritative decisions.

## Explicit Non-Decisions

This Sprint does not decide:

- SourceObservation module ownership;
- aggregate root status;
- aggregate membership;
- entity versus value-object modeling;
- exact fields;
- identifier type;
- source-sameness algorithm;
- hashing algorithm;
- checksum policy;
- metadata requirements;
- database schema;
- ORM model;
- indexes;
- uniqueness constraints;
- retention;
- deletion;
- correction workflow;
- supersession;
- lifecycle transitions;
- state machine;
- transaction boundary;
- locking;
- concurrency control;
- repository interface;
- Unit of Work;
- Domain Events;
- Outbox;
- API;
- DTO;
- worker behavior;
- filesystem layout;
- storage implementation;
- DSA selection;
- Design Pattern selection; or
- source code.

## Scope Boundary

Only SourceObservation is classified by this document. References to files, paths, bytes, measurements, execution outcomes, review, export, storage, infrastructure, and technical representations exist solely to limit what SourceObservation means and does not positively classify those adjacent concepts.
