# Ghateh Iran Image Processor

Ghateh Iran Image Processor is a self-hosted system whose Internal Pilot uses independent standalone-local installations. The browser and application run on the same operator computer, with configured local or externally attached storage. It preserves source photographs, creates reviewable non-generative candidates, and exports only versions accepted under the configured human-review policy.

## Current Status

Sprint 1.8.2 — FastAPI Application Factory and Liveness Contract completed.

The backend now creates the API through an explicit FastAPI application factory. Its local liveness route is available at `GET /api/v1/health/live`.

From `backend/`, start the development server on loopback with:

```text
uv run uvicorn ghateh_processor.bootstrap.api:create_app --factory --host 127.0.0.1
```

No operational image-processing workflow has been implemented yet.

Persistence, authentication, storage, queue, and processing capabilities have not been implemented.

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
- [Git branch and commit standards](docs/architecture/git-branch-and-commit-standards.md)
- [Pull Request title and target standards](docs/architecture/pull-request-title-and-target-standards.md)
- [Pull Request description structure](docs/architecture/pull-request-description-structure.md)
- [Sprint plan](docs/architecture/sprint-plan.md)
- [Architecture decisions](docs/adr/)
- [Mermaid diagrams](docs/diagrams/)
- [Sprint 0 source prompt](prompts/sprints/sprint-00-architecture.md)

## Repository Structure

- `backend/` — Python backend workspace and package foundation
- `frontend/` — frontend workspace placeholder
- `deploy/` — deployment workspace placeholder
- `config/` — repository configuration placeholder
- `data/` — ignored local data; only the placeholder is tracked
- `scripts/` — repository scripts placeholder
- `docs/` — authoritative specifications, architecture, decisions, and diagrams
- `prompts/` — sprint source prompts
- `samples/` — ignored local fixtures and reference outputs

## Next Steps

The next implementation increment is typed local application configuration.
