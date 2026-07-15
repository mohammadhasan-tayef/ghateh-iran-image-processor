# Proposed Project Structure

This is the intended monorepo tree for later sprints; Sprint 0/0.1 does not create production source-code folders or dependency manifests.

```text
ghateh-iran-image-processor/
├── backend/
│   ├── pyproject.toml
│   ├── migrations/
│   ├── src/ghateh_processor/
│   │   ├── shared/
│   │   ├── identity/
│   │   ├── storage_catalog/
│   │   ├── ingestion/
│   │   ├── assets/
│   │   ├── processing/
│   │   ├── review/
│   │   ├── export/
│   │   ├── operations/
│   │   ├── api/
│   │   ├── workers/
│   │   └── bootstrap/
│   └── tests/
│       ├── unit/
│       ├── integration/
│       ├── contract/
│       └── fixtures/
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   ├── features/
│   │   ├── i18n/
│   │   ├── shared/
│   │   └── pages/
│   └── tests/
├── deploy/
│   ├── compose/
│   └── scripts/
├── docs/
│   ├── architecture/
│   ├── adr/
│   ├── diagrams/
│   └── specifications/
├── prompts/sprints/
├── samples/
│   ├── raw/
│   └── reference-output/
└── README.md
```

## Backend Module Shape

Each business module may contain `domain/`, `application/`, `infrastructure/`, and `presentation/` packages only when needed. The domain holds entities, value objects, policies, events, and port protocols. Application holds command/query DTOs and use cases. Infrastructure holds SQLAlchemy repositories, storage/engine adapters, and external integrations. Presentation translates HTTP/task input and output. Avoid empty ceremonial layers.

`identity/` owns named users, fixed role policies, and PostgreSQL-backed UserSessions. `storage_catalog/` owns configured-root activation, SourceObservation, and SourcePreviewArtifact adapters. `ingestion/` owns Batch/BatchImage processing-review roll-up; `export/` owns independent ExportJob/ExportItem state and naming snapshots. `api/` composes routers and transport concerns; `workers/` exposes thin Celery entry points; `bootstrap/` is the composition root/factories; `shared/` contains only stable primitives such as IDs, time/result types, Unit of Work contracts, and cross-cutting errors—not miscellaneous business helpers.

## Folder Responsibilities

- `backend/migrations`: Alembic revisions; no business decisions hidden solely in migrations.
- `backend/tests/unit`: dependency-free domain/application tests.
- `backend/tests/integration`: PostgreSQL/Redis/filesystem/engine integration.
- `backend/tests/contract`: REST and adapter conformance, especially `StorageBackend` and segmentation engines.
- `frontend/src/app`: composition, routing, providers, global error boundaries.
- `frontend/src/features`: vertical UI features aligned with API resources (batches, review, exports, admin).
- `frontend/src/i18n`: `fa-IR` translations, RTL direction configuration, stable English error-code mappings, timezone formatting, and LTR isolation helpers; font binaries are ordinary later application assets, not Sprint 0.1 files.
- `frontend/src/shared`: design primitives and transport utilities without feature business rules.
- `deploy`: deployment definitions and operator scripts, not application logic or secrets.
- `docs`: authoritative specifications/decisions and derived diagrams.
- `samples`: ignored local fixtures until licensing/storage policy exists.

## Dependency Rules

```text
presentation/api/workers → application → domain
infrastructure ───────────→ application/domain ports
bootstrap ────────────────→ all concrete composition
domain ───────────────────→ standard library/stable shared primitives only
```

- Business modules do not import another module's infrastructure or ORM rows. They call explicit public application/domain ports.
- HTTP schemas, Celery messages, SQLAlchemy models, Redis types, OpenCV arrays, PyTorch tensors, and filesystem paths do not become domain entities.
- Pipeline implementation belongs to `processing`; engine/storage implementations are adapters selected in `bootstrap`. BatchImage modules cannot depend on export infrastructure or expose export states.
- Frontend features may import shared UI/transport primitives but not another feature's internal modules. Cross-feature orchestration lives in pages/app or an explicit public feature API.
- Circular imports and service location are prohibited; dependency checks should be automated.

## Deferred Creation

Sprint 1 creates only the minimal folders and toolchain needed for the walking skeleton using Python 3.12, Node.js 22 LTS, PostgreSQL 17, Redis 7.x, and Linux containers under Windows 11/Docker Desktop/WSL2. Exact patch/image versions are pinned from official compatible releases during Sprint 1. Processing engines and GPU-specific structure remain deferred to their owning sprint.
