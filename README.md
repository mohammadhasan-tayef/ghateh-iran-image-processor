# Ghateh Iran Image Processor

Ghateh Iran Image Processor is a self-hosted, local-network system for registering and processing large product-image batches directly from approved external-storage folders. It preserves source photographs, creates reviewable non-generative candidates, and exports only versions accepted under the configured human-review policy.

## Current Status

Sprint 0.1 — Architecture corrections and technical specification refinement.

No application code has been implemented yet.

## Sprint 0 Scope

Sprint 0 and Sprint 0.1 define and correct the product requirements, modular-monolith boundary, domain and state models, secure external-storage handling, image pipeline, REST API, persistence, queues, review controls, deployment, testing, and incremental delivery. These sprints create documentation only; implementation and dependency installation are deliberately deferred.

## Core Principles

- Originals are immutable and are addressed through configured storage roots.
- PostgreSQL is the durable source of truth; Redis contains only disposable coordination state.
- The main pipeline is deterministic and non-generative.
- Product authenticity takes priority over aesthetic similarity.
- Automated checks assist review but do not prove semantic correctness.
- The first rollout requires explicit human approval before final export.
- Image review completion and export completion are independent lifecycles.
- Named local accounts use PostgreSQL-backed server sessions; browser JWT authentication is excluded from the MVP.

## Documentation Index

- [Product requirements](docs/specifications/product-requirements.md)
- [System architecture](docs/architecture/system-architecture.md)
- [Domain model](docs/architecture/domain-model.md)
- [State machines](docs/architecture/state-machines.md)
- [Storage design](docs/architecture/storage-design.md)
- [Image pipeline](docs/architecture/image-pipeline.md)
- [API design](docs/architecture/api-design.md)
- [Database design](docs/architecture/database-design.md)
- [Worker and queue design](docs/architecture/worker-and-queue-design.md)
- [Security](docs/architecture/security.md)
- [Observability](docs/architecture/observability.md)
- [Testing strategy](docs/architecture/testing-strategy.md)
- [Deployment](docs/architecture/deployment.md)
- [Proposed project structure](docs/architecture/project-structure.md)
- [Sprint plan](docs/architecture/sprint-plan.md)
- [Architecture decisions](docs/adr/)
- [Mermaid diagrams](docs/diagrams/)
- [Sprint 0 source prompt](prompts/sprints/sprint-00-architecture.md)

## Repository Structure

- `docs/architecture/` — authoritative technical designs
- `docs/adr/` — accepted architecture decisions and rationale
- `docs/diagrams/` — Mermaid views derived from the authoritative documents
- `docs/specifications/` — product requirements and acceptance criteria
- `prompts/sprints/` — source prompts for planning sprints
- `samples/raw/` — ignored local raw fixtures; only the placeholder is tracked
- `samples/reference-output/` — ignored local reference results; only the placeholder is tracked

## Next Steps

Review and approve the corrected Sprint 0.1 decisions and remaining open questions. Sprint 1 may begin only after this documentation branch is accepted; it should establish the pinned toolchain and implement only the walking skeleton described in the [sprint plan](docs/architecture/sprint-plan.md), with no image processing yet.
