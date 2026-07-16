# Internal Pilot Scope

## Milestone Definition

The Internal Pilot is a constrained pre-production delivery milestone for one or two named internal Ghateh Iran operators. It is deployed locally on the approved Windows 11, Docker Desktop, WSL2, and Linux-container baseline, is restricted to trusted internal use, and uses the accepted MVP runtime and architectural boundaries.

Its purpose is to validate real product-image processing with actual Ghateh Iran datasets through the smallest complete operational feature slice. It is not a separate product, throwaway prototype, alternative architecture, reduced definition of the official MVP, or permission to bypass an accepted ADR. Pilot capability is promoted incrementally into the official MVP rather than replaced.

> The Internal Pilot narrows feature breadth, not architectural integrity.

## Mandatory Architecture Retained

The Internal Pilot retains:

- the React and TypeScript operational UI;
- the FastAPI REST backend;
- PostgreSQL as the durable Source of Truth for business and session state;
- Redis only as a non-durable broker and temporary coordination store;
- Celery background workers;
- named user accounts;
- server-side PostgreSQL-backed sessions;
- the accepted fixed role-based authorization boundaries;
- immutable source images and exact source observations;
- durable processing intent, state, provenance, and audit facts;
- mandatory human review before production export;
- an ExportJob and ExportItem lifecycle independent from Batch and BatchImage lifecycles;
- Docker Compose deployment on the approved local baseline;
- local or external-HDD-backed storage through the approved storage abstractions;
- a versioned, deterministic, non-generative image-processing pipeline; and
- enough auditability to explain every approved export.

The Pilot must not create a second local runner, CLI architecture, desktop-only architecture, in-process job system, SQLite path, filesystem-only state model, alternate session mechanism, or alternate processing core. The UI has no direct filesystem authority, and Redis or Celery state never determines business success.

## Pilot User Scope

The initial operational audience is one or two named internal Ghateh Iran users. Only the minimum accounts needed for real operation may initially be provisioned, but every account uses the accepted identity, authentication, session, and authorization architecture.

The authoritative four-role model remains `admin`, `operator`, `reviewer`, and `auditor`. The Pilot does not remove or redefine a role, invent a new role, or introduce editable permission policy. It may initially expose only the role capabilities and screens required by the selected end-to-end workflow, while the official MVP permission model remains unchanged. Anonymous access is prohibited.

## Minimum End-to-End Pilot Workflow

The minimum complete operational workflow is:

1. An authenticated operator accesses the local React UI.
2. The operator selects an enabled, server-configured storage root and a safe relative folder.
3. The system performs bounded image discovery and durable registration.
4. PostgreSQL records source observations and the intended processing work.
5. Celery dispatches processing through Redis.
6. A worker reads the immutable source image through the approved storage abstraction.
7. The versioned, non-generative processing pipeline creates a review candidate.
8. The candidate follows the approved technical output direction:
   - PNG;
   - exactly 2000 × 2000 pixels;
   - RGB;
   - sRGB;
   - 8-bit per channel;
   - a white `#FFFFFF` canvas outside the real product and any explicitly enabled approved bounded contact shadow;
   - preserved aspect ratio and geometry;
   - no generative reconstruction; and
   - no added or invented objects.
9. A human compares the source preview and candidate.
10. The human approves, rejects, or requests reprocessing.
11. Only an approved candidate is eligible for export.
12. Export writes a validated output without modifying the original image.
13. PostgreSQL retains sufficient durable facts to trace the output to its source observation, processing provenance, human decision, and export record.

This workflow defines delivery scope. It does not authorize implementing all capabilities in one Sprint. Each capability must be introduced through its own separately reviewed Micro Sprint.

## Minimum Pilot Feature Breadth

The initial Internal Pilot is limited to:

- one configured installation;
- one or two named internal operators;
- one enabled local or external-storage workflow;
- bounded folder discovery;
- one approved processing preset or tightly controlled initial preset;
- batch registration;
- asynchronous processing;
- basic progress visibility;
- human candidate review;
- approve, reject, and reprocess decisions;
- approved-only PNG export;
- essential failure visibility; and
- restart-safe durable state for accepted operations.

One preset means limited user-facing breadth. It does not permit hard-coding the processing engine, preset policy, or business rules into the UI, infrastructure, or deployment scripts. The preset remains a validated, immutable, versioned processing input.

## Deferred From the Internal Pilot, Not Removed From the MVP

The following feature breadth may be deferred until after the Internal Pilot while remaining part of the official MVP or later roadmap:

- broad administration screens;
- a full preset-management UI;
- multiple active presets;
- advanced dashboard analytics;
- auditor-focused UI breadth;
- bulk administrative operations;
- advanced automatic QC scoring;
- optional GPU execution;
- sophisticated performance tuning;
- extended diagnostics;
- commercial packaging;
- tenant isolation;
- licensing and billing;
- cloud deployment;
- S3-compatible storage;
- broad localization beyond the approved primary locale; and
- advanced deployment automation.

No accepted architectural foundation is deferred. In particular, the Pilot retains PostgreSQL, Redis, Celery, FastAPI, React, authentication, named PostgreSQL-backed sessions, mandatory human review, approved-only export, and immutable source handling.

## Pilot Quality Gates

The Internal Pilot must not be handed to operators unless:

- original images remain unchanged;
- interrupted operations do not falsely report success;
- accepted business state survives application and browser restarts;
- queue state is not treated as business truth;
- only approved candidates can be exported;
- output files pass the required technical PNG checks;
- filesystem paths cannot escape approved storage roots;
- authentication is required;
- secrets and machine-local values are not committed;
- a small real Ghateh Iran image set has completed the full workflow;
- known limitations are documented;
- installation and operator-start instructions exist; and
- critical failures are visible to the operator.

Numerical performance targets are not introduced by this scope document. Any such target must come from authoritative requirements or measured, reviewed evidence.

## Evolution Into the Official MVP

The Internal Pilot evolves into the official MVP by expanding feature breadth over the same architecture. That evolution preserves:

- database identities and durable history;
- API boundaries;
- worker contracts;
- storage abstractions;
- domain boundaries;
- processing provenance;
- review decisions;
- export records; and
- architectural dependency direction.

Pilot implementation must not create a migration dependency on:

- SQLite;
- ad hoc JSON state;
- filesystem folder names as business state;
- anonymous sessions;
- synchronous browser-bound processing;
- direct UI filesystem authority;
- Redis or Celery result state as truth;
- an alternate image-processing core; or
- a separate repository.

## Terminology

- **Internal Pilot:** A constrained pre-production operational milestone for Ghateh Iran's internal users.
- **MVP:** The accepted multi-role product scope defined by authoritative repository documentation.
- **Production Release:** A hardened, tested, supportable release approved for normal operational use.
- **Commercial Product:** A future distributable offering with packaging, licensing, support, and customer-specific concerns.

The term MVP must not be used as a synonym for the Internal Pilot.
