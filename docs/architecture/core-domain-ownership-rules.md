# Core Domain Ownership Rules

## Purpose

This document defines repository-wide rules for domain ownership, mutation authority, and cross-boundary access. These rules apply to every durable business concept while leaving the ownership of particular concepts to their authoritative architecture decisions.

## Domain Ownership

Domain ownership is the architectural responsibility for defining the meaning, invariants, lifecycle rules, and authoritative interpretation of a durable business concept. Ownership exists so that business meaning has one coherent source rather than being reconstructed differently by multiple parts of the system.

Ownership must be singular. Shared ownership creates competing lifecycle rules, ambiguous responsibility for correctness, and changes that cannot be evaluated within one clear boundary. Other boundaries may use a concept, but use does not make them co-owners.

## Mutation Authority

Mutation authority is the authority to accept or reject a requested change according to the owner-defined business rules. The owner defines the valid changes and remains accountable for preserving the concept's invariants.

Ownership and access are different. A consumer may be permitted to request a change, observe a result, or use an established fact without gaining authority to redefine or directly alter the underlying lifecycle. Permission to initiate an action is therefore not ownership, and access to data is not mutation authority.

## Cross-Module Access

Cross-module access must preserve the owning boundary. Consumers may refer to durable concepts through stable identifiers and may obtain facts or request behavior through explicit, documented contracts. Contracts must expose only the information and capabilities required by the consumer and must preserve the owner's authority to validate every change.

Consumers must not directly mutate another boundary's durable business state, reproduce its lifecycle decisions, or treat a local copy as an independent source of truth. Cross-boundary access must not depend on internal representations or allow a consumer to bypass the authoritative rules.

These principles define architectural boundaries only. They do not prescribe a transport, persistence, messaging, data-access, or code-level mechanism.

## Repository-Wide Ownership Rules

1. Every durable business concept has exactly one owner.
2. Ownership cannot be shared between architectural boundaries.
3. Only the owner defines the concept's meaning, invariants, lifecycle, and mutation rules.
4. Other boundaries may observe facts or request behavior, but they do not acquire ownership through access.
5. Cross-boundary references use stable identifiers or explicit contracts and preserve the owner's authority.
6. Direct cross-boundary mutation of durable business state is forbidden.
7. Ownership is independent from persistence technology. A database structure, record, relationship, or storage engine does not determine ownership.
8. Ownership is independent from APIs. Exposing or accepting an operation does not make a transport boundary the owner.
9. Ownership is independent from UI. Displaying, collecting, or initiating an action does not make a presentation boundary the owner.
10. Ownership is independent from queues and workers. Delivering or executing work does not transfer authority over the business lifecycle.
11. Ownership is independent from storage location. Co-location in a database, filesystem, object store, or other storage medium does not create shared ownership.
12. Read models and combined views may present facts from multiple owners but do not own or redefine those facts.
13. Audit records describe accepted facts and changes but do not become an alternate mutable source of business truth.
14. Ownership rules remain valid when execution is scaled independently or an architectural boundary is later extracted.

## Architectural Rationale

Singular ownership prevents technical debt by keeping business rules from being duplicated across transport, presentation, execution, and persistence concerns. A change has one authoritative place for validation, which reduces accidental coupling and prevents divergent interpretations of the same durable fact.

Clear mutation authority preserves transactional clarity. The system can identify which boundary must validate a change, which invariants must remain true, and which accepted result other consumers may trust. This also improves maintainability because responsibilities remain understandable as the codebase grows, and it supports scalability by keeping authority explicit when execution capacity changes.

These rules strengthen modular-monolith boundaries without introducing premature distribution. Boundaries can be developed, tested, reviewed, and scaled with explicit dependencies. If future evidence supports extraction, singular ownership and contract-based access provide a migration seam without first untangling shared lifecycle logic.

Testability improves because invariant and lifecycle behavior can be verified at its authoritative boundary, while consumers can be tested against stable contracts. Auditability improves because accepted changes and their responsible authority remain explainable, and combined views cannot silently redefine the underlying facts.

## Scope Boundary

This document does not assign ownership to any aggregate, entity, value, workflow, or module. It does not define database design, state machines, APIs, DTOs, processing contracts, persistence choices, transactions, design patterns, or implementation structure. Specific ownership assignments remain separate architectural decisions governed by these universal rules.
