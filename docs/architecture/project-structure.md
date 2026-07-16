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
├── config/
├── data/
├── scripts/
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

`identity/` owns named users, fixed role policies, and PostgreSQL-backed UserSessions. `assets/` is the sole semantic/domain owner of ImageAsset and SourceObservation, including accepted SourceObservation meaning, accepted source identity and provenance, historical stability, and invariants. `storage_catalog/` has operational responsibility for configured-root activation, safe locators and keys, source discovery, source-byte access, current availability, source previews, storage and discovery adapters, and technical evidence supplied to the Assets boundary; it does not own or independently accept SourceObservation. `ingestion/` owns Batch/BatchImage processing-review roll-up; `export/` owns independent ExportJob/ExportItem state and naming snapshots. `api/` composes routers and transport concerns; `workers/` exposes thin Celery entry points; `bootstrap/` is the composition root/factories; `shared/` contains only stable primitives such as IDs, time/result types, Unit of Work contracts, and cross-cutting errors—not miscellaneous business helpers.

This singular ownership keeps SourceObservation as a durable historical domain fact whose meaning survives storage-technology changes. Separating Assets authority from Storage catalog operations prevents source discovery, byte access, current path state, physical storage, or technical co-location from becoming acceptance authority or a competing mutable Source of Truth, preserving source identity and provenance, auditability, and historical stability without expanding Assets into storage operations.

## Top-Level Folder Ownership

Ownership identifies the repository role accountable for maintaining a boundary. Allowed contents describe where later sprint work belongs; they do not authorize creating that work before its owning sprint.

### `backend/`

- **Purpose:** Own all backend implementation and backend-specific verification in future sprints.
- **Repository Owner:** Backend maintainers, with the technical lead accountable for module-boundary enforcement.
- **Allowed Contents:** The Python workspace and its versioned tooling manifest; `src/ghateh_processor/` modules; backend tests and fixtures; database migration definitions; API and worker entry points; backend-specific static configuration required to build or test the workspace.
- **Forbidden Contents:** React/frontend code; deployment scripts or infrastructure manifests; runtime-generated data; model weights, previews, exports, or caches; secrets and credentials.
- **Notes:** `backend/migrations/` contains Alembic revisions but must not hide business decisions solely in migrations. Unit, integration, contract, and fixture suites belong under `backend/tests/` when their implementation sprint begins.

### `frontend/`

- **Purpose:** Own the React application and frontend-specific verification in future sprints.
- **Repository Owner:** Frontend maintainers, with the technical lead accountable for frontend feature boundaries.
- **Allowed Contents:** React/TypeScript application source; frontend tests; versioned frontend build and package metadata; static UI assets; `fa-IR` translations, RTL configuration, error-code mappings, timezone formatting, and LTR-isolation helpers.
- **Forbidden Contents:** Backend Python code; server-side domain or persistence logic; database migrations; deployment scripts or infrastructure manifests; runtime-generated data; secrets and credentials.
- **Notes:** Application composition belongs in `frontend/src/app/`; resource-aligned UI belongs in `frontend/src/features/`; shared design and transport primitives must not contain feature business rules. Frontend tests belong under `frontend/tests/` when their implementation sprint begins.

### `deploy/`

- **Purpose:** Own deployment-related assets only.
- **Repository Owner:** Platform and operations maintainers.
- **Allowed Contents:** Docker definitions; Compose definitions; infrastructure manifests; deployment templates; and deployment scripts under `deploy/scripts/`, including container entrypoints, deployment-time migration execution, deployment health probes, backup and restore execution, operator automation, and install, start, stop, upgrade, and rollback scripts.
- **Forbidden Contents:** Backend or frontend application code; repository-level lint/format/verify utilities; runtime-generated data; model weights; committed secrets or credentials; user-specific deployment overrides.
- **Notes:** `backend/migrations/` owns Alembic migration definitions; `deploy/scripts/` may own deployment-time invocation of those migrations. Business decisions must never exist only in deployment scripts. Any script that operates a deployed environment belongs under `deploy/scripts/`, not root `scripts/`.

### `config/`

- **Purpose:** Own version-controlled project configuration shared by the repository or its workspaces.
- **Repository Owner:** Technical lead and developer-experience maintainers, with component owners reviewing component-specific configuration.
- **Allowed Contents:** Non-secret configuration templates; checked-in tool configuration; schemas; safe defaults; documented example values that are valid to publish.
- **Forbidden Contents:** Secrets; credentials; generated files; runtime state; user-specific configuration; machine-local paths; active environment files containing private values.
- **Notes:** Sensitive or deployment-local values remain outside Git. A committed example must contain placeholders or safe development defaults only. Shared repository/workspace configuration normally belongs under `config/`; deployment-specific manifests, templates, and configuration belong under `deploy/`.
- **Root-Level Convention Exception:** A configuration file may reside at the repository root only when at least one of these conditions applies:
  1. The tool's standard discovery mechanism requires or conventionally expects the file at the repository root.
  2. Placing the file under `config/` would prevent repository-wide discovery or correct operation.
  3. The file governs repository-wide developer or version-control behavior and has a conventional root location.

  This narrow exception does not authorize arbitrary root-level configuration.
- **Root-Level Requirements:** Every root-level configuration file must:
  - have a technical discovery or ecosystem-convention justification;
  - govern repository-wide behavior;
  - contain no secrets or machine-local values;
  - not duplicate configuration already owned elsewhere;
  - not become a miscellaneous alternative to `config/`;
  - remain minimal and purpose-specific; and
  - be introduced only in its owning approved Micro Sprint.
- **Non-Exhaustive Examples:** `.editorconfig`, `.gitattributes`, and `.gitignore` are examples only when their standard repository-wide behavior requires root placement. Listing them documents possible root ownership; it does not create or modify them in this Sprint.
- **Rationale:** The exception allows standard tool discovery to work and repository-wide behavior to apply from the root while preserving explicit ownership. Its conditions prevent both broken discovery caused by forced relocation and uncontrolled root clutter caused by treating the root as a general configuration directory.

### `data/`

- **Purpose:** Provide a local location for runtime-generated or externally installed data.
- **Repository Owner:** Operations maintainers own lifecycle policy; producing components own the correctness of their subdirectories.
- **Allowed Contents:** Caches, installed model data, generated previews, export outputs, temporary files, and other runtime-generated artifacts.
- **Forbidden Contents:** Application source code; dependency manifests; architecture documentation; reusable developer scripts; committed configuration; version-controlled configuration templates; configuration schemas; project defaults; secrets or credentials; production data copied into Git.
- **Notes:** Git ignores `data/` contents except its placeholder. Contents are disposable or governed by runtime retention/backup policy and are never treated as version-controlled source. Shared committed configuration belongs under `config/`, while deployment-specific configuration belongs under `deploy/`.

### `docs/`

- **Purpose:** Own long-term project documentation.
- **Repository Owner:** Technical lead and the maintainers of the documented subsystem.
- **Allowed Contents:** Architecture documents, ADRs, specifications, diagrams, operational documentation, and other durable project guidance.
- **Forbidden Contents:** Application implementation; executable operator/deployment scripts; runtime-generated data; build output; secrets or credentials; transient personal notes presented as project policy.
- **Notes:** Authoritative documents and derived diagrams must remain consistent. Material architecture decisions require the appropriate document or ADR update.

### `prompts/`

- **Purpose:** Own reusable prompts used during development and planning.
- **Repository Owner:** Development team, with the technical lead accountable for prompts that define sprint scope.
- **Allowed Contents:** Version-controlled reusable prompts, sprint prompts, prompt templates, and concise prompt-specific usage notes.
- **Forbidden Contents:** Generated model responses; application source code; runtime data; application runtime configuration; runtime business rules; production policy; operational or application sources of truth; secrets, credentials, or private production content; one-off personal scratch prompts.
- **Notes:** `prompts/` must never be loaded by the application as runtime configuration, must never define runtime business rules, must never be treated as production policy, and must never become an operational or application runtime source of truth. Accepted architecture documents, ADRs, validated configuration, immutable preset revisions, and PostgreSQL records remain authoritative according to their domains.

### `samples/`

- **Purpose:** Own sample datasets, fixtures, and reference images used for documentation, evaluation, or later tests.
- **Repository Owner:** Quality and product maintainers, with technical owners reviewing format and licensing requirements.
- **Allowed Contents:** Licensed or approved sample images, synthetic fixtures, reference outputs, manifests, and non-sensitive metadata required to interpret them.
- **Forbidden Contents:** Production data; customer data; unlicensed assets; secrets or credentials; runtime outputs presented as approved references; application source code.
- **Notes:** Sample data is never production data. Large or policy-restricted samples remain outside Git; current raw and reference-output directories track placeholders only.

### `scripts/`

- **Purpose:** Own repository-level developer utilities only.
- **Repository Owner:** Developer-experience maintainers.
- **Allowed Contents:** Bootstrap, lint, format, verify, and documentation utilities that operate on the repository or developer workflow.
- **Forbidden Contents:** Deployment or operator scripts; application business logic; long-running runtime services; generated data; secrets or credentials; user-specific automation.
- **Notes:** Deployment scripts belong under `deploy/scripts/`. Root `scripts/` must not install, start, stop, upgrade, back up, restore, or otherwise operate a deployed environment.

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
