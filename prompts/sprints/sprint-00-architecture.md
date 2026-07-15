# Sprint 0: Architecture and Technical Specification

You are acting as a senior software architect and technical lead.

We are starting a new project called:

Ghateh Iran Image Processor

This is Sprint 0: Architecture and Technical Specification.

Do not implement the application.
Do not generate backend, frontend, Docker, database, Celery, Redis, or image-processing code.
Do not install dependencies.
Do not create production source-code folders yet.

Your job is to inspect the repository and create the complete architectural foundation for later coding sprints.

==================================================
PROJECT PURPOSE
==================================================

The application is a local-network web application for high-volume product image processing.

Users will connect an external hard drive containing thousands of raw product photographs.

The application must read images directly from approved folders on that external drive without requiring users to copy all images to the computer's internal storage and without requiring browser uploads for large batches.

The web interface is a local operational control panel.

The actual image-processing workers run locally on the host computer or later on dedicated worker machines.

The application must:

- Scan a selected folder from a configured external storage root
- Register thousands or tens of thousands of image files as a batch
- Preserve original images unchanged
- Process images asynchronously
- Remove the original background
- Preserve the real product exactly
- Never generate, invent, reconstruct, or add product components
- Place the extracted product on a pure white #FFFFFF canvas
- Produce a 2000 × 2000 PNG
- Preserve product aspect ratio, text, colors, geometry, and visible details
- Apply conservative lighting correction
- Apply mild denoising and sharpening
- Center and scale the product consistently
- Perform automated quality checks
- Route outputs to review
- Show raw and processed images side by side
- Allow human approve, reject, or reprocess actions
- Save only human-approved final versions into the final output directory on the external drive
- Preserve all processing versions and audit history
- Continue processing when the browser is closed
- Recover safely after application or machine restart

The target visual result is the approved Ghateh Iran product-photo standard.

The system should attempt to match the reference outputs, but product authenticity must always be prioritized over visual perfection.

==================================================
NON-NEGOTIABLE CONSTRAINTS
==================================================

- Fully self-hosted
- No paid API
- No cloud image-processing dependency
- No generative image model in the main pipeline
- Must work offline after dependencies and model weights are installed
- Windows must be supported
- CPU execution must be supported
- Optional NVIDIA GPU acceleration may be supported
- External-drive originals must never be overwritten
- PostgreSQL must be the permanent source of truth
- Redis must only hold queues, locks, cancellation flags, and temporary state
- REST API
- Modular monolith for the initial architecture
- No microservices for the MVP
- No Kubernetes
- No Kafka
- No GraphQL
- No event sourcing
- No image blobs inside PostgreSQL

==================================================
PLANNED TECHNOLOGY DIRECTION
==================================================

Backend:
- Python 3.12
- FastAPI
- Pydantic v2
- SQLAlchemy 2
- Alembic
- PostgreSQL

Background processing:
- Celery
- Redis

Image processing:
- BiRefNet primary segmentation adapter
- rembg fallback adapter
- OpenCV
- Pillow
- NumPy
- PyTorch

Frontend:
- React
- TypeScript
- Vite
- TanStack Query

Infrastructure:
- Docker
- Docker Compose

Testing:
- Pytest
- Vitest
- Ruff
- MyPy
- ESLint
- Prettier

Do not treat every planned technology as unquestionable.
Identify risks and alternatives, but do not replace the chosen stack without clearly documenting a blocking reason.

==================================================
REQUIRED ARCHITECTURAL STYLE
==================================================

Use a modular monolith with clear boundaries:

- API/presentation layer
- Application/use-case layer
- Domain layer
- Infrastructure layer
- Processing pipeline
- Background workers
- Persistence
- Storage abstraction

Use design patterns only where they solve a concrete problem.

Expected patterns include:

- Strategy for segmentation engines
- Adapter for third-party/local image engines and storage backends
- Pipeline or Chain of Responsibility for image-processing stages
- Factory for constructing pipelines and engines from configuration
- Repository for domain-specific persistence access
- Unit of Work for transactional use cases
- State machine for Batch, Image, Review, and Export transitions
- Command/use-case objects for application operations
- Domain events inside the modular monolith
- StorageBackend abstraction for local storage and future network/object storage

Avoid:
- unnecessary generic abstractions
- excessive inheritance
- service locator
- global mutable state
- premature microservice boundaries
- patterns added only for appearance

==================================================
PRIMARY WORKFLOW
==================================================

External drive folder
→ register allowed storage root
→ select relative folder in web panel
→ scan folder safely
→ create batch
→ stream file metadata into PostgreSQL
→ enqueue one image job per file
→ process asynchronously
→ generate candidate output
→ automated quality checks
→ review queue
→ human approve, reject, or reprocess
→ approved version becomes ready for export
→ export final version to the external drive
→ preserve processing versions and audit history

Browser upload must be treated only as a secondary method for small ad-hoc batches.

==================================================
STORAGE REQUIREMENTS
==================================================

The application must use configured storage roots.

Example Windows host path:

E:\GhatehIran-Images

Example container path:

/data/shared

The frontend must never submit unrestricted absolute filesystem paths.

It should submit:

- root_id
- relative_path

The backend must:

- resolve the path under the configured root
- reject path traversal
- reject symlink escape
- only expose allowed directories
- store logical storage keys or relative paths in PostgreSQL
- never expose host-specific absolute paths through the REST API

Proposed logical structure:

inbox/
working/
candidates/
review/
approved/
failed/
masks/
previews/
exports/
models/
temp/

The architecture document must determine exactly when files are copied, referenced, written atomically, renamed, or versioned.

==================================================
HUMAN REVIEW REQUIREMENTS
==================================================

All candidate images must be reviewable.

The system must support:

- side-by-side raw and processed image
- optional mask view
- quality score
- warnings
- approve
- reject with reason
- reprocess using another preset or engine
- select a previous processing version as final
- keyboard navigation
- bulk approval only when explicitly selected

Final output must not be considered production-ready merely because automated checks passed.

Design the workflow so we can choose between:

- mandatory human approval for every image
- auto-approval for high-confidence images
- mandatory review only for uncertain images

For the first operational rollout, recommend the safest policy.

==================================================
REQUIRED DOMAIN ENTITIES
==================================================

At minimum analyze and define:

- User
- Role
- StorageRoot
- Batch
- ImageAsset
- ProcessingRun
- ProcessingVersion or CandidateVersion
- Preset
- ReviewDecision
- ExportJob
- ProcessingEvent
- ModelInstallation or ModelRegistry entry

Determine whether ProcessingRun and CandidateVersion should be separate entities.

Use UUID identifiers.

Use PostgreSQL JSONB only for structured variable metadata, not as a replacement for proper relational modeling.

==================================================
STATE MACHINES
==================================================

Define explicit states and valid transitions for:

Batch:
- created
- scanning
- scan_paused
- queued
- processing
- awaiting_review
- completed
- partially_completed
- cancelled
- failed

Image:
- discovered
- registered
- queued
- processing
- candidate_ready
- needs_review
- human_approved
- rejected
- reprocess_queued
- export_ready
- exported
- failed
- cancelled

Processing run:
- pending
- running
- succeeded
- failed
- cancelled

Export:
- pending
- running
- completed
- partially_completed
- failed
- cancelled

Do not assume these proposed states are perfect.
Review them, remove redundancies, and document every allowed transition and retry path.

==================================================
SCALABILITY REQUIREMENTS
==================================================

The initial system may run as:

- 1 frontend
- 1 API
- 1 PostgreSQL
- 1 Redis
- 1 image worker
- 1 maintenance/export worker
- 1 external hard drive

The architecture must allow future growth to:

- multiple CPU workers
- dedicated GPU worker
- multiple API instances
- shared NAS storage
- future S3-compatible storage such as MinIO
- separate PostgreSQL and Redis hosts

Do not design distributed infrastructure now.
Document the seams that will allow later scaling without rewriting domain logic.

For high-volume ingestion:

- do not load all file paths or images into memory
- scan incrementally
- calculate SHA-256 using streams
- use bulk database inserts
- paginate UI results
- avoid one database transaction for an entire massive batch
- define idempotency and duplicate detection
- define crash recovery
- define backpressure
- define worker concurrency and memory limits
- define behavior when the external drive disconnects

==================================================
QUALITY AND AUTHENTICITY
==================================================

The system must not claim that every raw photo can automatically match a manually or generatively edited reference image.

Define:

- what transformations are deterministic and safe
- what transformations are uncertain
- when the system must stop and request human review
- how product text and geometry are protected
- how internal holes are preserved
- how thin cables, transparent materials, white products, reflective metal, and dark products are handled
- how confidence and quality scores are computed
- how quality scoring differs from semantic correctness

Document that a high quality score cannot guarantee product accuracy.

==================================================
SPRINT 0 DELIVERABLES
==================================================

Create only documentation and planning files.

Required files:

1. README.md
   - project purpose
   - current status
   - Sprint 0 scope
   - documentation index
   - next steps

2. docs/specifications/product-requirements.md
   - goals
   - users
   - workflows
   - functional requirements
   - non-functional requirements
   - acceptance criteria
   - out-of-scope items

3. docs/architecture/system-architecture.md
   - architecture style
   - system context
   - containers/components
   - module boundaries
   - dependencies
   - scalability path
   - failure handling

4. docs/architecture/domain-model.md
   - entities
   - relationships
   - invariants
   - aggregate boundaries
   - transaction boundaries

5. docs/architecture/state-machines.md
   - batch states
   - image states
   - processing-run states
   - review states
   - export states
   - valid and invalid transitions
   - retry behavior

6. docs/architecture/storage-design.md
   - external-drive model
   - allowed roots
   - path security
   - logical storage keys
   - directory structure
   - atomic writes
   - file versioning
   - disconnection behavior
   - future NAS/MinIO migration

7. docs/architecture/image-pipeline.md
   - pipeline stages
   - PipelineContext design
   - stage contracts
   - segmentation abstraction
   - mask refinement
   - color rules
   - canvas rules
   - quality control
   - review routing
   - reproducibility

8. docs/architecture/api-design.md
   - REST resources
   - endpoint list
   - request/response conventions
   - errors
   - pagination
   - idempotency
   - file-serving strategy
   - no absolute path exposure

9. docs/architecture/database-design.md
   - proposed tables
   - field descriptions
   - relationships
   - indexes
   - uniqueness rules
   - JSONB usage
   - retention rules
   - audit data

10. docs/architecture/worker-and-queue-design.md
    - Celery queues
    - Redis responsibilities
    - PostgreSQL truth model
    - retry policy
    - task idempotency
    - cancellation
    - CPU/GPU concurrency
    - backpressure
    - crash recovery

11. docs/architecture/security.md
    - local-network threat model
    - authentication
    - authorization
    - upload and file validation
    - path traversal prevention
    - secret management
    - CORS
    - auditability

12. docs/architecture/observability.md
    - logs
    - correlation IDs
    - per-stage timings
    - operational metrics
    - failure categories
    - local monitoring approach

13. docs/architecture/testing-strategy.md
    - unit tests
    - integration tests
    - pipeline fixtures
    - golden-image tests
    - hardware variance
    - end-to-end tests
    - performance tests
    - recovery tests

14. docs/architecture/deployment.md
    - local Windows deployment
    - Docker Compose topology
    - external-drive mounting
    - CPU profile
    - future GPU profile
    - backup and restore
    - upgrade strategy

15. docs/architecture/project-structure.md
    - final proposed monorepo tree
    - responsibilities of every main folder
    - dependency rules between folders

16. docs/architecture/sprint-plan.md
    - incremental implementation sprints
    - entry criteria
    - deliverables
    - tests
    - exit criteria
    - dependencies
    - rollback points

17. docs/adr/
    - 0001-modular-monolith.md
    - 0002-postgresql-as-source-of-truth.md
    - 0003-redis-and-celery.md
    - 0004-local-storage-abstraction.md
    - 0005-rest-api.md
    - 0006-non-generative-main-pipeline.md
    - 0007-human-review-before-final-export.md
    - 0008-birefnet-primary-rembg-fallback.md

18. docs/diagrams/
    Create Mermaid diagrams for:
    - system context
    - container architecture
    - batch processing sequence
    - review sequence
    - storage flow
    - entity relationship diagram
    - state machines

==================================================
AGENT WORKING RULES
==================================================

Before changing files:

1. Inspect the repository.
2. Report the current tree.
3. State assumptions.
4. List every file you plan to create or modify.
5. Identify ambiguities that genuinely block the documentation.

Then create the Sprint 0 documentation.

After changes:

1. Report all files created or modified.
2. Summarize major architecture decisions.
3. List unresolved questions.
4. List identified risks.
5. Propose Sprint 1 scope.
6. Do not begin Sprint 1.
7. Do not generate application code.
8. Do not claim diagrams or documents exist unless they were actually created.
9. Check internal consistency between documents.
10. Ensure every major decision has one authoritative location and is referenced elsewhere rather than contradicted.

Use precise engineering language.
Avoid filler.
Avoid pretending uncertain image-processing behavior is guaranteed.
