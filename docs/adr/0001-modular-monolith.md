# ADR 0001: Use a Modular Monolith

- Status: Accepted
- Date: 2026-07-15

## Context

The MVP combines storage ingestion, image processing, review, and export, but one team must evolve shared lifecycle and audit invariants. Premature services would add distributed transactions, deployment, versioning, and observability cost without a demonstrated scaling boundary.

## Decision

Build one backend codebase as a modular monolith with explicit identity, storage catalog, ingestion, assets, processing, review, export, and operations modules. Separate domain, application, presentation, and infrastructure concerns where useful. API and Celery worker processes may run independently but execute the same versioned application modules. Cross-module access uses explicit public ports; infrastructure and ORM types do not cross module boundaries.

## Consequences

- Business transitions can use local transactions and one schema while remaining testable without frameworks.
- API and worker processes scale independently; modules can be extracted later only with measured need.
- The team must automate dependency rules and prevent a shared-database free-for-all.
- A deployment is still multi-process/container; “monolith” describes code and consistency boundaries, not one OS process.

## Rejected Alternatives

Microservices add avoidable distributed failure modes. A layer-only monolith obscures business ownership. A single unstructured package would make later scaling and testing expensive.
