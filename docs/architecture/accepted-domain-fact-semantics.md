# Accepted Domain Fact Semantics

## Purpose and Scope

This document defines only the architectural semantics of an Accepted Domain Fact. It explains what it means for a proposed domain statement to become accepted, what acceptance establishes, what it does not establish, and how acceptance relates to business truth.

This document does not assign ownership or define lifecycle states, state machines, aggregates, entities, modules, persistence, transactions, APIs, schemas, identifiers, algorithms, data structures, design patterns, or implementation.

## Accepted Domain Fact

An Accepted Domain Fact is a statement with domain meaning that has been recognized as valid under the applicable business meaning and invariants and may therefore be relied upon as authoritative business truth within its defined semantic scope.

Acceptance distinguishes an authoritative business statement from an observation, proposal, attempt, representation, or technical result that has not acquired domain authority. Acceptance concerns the business meaning of the statement, not the technology or mechanism through which it is represented.

## What Acceptance Means

Acceptance means that the responsible domain authority has recognized a proposed statement as satisfying the applicable rules for business validity. The statement is no longer merely asserted, observed, attempted, transmitted, calculated, or displayed; it is authoritative within the limits of what it says.

Acceptance is a semantic determination. This document does not define who owns a particular fact, which operation performs acceptance, when it occurs in a lifecycle, or how an implementation records or enforces it.

## What Acceptance Establishes

Acceptance establishes that:

- the statement has recognized business meaning;
- the statement may be treated as authoritative business truth within its semantic scope;
- other architectural concerns may rely on the accepted meaning without redefining it;
- the statement may contribute to accepted business history or interpretation where separately applicable; and
- technical representations of the statement do not gain independent authority merely by containing it.

Acceptance establishes authority for the statement itself. It does not expand the statement's scope or establish unrelated facts.

## What Acceptance Does Not Establish

Acceptance does not by itself establish:

- ownership or mutation authority;
- aggregate membership or structure;
- a lifecycle state or transition;
- workflow completion;
- execution success;
- technical completion;
- implementation success;
- persistence or retention requirements;
- a transaction boundary or commit result;
- an API, schema, identifier, or representation;
- durability or immutability unless separately classified; or
- the correctness or success of any unrelated statement.

These matters require their own authoritative architectural decisions.

## Acceptance Distinctions

### Acceptance and Technical Completion

Technical completion means that a technical operation reports that it finished. Acceptance means that a domain statement is recognized as valid business truth. A completed technical step may produce evidence or a proposal for acceptance, but completion alone does not establish acceptance.

### Acceptance and Ownership

Ownership determines which authoritative boundary defines meaning, invariants, and mutation authority. Acceptance determines whether a particular statement has satisfied the applicable business validity rules. Acceptance does not assign ownership, and access to an accepted fact does not transfer ownership.

### Acceptance and Execution Success

Execution success describes the outcome of attempted work. Acceptance describes the authority of a business statement. Successful execution does not automatically establish an Accepted Domain Fact, and acceptance does not imply that every surrounding execution concern succeeded.

### Acceptance and Lifecycle Transitions

A lifecycle transition is a separately defined change in accepted business interpretation. Acceptance semantics explain why a resulting statement may be authoritative, but they do not define a lifecycle, state, transition, trigger, or guard. Acceptance therefore must not be used as an implicit lifecycle design.

### Acceptance and Implementation Success

Implementation success means that code, infrastructure, or another technical mechanism behaved according to its technical expectations. That success may support acceptance but cannot replace the domain determination. Conversely, an Accepted Domain Fact does not certify the quality or completeness of its implementation mechanism.

## Acceptance Principles

1. Acceptance is a domain-semantic determination, not a technical status.
2. Acceptance requires conformity with applicable business meaning and invariants.
3. Acceptance establishes an authoritative business statement only within the statement's semantic scope.
4. Observation, attempt, transmission, storage, display, or technical completion does not independently establish acceptance.
5. Acceptance does not assign ownership or broaden mutation authority.
6. Acceptance does not imply execution, implementation, workflow, or lifecycle completion.
7. Acceptance does not select a persistence, transaction, API, schema, identifier, algorithm, data structure, design pattern, or implementation mechanism.
8. Acceptance semantics remain stable when technical representations or implementation technologies change.
9. Acceptance must not create competing mutable authorities for the same business statement.
10. Accepted meaning remains authoritative when execution is independently scaled or an architectural boundary is later extracted.

## Acceptance Invariants

1. Accepted facts are authoritative business statements within their defined semantic scope.
2. Acceptance semantics are independent from storage, transport, process, framework, and deployment technology.
3. Acceptance semantics remain valid under future extraction and independent scaling.
4. Acceptance does not imply or assign ownership.
5. Acceptance does not imply a persistence design.
6. Acceptance does not imply workflow completion.
7. Technical representations may carry an accepted fact but may not redefine its accepted meaning.
8. Technical success, recency, or existence cannot independently promote a statement into business truth.

These are semantic invariants only. They do not define lifecycle transitions, validation procedures, persistence constraints, or runtime behavior.

## Acceptance and Business Truth

Business truth is composed of domain statements that are authoritative within their defined meanings. Acceptance is the semantic boundary between information that may serve as business truth and information that remains observation, evidence, proposal, attempt, or technical representation.

An Accepted Domain Fact may be relied upon according to its scope, but acceptance does not make every representation of that fact a Source of Truth. Nor does it allow a cache, message, file, log, response, task result, or other technical form to become an independent business authority.

Acceptance must remain explainable: it must be possible to distinguish the accepted business statement from the technical evidence or mechanisms associated with it. This distinction preserves one coherent business interpretation without defining its ownership or implementation here.

## Acceptance Exclusions

This document explicitly excludes:

- ownership decisions;
- aggregate decisions;
- lifecycle design;
- state-machine design;
- transaction design;
- persistence design;
- implementation decisions;
- schema design;
- API design;
- DSA decisions; and
- design pattern decisions.

These exclusions mean that acceptance semantics neither establish nor change those decisions.

## Architectural Rationale

Explicit acceptance semantics improve auditability by distinguishing authoritative business statements from technical attempts, evidence, and representations. They preserve coherent business truth by making clear when information may be relied upon and by preventing technical completion from being reported as domain acceptance.

The semantics provide stable inputs for future ownership design and aggregate design without assigning either. They also clarify future lifecycle design by separating the authority of an accepted statement from the states and transitions that may later organize business behavior.

Clear acceptance meaning guides later persistence design and transaction-boundary decisions by identifying which statements require authoritative treatment without prescribing storage or commit mechanisms. It likewise allows future DSA decisions to follow the meaning and correctness needs of accepted information rather than technical convenience.

Technology-independent semantics preserve implementation flexibility. Representations, processes, frameworks, deployment topology, and scaling strategies may change while the meaning of acceptance remains stable.

## Scope Boundary

Only Accepted Domain Fact semantics are defined here. This document introduces no concrete fact, owner, aggregate, entity, module, lifecycle, state, transition, persistence mechanism, transaction, interface, schema, identifier, algorithm, data structure, design pattern, or implementation.
