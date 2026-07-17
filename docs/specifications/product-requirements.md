# Product Requirements

## Purpose and Goals

The product is an offline-capable browser-based control panel for high-volume product-image processing. It registers images in server-configured storage folders without browser upload, preserves originals, produces reviewable non-generative candidates, supports human review, and exports only explicitly approved versions.

The initial Internal Pilot deployment profile is standalone-local. Each named operator uses an independent installation on their own Windows computer, and the browser accesses the application only on that same computer. LAN access, an office network, a VPN, a shared application server, centralized processing, shared runtime state, and cross-installation synchronization are not required by the Internal Pilot. Other deployment profiles remain possible only through separate reviewed architecture decisions.

The production e-commerce output is unambiguous: PNG, exactly 2000 × 2000 pixels, 8-bit per channel, sRGB, RGB with no alpha channel, and a pure white `#FFFFFF` canvas. When the optional approved deterministic shadow is enabled, only its mask-derived pixels may differ from white outside the real product. Internal candidate artifacts may use RGBA; masks may use grayscale or alpha PNG.

Success means operators can safely resume a batch after browser, process, or host interruption and can explain every exported file through durable source-observation, processing-version, review, naming-policy, and audit records. Similarity to the approved visual reference is desirable; product authenticity is mandatory.

## Users, Roles, and Localization

The MVP uses four fixed roles whose permissions are defined in application code, not editable permission tables:

| Role | Primary responsibility |
|---|---|
| `admin` | Users, configured roots, presets, models, batches, review, export, and audit |
| `operator` | Browse enabled roots, create/manage batches, start processing, view results, request reprocessing |
| `reviewer` | Review candidates, approve/reject/reprocess, and select a prior candidate |
| `auditor` | Read-only batches, runs, decisions, exports, and audit events |

The detailed permission matrix is authoritative in [security](../architecture/security.md). Root-level per-user scoping is deferred for the MVP; enabled roots are visible according to role, with media access still constrained to authorized workflow resources.

The primary locale is `fa-IR` and the primary layout direction is RTL. Persian user messages, filenames, and Unicode paths must work safely. Identifiers, hashes, logical paths, filenames/extensions, and other code-like values remain LTR where appropriate. Backend error codes remain stable English identifiers and the frontend maps them to Persian messages. UI timestamps use the user's configured timezone while database timestamps remain UTC. Keyboard navigation and review hotkeys must be direction-independent. A suitable Persian font is served as a normal application asset in a later sprint; Sprint 0.1 commits no font binaries.

## Input Photography and Subject Policy

Input photography should contain one SKU per image; show the complete sellable product; physically include every required component; and exclude hands, tools, rulers, unrelated labels, spare parts, and background objects. Hidden or cropped components are never reconstructed.

Every immutable preset revision defines one `SubjectMode`, captured in the Batch and ProcessingRun preset snapshot:

- `single_object`
- `product_with_packaging`
- `multi_component_product`
- `keep_all_foreground_objects`
- `manual_subject_review_required`

Multiple disconnected real components are valid only for a compatible mode. Background removal does not decide business subject membership. Ambiguous interpretation, inconsistent component count, or `manual_subject_review_required` must route to human review; automatic segmentation may still run, but the reviewer must validate that the intended sellable subject was preserved. The pipeline never invents a missing subject. Interactive manual mask editing and subject painting are not part of the MVP.

## Primary Workflow

1. Server/Docker configuration defines a storage `config_key` and mounted container path. An admin activates or labels that preconfigured root; the UI never submits a host absolute path.
2. An operator selects `root_id`, `relative_path`, and an immutable preset revision, previews a bounded scan, and creates a batch.
3. The scanner creates durable source observations incrementally, validates regular image files, streams SHA-256, and commits bounded registration chunks.
4. Each `BatchImage` references the exact source observation used; one idempotent processing task is dispatched per registered item subject to backpressure.
5. A versioned pipeline applies the subject policy, produces a candidate and optional mask, creates/regenerates a display-only source preview, records metrics, and routes the item to review.
6. A human compares the source preview and candidate and approves, rejects with a reason, requests reprocessing, or selects a previous candidate.
7. Batch closure depends on processing/review resolution, not export.
8. Any number of independent export jobs may copy an approved candidate to `exports/` using an immutable naming-policy snapshot and record output checksum/destination.

Small ad-hoc browser upload is a later, secondary workflow and is never the high-volume path.

## Functional Requirements

### Storage and ingestion

- Activate only server-configured roots and expose only aliases, health/capabilities, and safe relative paths.
- Reject traversal, client absolute paths, symlink/junction/reparse escape, unsupported types, and inaccessible entries.
- Scan without retaining a complete directory listing or file in memory; allow pause, resume, cancellation, and reconnect recovery.
- Record preliminary identity by logical path plus observed size/mtime, then use streamed content SHA-256 as the authoritative duplicate signal.
- Changed content at the same path creates a new `SourceObservation`; batch membership references the exact observation processed.
- The application must never write to, rename, move, delete, truncate, or intentionally modify a source file or its application-visible content metadata. Source content SHA-256 must remain unchanged. Operating-system, filesystem, antivirus, or mount-driven access-time changes are outside this guarantee.

### Processing

- Run asynchronously while the browser is closed.
- Use a reproducible pipeline with BiRefNet primary and rembg fallback adapters.
- Apply the selected SubjectMode; preserve aspect ratio, visible text, colors, geometry, holes, and real fine structures where segmentation supports them.
- Never generate, reconstruct, inpaint, or add product components.
- Allow an optional `DeterministicContactShadowStage` derived only from the real product mask. It is disabled by default until benchmarked and never modifies product pixels.
- Produce versioned candidates; internal candidates may be RGBA when needed. Final export always flattens to the specified RGB production format.
- Apply only bounded lighting, denoise, and sharpening operations; record every parameter and artifact checksum.
- Retain processing failures and candidate versions without silent overwrite.

### Quality and review

- Calculate explainable checks for dimensions/format, background, mask topology, subject-mode consistency, clipping, margins, blur/noise, color, contact-shadow bounds, and warnings.
- Treat segmentation confidence and quality score as prioritization signals, never evidence of semantic correctness.
- Offer source-preview/candidate comparison, optional mask, warnings, version history, RTL-safe keyboard navigation, and explicit per-item or selected bulk actions.
- For rollout one, every production export requires an explicit human approval. Automated scoring cannot create an approval or production-final image. Future auto-approval requires a later ADR and benchmark evidence.
- Record actor, timestamp, reason, selected version, and correlation ID for every decision.

### Reprocessing and review cycles

- Every Batch starts with `review_cycle = 1`. `review_completed` and `partially_completed` close the current cycle but may be reopened only by an authorized explicit BatchImage reprocess command.
- Reopening creates a new ProcessingRun, moves the image to `reprocess_queued`, moves Batch to `processing`, increments the cycle once, records actor/time/reason, and emits an audit event in one transaction.
- Reprocess requests added while Batch is already `processing` or `awaiting_review` stay in the current cycle; `awaiting_review` moves to `processing` so the run may execute. Idempotent repeats and additional requests in that open cycle do not increment again.
- Cancelled/failed Batches cannot reopen through normal reprocessing. Prior CandidateVersions, ReviewDecisions, and ExportJobs remain immutable; the new candidate requires a new human decision before Batch closes again.

### Export

- Export is independent from BatchImage and Batch completion state.
- One approved candidate may appear in multiple independent ExportJobs.
- Every ExportJob snapshots an immutable versioned naming policy before it starts, including naming source/SKU mode, sanitization, Unicode, collision, suffix/extension, maximum length, directory grouping, case, and duplicate-output behavior.
- Export only PNG, 2000 × 2000, 8-bit sRGB RGB, no alpha, with exact-white canvas pixels outside the product and any enabled bounded contact shadow.

### Operations and sessions

- Recover durable work from PostgreSQL after restart; reconcile stale leases and incomplete writes.
- Show independent derived counts for approved, rejected, unresolved, processing-failed, and exported-at-least-once items.
- Use named local accounts, Argon2id password hashes, and revocable PostgreSQL-backed browser sessions with secure cookies and CSRF protection; browser JWT and OAuth are out of scope.
- Support CPU operation and an optional later NVIDIA worker without changing domain use cases.

## Non-Functional Requirements

- **Safety:** source content is application-immutable; derived writes use temporary files, checksum verification, and atomic same-volume rename.
- **Scale:** tens of thousands of images per batch with bounded scan and worker memory.
- **Durability:** PostgreSQL holds all business/session state; Redis loss cannot lose an accepted decision.
- **Security:** authenticated access, with loopback/local-host-only browser access for the Internal Pilot; fixed-role authorization, revocable sessions, CSRF/CORS controls, path containment, and server-configured mounts remain required.
- **Portability:** Windows 11, Docker Desktop, WSL2, and Linux containers are the baseline; CPU is required.
- **Auditability:** append-only events, immutable candidate artifacts, and preserved export/name snapshots.
- **Accessibility/localization:** `fa-IR`/RTL first, direction-independent hotkeys, visible focus, Persian font assets later, and no color-only signals.

## Acceptance Criteria

- A 10,000-file synthetic tree scans incrementally with bounded memory, resumable progress, exact source observations, and streamed hashes.
- API clients cannot create a root from a host path or escape an enabled configured root using traversal, alternate separators, Unicode/case tricks, symlinks, junctions, or reparse points.
- The application performs no write/rename/move/delete/truncate against sources and source SHA-256 remains unchanged; tests do not assert OS-maintained access time.
- Changed bytes at the same logical path produce a new SourceObservation and do not silently alter an existing BatchImage.
- Concurrent candidate finalization produces unique UUIDs and gap-tolerant per-BatchImage `version_no` values without collision.
- Every candidate identifies source-observation checksum, subject mode, pipeline/model/preset versions, parameters, environment facts, and output checksum.
- Every exported file maps to one human-approved candidate, one immutable naming-policy snapshot, and durable audit events; export failure does not change BatchImage approval/processing state.
- Production exports decode as PNG, exactly 2000 × 2000, 8-bit sRGB RGB with no alpha; all canvas pixels outside product and any enabled bounded shadow are `#FFFFFF`.
- Source previews contain only EXIF orientation normalization and display resize, never replace originals, and expose no host path.
- Session revocation, idle/absolute expiry, rotation, logout-all, password-reset revocation, CSRF, and fixed permission matrix pass integration tests.
- Persian filenames/paths, `fa-IR` RTL layouts, LTR technical fields, timezone display, and direction-independent review hotkeys pass acceptance tests.
- Known subject/segmentation/shadow hard cases are warned and reviewed; no score creates a production approval.
- Reprocessing an approved image in a `review_completed` Batch atomically creates one run, changes Batch/Image to `processing`/`reprocess_queued`, and increments `review_cycle` exactly once; an idempotent repeat creates neither another run nor increment.
- Reprocessing a processing-failed image in a `partially_completed` Batch follows the same controlled reopen; two requests in one open cycle increment only once.
- Cancelled/failed Batch reprocess requests and worker tasks without a valid current-cycle command are rejected without reopening.
- Reopen preserves all prior CandidateVersions, ReviewDecisions, and completed ExportJobs; every new candidate receives a new human decision.
- `manual_subject_review_required` always routes an automatically segmented candidate to human review, never auto-finalizes it, and allows another preset/engine through reprocess without claiming an interactive mask editor.
- Cross-BatchImage selected candidate, ReviewDecision candidate, and ExportItem candidate references are rejected; ExportItem also requires the effective approved candidate.

## Out of Scope for MVP

- Generative completion, reconstruction, relighting, or component invention
- Unrestricted filesystem browsing or direct host-path submission
- Cloud processing or paid APIs
- Dynamic permission/role editors and per-root user grants
- JWT browser authentication, OAuth, public internet exposure, and real-time collaborative editing
- Microservices, Kubernetes, Kafka, GraphQL, event sourcing, image blobs in PostgreSQL, and distributed multi-region operation
- Automatic production approval and S3/object storage in the initial release
- Interactive manual mask editing and subject painting are not part of the MVP; adding a mask/polygon/subject editor requires a future ADR and implementation sprint

## Remaining Product Questions

- Formal framing and margin rules by product category
- Retention periods for rejected candidates, masks, previews, sessions, and audit events
- Maximum supported batch size and measurable throughput target on named baseline hardware
- Final SKU source/integration and the default export naming-policy values within the now-defined snapshot schema
