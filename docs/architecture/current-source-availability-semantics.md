# Current Source Availability Semantics

## Purpose

This document defines only the architecture-level meaning and classification of current source availability. It establishes the present-tense question that availability answers, its time-relative operational nature, its distinction from accepted SourceObservation history, and the semantic limits that future decisions must preserve.

This document does not assign ownership or authority and does not define representation, lifecycle, persistence, or implementation.

## Definition

Current source availability answers only this present-tense operational question:

> Can the system currently obtain the source bytes associated with an exact SourceObservation through its configured storage context?

The answer is limited to current byte access in that configured context. It does not establish whether the source existed historically, whether the SourceObservation is valid, or whether the content is approved, processable, reviewed, exportable, or commercially usable.

Current source availability does not describe source identity, provenance, authenticity, or content equality. It does not determine whether bytes currently found at a locator are the bytes historically associated with the SourceObservation.

## Architectural Classification

Current source availability is operational information. It is time-relative and mutable, and it remains distinct from the accepted, durable, immutable historical source identity and provenance represented by SourceObservation.

Current source availability is not, by itself:

- an accepted historical domain fact;
- business approval;
- processing success;
- review success;
- export eligibility;
- artifact existence;
- source authenticity;
- content equality;
- permanent absence;
- deletion; or
- invalidation.

This operational classification is independent of ownership, mutation authority, persistence location, and technical representation. None of those decisions can be inferred from the classification.

## Temporal Semantics

An availability assessment is meaningful only relative to an observation time or evidence context. It describes what can be supported about current access in that temporal context, not a timeless property of the source.

A prior assessment must not automatically be treated as permanently current. Later evidence may support a different present-tense assessment without changing accepted SourceObservation history. This temporal variability does not define lifecycle states or transitions.

No freshness duration, expiration threshold, probing interval, or evidence-retention period is selected here.

## Relationship to SourceObservation

SourceObservation remains an accepted, durable, immutable historical fact even when its associated source bytes cannot currently be obtained. Current unavailability must not:

- delete the SourceObservation;
- invalidate its accepted identity;
- alter its accepted provenance;
- retarget it to another source;
- rewrite its historical path or source meaning; or
- make prior processing or export provenance false.

Current availability must not become part of SourceObservation identity. Co-location in a record, response, projection, or other representation does not make current availability an immutable identity or provenance fact.

An availability change alone must not create a new SourceObservation. Source bytes becoming inaccessible and later accessible again does not, by itself, establish a new source identity. The existing rule remains authoritative: materially changed content at the same path requires a distinct SourceObservation, while availability change alone does not.

This distinction does not define content-comparison, source-sameness, or hashing algorithms.

## Evidence and Assessment

Technical evidence and a current availability assessment are distinct. Technical evidence reports an observation or attempted interaction within a particular technical context. An availability assessment expresses the present-tense operational meaning supported by the relevant evidence context.

Non-exhaustive conceptual examples of technical evidence include:

- successful byte access;
- a missing configured storage context;
- a failed lookup;
- a permission failure;
- a disconnected drive; or
- a storage probe result.

These examples do not define evidence fields, records, commands, probes, retries, algorithms, or storage-adapter behavior.

Technical evidence does not automatically establish permanent availability truth. A successful technical observation supports only the access conclusion warranted by its evidence context, and a failed technical attempt does not prove permanent source absence. Evidence production and an availability assessment must remain distinguishable.

## Semantic Uncertainty

The semantics must preserve the difference between evidence that source bytes are currently accessible, evidence that they are currently inaccessible, and evidence that is insufficient or stale for a present-tense conclusion.

Lack of evidence is not equivalent to confirmed unavailability. Unknown or insufficient knowledge must remain semantically possible, and an old assessment must not be treated as current merely because no newer evidence exists.

Terms such as available, unavailable, and unknown describe semantic possibilities only. This document does not select status names, enum values, lifecycle states, or transition rules.

## Invariants

1. Current availability cannot redefine SourceObservation identity.
2. Current availability cannot rewrite accepted provenance.
3. Current unavailability cannot invalidate historical existence.
4. Availability change alone cannot create a new SourceObservation.
5. Technical evidence is not automatically permanent availability truth.
6. Lack of evidence is not equivalent to confirmed unavailability.
7. Availability does not establish content equality or authenticity.
8. Availability does not establish processing, review, or export success.
9. Availability semantics remain independent of storage technology.
10. Availability semantics remain independent of persistence representation.

These invariants constrain future architecture without assigning responsibility or selecting how they are enforced.

## Explicit Non-Decisions

This document does not decide:

- semantic/domain ownership of availability;
- mutation authority;
- acceptance authority;
- persistence requirement;
- persistence location;
- database fields;
- database tables;
- JSON representation;
- enum or status values;
- lifecycle states;
- state transitions;
- aggregate membership;
- transaction boundaries;
- concurrency;
- freshness duration;
- evidence retention;
- probing frequency;
- retry policy;
- reconciliation behavior;
- failure handling;
- storage-adapter behavior;
- filesystem implementation;
- API design;
- DTOs;
- commands;
- queries;
- events;
- workers;
- UI behavior;
- user messages;
- alerts;
- algorithms;
- data structures;
- design patterns;
- source code;
- tests;
- configuration; or
- CI/CD.

It also does not make Availability an entity or aggregate, add fields to SourceObservation, define a Source of Truth, or change any accepted SourceObservation classification, ownership, deployment, topology, or technology decision.

## Architectural Rationale

Separating current operational access from immutable historical truth protects provenance and auditability. A temporary disconnect, permission problem, missing mount, or stale observation cannot erase the fact that an exact source was historically observed or make prior processing and export records false.

Separating evidence from assessment prevents one technical attempt from becoming permanent truth. Preserving uncertainty avoids false claims when evidence is absent, stale, incomplete, or limited to a particular technical context.

Technology-independent semantics keep future ownership, persistence, lifecycle, API, and implementation choices open. Any later design must preserve the same present-tense meaning and must not turn mutable operational information into SourceObservation identity or a competing historical authority.
