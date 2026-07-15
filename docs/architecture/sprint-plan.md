# Incremental Sprint Plan

Sprint numbers are architectural increments, not fixed calendar durations. Each sprint begins only when its entry criteria are accepted and ends with a reversible, tested increment. Product authenticity and original immutability are release gates throughout.

## Sprint 0 — Architecture and Specification (current)

- **Entry:** project purpose and constraints available.
- **Deliverables:** the documents, ADRs, and diagrams indexed by the README.
- **Checks:** internal link/terminology review, state/entity/storage consistency, stakeholder review.
- **Exit:** decisions accepted or explicitly reopened; open product questions assigned.
- **Rollback:** documentation commit can be reverted without runtime impact.

## Sprint 1 — Repository Toolchain and Walking Skeleton

- **Entry:** Sprint 0 approved; local authentication choice and baseline developer environment decided.
- **Deliverables:** Python/TypeScript workspaces, formatting/lint/type/test configuration, FastAPI health/version endpoint, React shell/status page, PostgreSQL migration harness, configuration validation, CI, architecture dependency check. No image processing.
- **Tests:** unit smoke, API contract, frontend smoke, migration/bootstrap, secret/config failure.
- **Exit:** reproducible local developer workflow; no production feature claims; quality gates pass.
- **Dependencies:** Python 3.12, Node LTS selection, PostgreSQL test environment.
- **Rollback:** remove skeleton/runtime without data migration beyond an empty baseline.

## Sprint 2 — Identity, Storage Roots, and Safe Ingestion

- **Entry:** authentication policy, root mapping, duplicate policy, allowed formats/limits decided.
- **Deliverables:** accounts/RBAC, root admin/config references, safe logical path/listing, batch creation, incremental scan/chunk registration, source checksums, pagination, audit/outbox foundation.
- **Tests:** Windows traversal/reparse suite, 10k synthetic scan/memory, duplicate/redelivery, disconnect/resume, authorization.
- **Exit:** originals register without modification or absolute-path exposure; scan recovery demonstrated.
- **Rollback:** disable scans; preserve registered metadata/audit.

## Sprint 3 — Queue Foundation and Pipeline Feasibility Spike

- **Entry:** representative licensed fixtures and baseline CPU hardware available; model license/source approved.
- **Deliverables:** Redis/Celery dispatch, leases/idempotency/reconciliation, model registry verification, BiRefNet/rembg adapter benchmark spike, non-generative pipeline contract, no operator production promise.
- **Tests:** Redis/worker loss, duplicate tasks, CPU memory/latency, GPU feasibility if available, hard-case segmentation evaluation.
- **Exit:** engine/model variant and capacity thresholds accepted or ADR 0008 reopened with evidence.
- **Rollback:** disable dispatch; PostgreSQL intents remain; remove model installation safely.

## Sprint 4 — Candidate Pipeline and Automated QC

- **Entry:** Sprint 3 feasibility gate passes; framing/color thresholds and fixture baselines approved.
- **Deliverables:** versioned stages, atomic candidate/mask/preview artifacts, conservative correction, 2000 × 2000 composition, QC vector/warnings, provenance.
- **Tests:** stage unit/property, golden/tolerance, source immutability, orphan/partial recovery, CPU/hardware variance.
- **Exit:** candidates are reproducible/explainable and unsafe hard cases route warnings; no automatic final export.
- **Rollback:** deactivate preset/pipeline revision; retain artifacts/history.

## Sprint 5 — Human Review

- **Entry:** decision/reason policy and accessibility acceptance agreed.
- **Deliverables:** paginated review queue, authorized media, side-by-side/mask/version view, keyboard flow, approve/reject/reprocess/select previous, explicitly selected bulk review, immutable decisions.
- **Tests:** authorization, state races, accessibility/keyboard, large queue UI, candidate supersession/audit.
- **Exit:** every candidate can receive a traceable human decision; rollout-one mandatory-review policy enforced.
- **Rollback:** disable review mutations; preserve decisions and processing.

## Sprint 6 — Verified Export and Operational Recovery

- **Entry:** output naming/collision and retention policies approved.
- **Deliverables:** export reservations/jobs, atomic verified finals, restart/disconnect reconciliation, operational metrics/alerts, backup/restore/runbooks.
- **Tests:** collision, low space, disconnect, kill points, stale workers, backup restore, approval/export race.
- **Exit:** only human-approved candidates export; no partial finals; end-to-end audit and restore demonstrated.
- **Rollback:** stop export queue; approved candidates remain safe and retryable.

## Sprint 7 — Pilot Hardening

- **Entry:** representative operator site/hardware/reference set and security owner available.
- **Deliverables:** capacity tuning, security remediation, UX fixes, installer/upgrade rehearsal, operator training, pilot acceptance report.
- **Tests:** full E2E, 10k+ batch soak, penetration/threat checks, recovery game day, CPU baseline and optional GPU profile.
- **Exit:** signed operational acceptance and known-limit documentation. Auto-approval remains out of scope unless separately designed and approved.
- **Rollback:** restore prior pinned release/database backup under rehearsed plan; preserve source and audit evidence.

## Cross-Sprint Rules

Schema and artifact changes use expand/migrate/contract and immutable revisions. A sprint cannot silently regenerate baselines, mutate originals/candidates, replace PostgreSQL truth with queue state, or begin its successor to conceal unmet exit criteria. Each deployment seam is implemented only when its owning behavior and recovery tests exist.
