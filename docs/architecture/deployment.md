# Deployment Baseline

This document is authoritative for the supported developer/local topology, server-configured mounts, profiles, backup/restore, and upgrades. Sprint 0.1 creates no deployment files.

## Approved Baseline

- Windows 11 host
- Docker Desktop with WSL2 backend
- Linux containers for frontend, FastAPI API, Celery workers, PostgreSQL, and Redis
- Python 3.12
- Node.js 22 LTS
- PostgreSQL 17
- Redis 7.x
- CPU execution required
- NVIDIA GPU profile optional and deferred

Sprint 1 must select and pin exact patch versions, base-image digests/tags, Python/Node packages, and compatible PostgreSQL/Redis images using then-current official images and compatibility tests. Sprint 0.1 does not invent patch versions or install dependencies.

The Internal Pilot instantiates this topology independently on each participating operator's Windows computer: one web, one API, one PostgreSQL volume, one bounded Redis, one CPU image worker, one scan/maintenance/export worker, and configured storage attached to that computer. Storage may be an internal HDD, internal SSD, or external drive exposed through the approved configured-root abstraction.

Internal Pilot API/web entry points bind only to loopback/local-host access on the same computer; PostgreSQL/Redis remain internal. No office network, LAN browser access, VPN, shared application server, shared runtime state, centralized processing service, or cross-installation synchronization is required. This constraint selects no exact port, packaging, installer behavior, or local transport implementation. Native Windows services are not the supported baseline because they expand Celery/PyTorch test risk.

## Server-Configured Storage Mounts

Host/Docker configuration owns config keys and mounted container paths:

```yaml
storage_roots:
  external_images:
    container_path: /data/shared
    mode: read_write
```

The UI/admin API may activate/label `external_images`; it never submits `E:\...`, `/data/shared`, or another arbitrary path. Prefer a read-only `/data/shared/inbox` and narrowly writable derived directories when mount layout supports it. `/models` is read-only to workers after verified installation.

Startup and operator probes validate availability, expected/observed volume identity, case/Unicode behavior, free space, permissions, reparse controls, flush, and atomic rename. Operational rules:

- missing mount: root unavailable; dependent commands hold/fail retryably;
- drive-letter change: operator updates host/Docker mapping for the config key and re-probes;
- disconnect during scan: Batch pauses with cursor retained;
- disconnect during processing: run retries/blocks without immediate semantic failure;
- disconnect during export: ExportItem retries/fails independently;
- reconnect with different volume identity: block until explicit admin validation/rebind.

## CPU and Deferred GPU Profiles

CPU is mandatory. Start one image-worker process/active task on unknown hardware; tune only from measured model RAM/latency. Scan/preview/export concurrency is independently capped per drive. Containers have memory/CPU/scratch limits, prefetch one, and process recycling.

The later NVIDIA profile requires compatible hardware/driver, WSL2/container GPU support, pinned CUDA/PyTorch/model checksums, telemetry, reproducibility tolerances, and dedicated `image.gpu` routing. CPU remains supported but device/engine substitution creates a distinct ProcessingRun and is never silent.

## Web, Sessions, Localization, and Configuration

Environment configuration includes database/Redis URLs, allowed origins, session/CSRF secrets, idle/absolute timeouts, TLS/cookie settings, root config keys/mounts, volume identities, retention, limits, model refs, and primary `fa-IR` locale/timezone defaults. Secrets remain outside Git.

Production session cookies require TLS and `Secure`. This topology alignment creates no TLS, certificate, or cookie exception for standalone-local operation. Certificate handling for any future network-accessible deployment profile remains a deployment prerequisite subject to separate review. The frontend ships a suitable Persian font through normal versioned assets in an implementation sprint; no host font assumption and no Sprint 0.1 binary asset. Backend/database time is UTC; client display uses configured timezone.

## Backup and Restore

- PostgreSQL backups cover User/UserSession (subject to retention), source observations, runs/candidates, review, exports/naming snapshots, and audit; encrypted/access-controlled and restore-tested.
- Artifact backup covers candidates/exports/manifests; source media follows business backup policy; regenerable source previews need not be primary backups if policy agrees.
- Protected configuration backup covers root config-key mappings, volume identities, deployment/model manifests, and secret recovery—not plaintext secrets in Git.
- Redis has no business backup requirement.

Restore configuration/secrets, PostgreSQL, artifacts, and verified models; start without dispatch; reconcile roots/volume identity and file/checksum manifests; then enable workers. Expired sessions may be globally invalidated after restore as a security policy.

## Upgrade and Rollback

1. Stop new batch/export commands and drain/stop workers.
2. Reconcile leases/partials and back up database/artifact/config manifests.
3. Pull pinned verified images and run preflight compatibility.
4. Apply backward-compatible expand migrations; deploy API/workers/web; smoke-test sessions, roots, RTL UI, and state queries.
5. Enable dispatch gradually and monitor processing and export independently.
6. Contract schema only in a later compatible release.

Rollback uses previous pinned images while schema remains compatible. Destructive migrations/artifact changes require tested restore/forward-fix. Immutable preset/naming/model/source/candidate records preserve explainability.

## Operator Runbooks

Document boot/shutdown, configured-root activation, drive-letter change, missing/different-volume recovery, low disk, model verification, session/user security response, backup/restore, queue recovery, export collision, and log collection before pilot use.
