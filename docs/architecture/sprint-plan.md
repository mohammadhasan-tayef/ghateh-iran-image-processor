# Incremental Sprint Plan

Sprint numbers are architectural increments, not fixed calendar durations. Each sprint begins only when its entry criteria are accepted and ends with a reversible, tested increment. Product authenticity and original immutability are release gates throughout.

## Sprint 0 and 0.1 — Architecture, Specification, and Corrections (current)

- **Entry:** project purpose and constraints available.
- **Deliverables:** the documents, ADRs, and corrected diagrams indexed by the README, including session/authentication, source observations/previews, SubjectMode/shadow, export separation, fixed roles, localization, naming snapshots, and deployment baseline.
- **Checks:** internal link/terminology/diagram review, state/entity/storage/API consistency, obsolete-term search, stakeholder review.
- **Exit:** decisions accepted or explicitly reopened; open product questions assigned.
- **Rollback:** documentation commit can be reverted without runtime impact.

## Sprint 1 — Repository Toolchain and Walking Skeleton

- **Entry:** Sprint 0.1 approved; remaining product questions do not block the walking skeleton.
- **Deliverables:** Python 3.12 and TypeScript/Node.js 22 LTS workspaces; exact compatible patch/image pins; Windows 11/Docker Desktop/WSL2 Linux-container developer baseline; formatting/lint/type/test configuration; FastAPI health/version endpoint; `fa-IR` RTL React shell/status page; PostgreSQL 17 migration harness; Redis 7.x connectivity/health configuration; configuration validation; CI and dependency-boundary checks. No image processing.
- **Tests:** unit smoke, API contract, RTL frontend smoke, PostgreSQL/Redis bootstrap, server root-config validation, secret/config failure.
- **Exit:** reproducible local developer workflow; no production feature claims; quality gates pass.
- **Dependencies:** official compatible images/releases for Python 3.12, Node.js 22 LTS, PostgreSQL 17, and Redis 7.x; exact patches pinned during the sprint.
- **Rollback:** remove skeleton/runtime without data migration beyond an empty baseline.

## Sprint 2 — Identity, Storage Roots, and Safe Ingestion

- **Entry:** allowed formats/limits and default retention decisions assigned; fixed authentication/root/source-observation policies approved.
- **Deliverables:** named accounts, Argon2id, UserSessions/CSRF, fixed-role authorization, server-configured root activation, safe logical path/listing, Batch/BatchImage, incremental SourceObservation/hash registration, source previews, pagination, audit/outbox foundation.
- **Tests:** session/CSRF/role matrix, Windows traversal/reparse/Unicode, 10k scan/memory, exact observations/duplicates, disconnect/different-volume resume, preview purity.
- **Exit:** sessions revoke/expire correctly; sources register without application mutation or path exposure; exact observation and scan recovery demonstrated.
- **Rollback:** disable scans; preserve registered metadata/audit.

## Sprint 3 — Queue Foundation and Pipeline Feasibility Spike

- **Entry:** representative licensed fixtures and baseline CPU hardware available; model license/source approved.
- **Deliverables:** Redis/Celery dispatch, leases/idempotency/reconciliation, model registry verification, BiRefNet/rembg adapter benchmark spike, non-generative pipeline contract, no operator production promise.
- **Tests:** Redis/worker loss, duplicate tasks, CPU memory/latency, GPU feasibility if available, hard-case segmentation evaluation.
- **Exit:** engine/model variant and capacity thresholds accepted or ADR 0008 reopened with evidence.
- **Rollback:** disable dispatch; PostgreSQL intents remain; remove model installation safely.

## Sprint 4 — Candidate Pipeline and Automated QC

- **Entry:** Sprint 3 feasibility gate passes; framing/color thresholds and fixture baselines approved.
- **Deliverables:** versioned SubjectMode-aware stages including `manual_subject_review_required`, atomic candidate/mask artifacts, conservative correction, optional default-off deterministic contact shadow, 2000 × 2000 candidate composition, QC vector/warnings, provenance, concurrency-safe CandidateVersion allocation. No interactive mask editor.
- **Tests:** mandatory subject-review routing, shadow/stage unit/property, concurrent finalization, golden/tolerance, source immutability, orphan/partial recovery, CPU/hardware variance.
- **Exit:** candidates are reproducible/explainable and unsafe hard cases route warnings; no automatic final export.
- **Rollback:** deactivate preset/pipeline revision; retain artifacts/history.

## Sprint 5 — Human Review

- **Entry:** decision/reason policy and accessibility acceptance agreed.
- **Deliverables:** paginated review queue, authorized SourcePreviewArtifact/candidate/mask media, Persian RTL side-by-side/version view, direction-independent keyboard flow, approve/reject/reprocess/select previous, controlled Batch reopen with review-cycle audit, explicitly selected bulk review, immutable decisions. Interactive mask painting/polygon subject editing remains out of scope.
- **Tests:** fixed-role authorization, controlled reopen/idempotency/cycle fencing, state races, RTL/accessibility/hotkeys, large queue UI, candidate supersession/audit/export-history preservation.
- **Exit:** every candidate can receive a traceable human decision; rollout-one mandatory-review policy enforced.
- **Rollback:** disable review mutations; preserve decisions and processing.

## Sprint 6 — Verified Export and Operational Recovery

- **Entry:** default values for the approved naming-policy snapshot and artifact retention are accepted.
- **Deliverables:** independent ExportJob/ExportItem lifecycle, immutable naming snapshot, atomic verified 2000 × 2000 8-bit sRGB RGB PNG (no alpha), restart/disconnect reconciliation, metrics, backup/restore/runbooks.
- **Tests:** naming Unicode/case/collision/duplicate behavior, final color type, multiple jobs per candidate, low space/disconnect/kill/stale worker, backup restore, approval/export race.
- **Exit:** only human-approved candidates export; export outcomes never change Batch/BatchImage resolution; no partial/transparent finals; audit/restore demonstrated.
- **Rollback:** stop export queue; approved candidates remain safe and retryable.

## Sprint 7 — Pilot Hardening

- **Entry:** representative operator site/hardware/reference set and security owner available.
- **Deliverables:** capacity tuning, security remediation, UX fixes, installer/upgrade rehearsal, operator training, pilot acceptance report.
- **Tests:** full E2E, 10k+ batch soak, penetration/threat checks, recovery game day, CPU baseline and optional GPU profile.
- **Exit:** signed operational acceptance and known-limit documentation. Auto-approval remains out of scope unless separately designed and approved.
- **Rollback:** restore prior pinned release/database backup under rehearsed plan; preserve source and audit evidence.

## Cross-Sprint Rules

Schema/artifact changes use expand/migrate/contract and immutable revisions. A sprint cannot silently regenerate baselines, mutate sources/candidates, let a worker reopen a Batch, repeatedly increment one open review cycle, merge export state into BatchImage, imply an unplanned mask editor, replace PostgreSQL truth with Redis/Celery, weaken mandatory human approval, or begin its successor to conceal unmet exit criteria. Each seam is implemented only with its owning security/recovery tests.
