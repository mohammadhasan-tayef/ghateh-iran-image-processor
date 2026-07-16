# SourceObservation Ownership Authority

## Purpose

This document defines the ownership-authority consequences of Assets being the sole semantic/domain owner of SourceObservation while Storage catalog remains a non-owning operational boundary.

These rules are normative, implementation-neutral, and limited to semantic authority, acceptance authority, mutation-authority restrictions, technical-evidence authority, and cross-boundary consumption authority. They do not reconsider the accepted ownership decision or define implementation mechanisms.

## Accepted Ownership Baseline

Assets is the sole semantic/domain owner of SourceObservation. That ownership is singular and includes authority over SourceObservation domain meaning, accepted source identity and provenance, historical interpretation and stability, invariants, acceptance or rejection of proposed SourceObservation facts, prevention of silent retargeting, and authoritative interpretation of an accepted SourceObservation.

Storage catalog is not a semantic/domain owner, co-owner, or secondary owner of SourceObservation. It retains operational responsibility for configured roots, root activation, safe source locators and keys, source discovery, source-byte access, current-location resolution, source previews, storage and discovery adapters, technical source evidence, and observation or supply of current availability information.

Storage catalog may provide technical evidence or propose a SourceObservation candidate for Assets consideration. It may not independently establish accepted SourceObservation meaning.

## Authority Model

### Semantic Authority

Only Assets may authoritatively define what a SourceObservation means, which facts form accepted SourceObservation identity and provenance, which invariants an accepted SourceObservation must preserve, and how an accepted SourceObservation is interpreted historically.

Another boundary may consume accepted meaning but must not reconstruct, broaden, narrow, replace, or maintain competing SourceObservation meaning.

### Acceptance Authority

Only Assets may accept or reject a proposed SourceObservation domain fact. Storage catalog may discover source material, collect technical observations, calculate or supply technical evidence, and submit a proposal or request for consideration. Submission, transmission, persistence, or technical completion does not create acceptance authority.

### Mutation Authority

Accepted SourceObservation-owned state must not be directly mutated by Storage catalog or another consuming boundary. A request that affects SourceObservation-owned state must preserve Assets authority, and no consumer may bypass Assets invariants or make a local copy an independently mutable Source of Truth.

These restrictions define authority only. They do not select a command, service, transaction, repository, event, API, message, or other implementation mechanism.

### Evidence Authority

Storage catalog may be authoritative for a technical observation it directly performs within its operational scope, including what a configured source adapter observed, whether byte access succeeded at an observation time, technical measurements supplied for consideration, and current storage or location information.

Technical-evidence authority is limited to the observation made. It does not make the evidence an accepted SourceObservation fact, create SourceObservation ownership, silently redefine accepted identity or provenance, or make the evidence producer the semantic owner of a resulting domain fact.

### Cross-Boundary Consumption Authority

Other boundaries may reference an accepted SourceObservation through its stable identity, consume accepted facts needed for their own behavior, request SourceObservation-related behavior through an explicit boundary, and retain non-authoritative projections or snapshots only where accepted architecture permits.

Consumption does not transfer semantic, acceptance, or mutation authority. A consumer must not directly mutate SourceObservation-owned state, reproduce SourceObservation acceptance rules, infer a new identity from a local copy, reinterpret provenance, retarget an existing reference, or treat a read model, projection, cache, foreign key, or copied field as an independent Source of Truth.

## Assets Authority

Assets exclusively retains authority to:

- define SourceObservation domain meaning;
- define which accepted facts establish source identity and provenance;
- define and preserve SourceObservation invariants;
- accept or reject proposed SourceObservation domain facts;
- interpret accepted SourceObservation facts historically;
- preserve accepted historical stability;
- prevent silent retargeting of an accepted SourceObservation;
- determine that materially different source content requires a distinct SourceObservation; and
- reject evidence, proposals, requests, or representations that do not preserve accepted meaning and invariants.

Assets authority does not require Assets to perform source discovery, source-byte access, adapter operations, preview generation, root activation, or other Storage catalog operational responsibilities. Operational performance by another boundary does not transfer or divide Assets authority.

## Storage Catalog Operational Authority

Storage catalog may:

- manage configured-root and root-activation concerns;
- manage safe source locators and keys;
- discover source material;
- resolve current source locations;
- provide source-byte access;
- manage source previews;
- operate storage and discovery adapters;
- collect, calculate, and supply technical source evidence;
- observe or supply current availability information; and
- propose a SourceObservation candidate or request consideration by Assets.

Storage catalog must not:

- define or redefine SourceObservation domain meaning;
- accept or reject a SourceObservation domain fact;
- treat discovery, byte access, location, or technical evidence as automatic domain acceptance;
- directly mutate SourceObservation-owned state;
- bypass Assets invariants;
- silently redefine accepted source identity or provenance; or
- become a co-owner, secondary owner, or competing Source of Truth for SourceObservation.

Storage catalog may observe or supply current availability information or technical evidence. Doing so does not create SourceObservation ownership or direct mutation authority over SourceObservation-owned state, and current availability information must not redefine accepted SourceObservation identity or provenance.

Whether Availability belongs to SourceObservation or is separate, who owns it, whether it is persisted, whether it is historical or current state, its acceptance rules, lifecycle, representation, mutation authority, and transaction boundaries remain deferred.

## Technical Evidence and Domain Acceptance

Technical evidence records or reports an operational observation. An accepted SourceObservation domain fact is a statement recognized by Assets as authoritative within SourceObservation meaning and invariants. These are distinct authority categories.

Storage catalog may establish what it directly observed within its operational scope and may supply that evidence for consideration. The evidence remains technical evidence unless and until Assets accepts a proposed SourceObservation fact. Evidence production, evidence quality, technical completion, storage, recency, or successful access does not independently establish domain acceptance.

Acceptance by Assets does not transfer semantic ownership to the evidence producer. Rejection or non-acceptance does not invalidate that a technical observation occurred; it means only that the evidence did not establish an accepted SourceObservation fact. Neither outcome expands Storage catalog authority beyond its operational boundary.

No technical observation, path, file, adapter result, preview, current-location report, availability report, read model, projection, cache, foreign key, or copied field may silently replace or redefine accepted SourceObservation identity and provenance.

## Cross-Boundary Access

A consuming boundary may:

- reference an accepted SourceObservation by stable identity;
- rely on accepted identity and provenance facts within their defined meaning;
- request behavior that affects SourceObservation through an explicit Assets boundary; and
- retain a non-authoritative projection or snapshot only where accepted architecture permits.

A consuming boundary must:

- preserve Assets as the sole semantic/domain owner;
- preserve accepted SourceObservation meaning and historical interpretation;
- keep local representations subordinate to accepted SourceObservation authority;
- keep requests subject to Assets acceptance and invariant authority; and
- preserve an existing reference rather than silently retarget it.

A consuming boundary must not:

- directly mutate SourceObservation-owned state;
- reproduce or independently apply SourceObservation acceptance rules;
- infer authoritative SourceObservation identity from its local representation;
- reinterpret accepted provenance;
- treat relationship direction, cardinality, aggregate grouping, persistence placement, or technical co-location as ownership;
- make a local representation an independently mutable Source of Truth; or
- infer semantic, acceptance, or mutation authority from access.

These rules do not prescribe transport, data-access, persistence, or communication mechanisms.

## Ownership-Authority Invariants

1. SourceObservation has exactly one semantic/domain owner: Assets.
2. Only Assets defines accepted SourceObservation meaning and invariants.
3. Only Assets accepts or rejects proposed SourceObservation domain facts.
4. Technical evidence is not automatically an accepted domain fact.
5. Discovery does not create ownership.
6. Byte access does not create ownership.
7. Storage location does not create ownership.
8. Persistence location does not create ownership.
9. Relationship cardinality does not create ownership.
10. Aggregate grouping does not create ownership.
11. A consumer cannot directly mutate SourceObservation-owned state.
12. A consumer cannot create a competing mutable Source of Truth.
13. An accepted SourceObservation cannot be silently retargeted.
14. Materially different source content cannot be represented by silently changing an accepted SourceObservation.
15. Current availability information cannot redefine accepted identity or provenance.
16. Cross-boundary access does not transfer semantic, acceptance, or mutation authority.

## Explicit Non-Decisions

This document does not decide:

- Aggregate Root status;
- aggregate membership;
- aggregate boundaries;
- entity versus value-object modeling;
- SourceObservation fields;
- evidence fields;
- identifiers;
- source-sameness algorithms;
- preliminary sameness rules;
- hashing algorithms;
- checksum policy;
- Availability ownership;
- Availability mutation authority;
- lifecycle states;
- lifecycle transitions;
- correction workflows;
- supersession;
- deletion;
- retention;
- persistence technology;
- database schema;
- ORM models;
- foreign keys;
- indexes;
- transaction boundaries;
- Unit of Work;
- Repository Pattern;
- concurrency;
- locking;
- Domain Events;
- Outbox;
- API;
- DTO;
- commands;
- queries;
- application services;
- workers;
- queues;
- filesystem layout;
- storage layout;
- algorithms;
- data structures;
- Design Patterns; or
- implementation.

## Architectural Rationale

Singular semantic authority prevents operational evidence, persistence placement, technical co-location, and cross-boundary access from creating competing interpretations of SourceObservation. Assets can preserve one authoritative meaning for accepted source identity and provenance while Storage catalog remains focused on source-access and evidence-producing responsibilities.

Separating technical evidence from domain acceptance preserves auditability. The architecture can explain what Storage catalog observed, what Assets accepted, and why an accepted SourceObservation remains authoritative without treating a successful technical operation as business truth.

Explicit mutation-authority restrictions preserve invariants and historical stability. They prevent consumers from bypassing Assets, silently retargeting accepted observations, or turning local copies into competing mutable Sources of Truth.

These rules preserve modular-monolith boundaries while remaining valid under future extraction and scaling. Technology, storage, transport, deployment, and execution choices may change without transferring SourceObservation semantic, acceptance, or mutation authority.

## Scope Boundary

This document defines only the authority consequences of the accepted SourceObservation ownership baseline. It does not redesign Assets or Storage catalog, assign shared or secondary ownership, assign persistence ownership, create or rename a module, alter module dependencies, or design Availability.

It introduces no aggregate, entity/value-object, field, identifier, lifecycle, state-machine, persistence, schema, transaction, concurrency, API, DTO, command, query, event, algorithm, data-structure, Design Pattern, implementation, source-code, test, configuration, CI, ADR, or diagram decision. All such matters remain governed by existing accepted architecture or deferred to separately approved Micro Sprints.
