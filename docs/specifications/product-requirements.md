# Product Requirements

## Purpose and Goals

The product is an offline-capable local-network control panel for high-volume product-image processing. It registers images in approved external-storage folders without browser upload, preserves originals, produces non-generative 2000 × 2000 PNG candidates on `#FFFFFF`, supports human review, and exports only approved versions.

Success means operators can safely resume a batch after browser, process, or host interruption and can explain every exported file through durable version and audit records. Similarity to a reference style is desirable; product authenticity is mandatory.

## Users and Roles

| User | Primary needs | Proposed role |
|---|---|---|
| Operator | Create batches, monitor work, review and reprocess images | `operator` |
| Supervisor | Bulk review, manage presets, resolve failures, export | `supervisor` |
| Administrator | Configure roots, users, models, and system policy | `admin` |
| Auditor | Inspect immutable decisions and processing history | `auditor` |

One user may hold multiple roles. Least privilege applies; root configuration and user administration are admin-only.

## Primary Workflow

1. An administrator registers an allowlisted storage root using host configuration, not a browser-provided absolute path.
2. An operator selects a `root_id` and relative folder, previews a bounded scan, and creates a batch with a preset.
3. The scanner walks incrementally, validates regular image files, streams SHA-256, and commits registration chunks.
4. One idempotent processing task is dispatched per registered image subject to backpressure.
5. A versioned pipeline reads the original, creates a candidate and optional mask/preview, records metrics, and routes the image to review.
6. A human compares source and candidate and approves, rejects with a reason, reprocesses with a chosen engine/preset, or selects a previous candidate.
7. An export job atomically copies the selected approved candidate to `exports/` and records its checksum and destination key.

Small ad-hoc browser upload is a later, secondary workflow and is never the high-volume path.

## Functional Requirements

### Storage and ingestion

- Configure enabled storage roots and expose only root aliases and safe relative paths.
- Reject traversal, absolute client paths, symlinks/reparse points that escape a root, unsupported types, and inaccessible entries.
- Scan without retaining a complete directory listing in memory; allow pause, resume, cancellation, and reconnect recovery.
- Identify content by streamed SHA-256 plus byte length; preserve distinct logical assets when policy permits duplicate content.
- Never modify or delete an original through application workflows.

### Processing

- Run asynchronously when the browser is closed.
- Use a versioned, reproducible pipeline with BiRefNet primary and rembg fallback adapters.
- Extract rather than generate the product; preserve aspect ratio, visible text, colors, geometry, internal holes, and fine structures where segmentation supports them.
- Produce lossless 2000 × 2000 RGBA/RGB PNG candidates composited on exact white.
- Apply only bounded lighting, denoise, and sharpening operations; record every parameter and artifact checksum.
- Retain failures and candidate versions; never silently overwrite a version.

### Quality and review

- Calculate explainable technical checks: dimensions, format, background whiteness, alpha/mask geometry, clipping, margins, blur/noise indicators, and processing warnings.
- Treat segmentation confidence and quality score as routing signals, not evidence of semantic correctness.
- Offer source/candidate comparison, optional mask, warnings, version history, keyboard navigation, and explicit per-item or selected bulk actions.
- For rollout one, require a human approval for every exported image. Auto-approval remains disabled by policy.
- Record actor, timestamp, reason, selected version, and request correlation for every decision.

### Operations

- Recover durable work from PostgreSQL after restart; reconcile stale leases and incomplete writes.
- Provide paginated filtering, progress derived from durable counts, retry controls, cancellation, and actionable failure categories.
- Support CPU operation and an optional later NVIDIA worker without changing domain use cases.

## Non-Functional Requirements

- **Safety:** originals are read-only at the application level; final writes use temporary files, checksum verification, and atomic same-volume rename.
- **Scale:** tens of thousands of images per batch; memory use remains bounded by scan chunk and worker concurrency.
- **Durability:** PostgreSQL holds all business state; a Redis loss may delay work but cannot lose an accepted decision.
- **Security:** authenticated local-network use, role authorization, CSRF-safe browser authentication, strict origin policy, and path containment.
- **Portability:** supported on Windows with Docker Compose; CPU baseline; storage abstraction isolates host paths.
- **Auditability:** append-only processing events and immutable candidate artifacts while referenced by decisions.
- **Performance:** exact targets require baseline hardware measurement in Sprint 3; queue depth and memory enforce backpressure meanwhile.
- **Accessibility:** keyboard-operable review, visible focus, meaningful status labels, and no color-only signals.

## Acceptance Criteria

- A 10,000-file synthetic tree can be scanned incrementally with bounded memory and resumable progress.
- API clients cannot access a path outside an enabled root using traversal, alternate separators, case tricks, symlinks, or Windows reparse points.
- Original file bytes and metadata remain unchanged after processing, rejection, retry, and export.
- Re-delivery of a scan, process, review, or export command is idempotent according to its documented key.
- Every candidate identifies original checksum, pipeline version, model checksum, preset revision, parameters, environment facts, and output checksum.
- Every exported file maps to one human-approved candidate and a durable audit event.
- Restart and external-drive-disconnect tests produce recoverable states without duplicate accepted versions or partial final files.
- Review UI requirements can be exercised without loading an entire batch into the browser.
- The generated image is exactly 2000 × 2000 PNG and canvas pixels classified as background are `#FFFFFF`.
- Known hard cases are warned and reviewed; the system never represents a quality score as an authenticity guarantee.

## Out of Scope for MVP

- Generative completion, reconstruction, relighting, or component invention
- Unrestricted filesystem browsing or direct absolute-path submission
- Cloud processing or paid APIs
- Microservices, Kubernetes, Kafka, GraphQL, event sourcing, or image blobs in PostgreSQL
- Mobile-native clients, public internet exposure, collaborative real-time editing, and automatic semantic correctness claims
- Distributed multi-region operation or object storage in the initial release

## Open Product Questions

- Approved output naming convention and behavior on a destination name collision
- Formal Ghateh Iran framing/margin rules by product category
- Retention periods for rejected candidates, masks, previews, and audit events
- Required authentication source for the first site and whether auditor separation is necessary
- Maximum supported batch size and measurable throughput target on named baseline hardware
