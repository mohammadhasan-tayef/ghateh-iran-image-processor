# Ghateh Iran Image Processor

Ghateh Iran Image Processor is a self-hosted system whose Internal Pilot uses independent standalone-local installations. The browser and application run on the same operator computer, with configured local or externally attached storage. It preserves source photographs, creates reviewable non-generative candidates, and exports only versions accepted under the configured human-review policy.

## Current Status

Sprint 1.9.3 — Alembic Migration Harness and Empty Baseline Revision completed.

The backend now includes exactly pinned SQLAlchemy and psycopg binary runtime dependencies and an immutable, secret-safe database configuration boundary. The only supported database URL environment variable is `GHATEH_DATABASE_URL`, and its URL must use the `postgresql+psycopg` driver with explicit credentials, host, port, and database name. This variable is required when database tooling or runtime composition begins.

All trusted database consumers, including Alembic, use the centralized `resolve_database_url()` boundary to obtain a normally redacted SQLAlchemy URL. Database URL query parameters remain rejected so unreviewed connection, credential, host, port, and TLS behavior cannot enter migration or runtime composition.

The database URL has no committed default, and `.env` loading remains disabled. The following value is a structural placeholder, not an active credential:

```text
postgresql+psycopg://<user>:<password>@<host>:5432/<database>
```

Alembic 1.18.5 is an exactly pinned runtime dependency. Migration definitions live in `backend/migrations/`, and the single `0001_empty_baseline` revision establishes migration lineage without creating any business tables. Migration commands consume `GHATEH_DATABASE_URL` through the centralized resolver; `backend/alembic.ini` stores no URL or password, and `.env` loading remains disabled.

From `backend/`, migration lineage and offline SQL can be inspected with:

```text
uv run alembic -c alembic.ini heads
uv run alembic -c alembic.ini history
uv run alembic -c alembic.ini upgrade head --sql
```

`GHATEH_DATABASE_URL` must be set before commands that execute the migration environment, including offline SQL generation and future online migration execution. Offline PostgreSQL SQL generation is supported. Online migration execution is scaffolded but has not been validated against a real PostgreSQL service. Autogenerate is not enabled because no ORM metadata exists.

The current `ghateh-api` runner still does not construct or connect to a runtime database engine. No application table exists yet.

The backend creates the API through an explicit FastAPI application factory and validates its local runtime binding before starting Uvicorn. Its local liveness route is available at `GET /api/v1/health/live`.

Every Pull Request and every push to `main` runs the backend quality gate. On the pinned Ubuntu 24.04, Python 3.12.13, and uv 0.11.29 environment, CI verifies lockfile consistency, locked environment synchronization, Ruff formatting, Ruff lint, strict mypy, pytest, and package construction. This gate validates only the platform-neutral backend foundation; it does not deploy or publish anything.

From `backend/`, the normal local development startup command is:

```text
uv run ghateh-api
```

The API defaults to `127.0.0.1:8000`. Process-environment overrides are limited to `GHATEH_API_HOST` and `GHATEH_API_PORT`; non-loopback addresses are rejected. Port `8000` is a local executable default, not a permanent deployment contract.

No `.env` loading exists, and no database URL or password is configured in the repository.

No operational image-processing workflow has been implemented yet.

Authentication, storage, queues, and processing capabilities have not been implemented.

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

The next implementation increment is real PostgreSQL-backed migration apply and downgrade verification.
