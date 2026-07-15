# Deployment

This document is authoritative for the supported initial topology, external-drive mounts, profiles, backup/restore, and upgrades. No deployment configuration is created in Sprint 0.

## Supported Initial Topology

The baseline is a Windows 11/Windows Server host capable of running Linux containers through Docker Desktop/WSL2 or an approved equivalent:

- one web container;
- one FastAPI container;
- one PostgreSQL container with a dedicated persistent volume;
- one Redis container with bounded disposable storage;
- one CPU image-worker container;
- one maintenance/export worker container;
- an external drive mapped into only the processes that need it.

API/web ports bind to the approved LAN interface/firewall scope. PostgreSQL and Redis use an internal network only. Container images and dependency/model versions are pinned. Services run non-root with health checks and resource limits.

Native Windows services are not the initial supported profile because Celery/PyTorch/process behavior would create another test matrix. If Docker/WSL availability or licensing blocks a site, evaluate and document a native deployment without changing domain/storage contracts.

## External-Drive Mapping

Example host `E:\GhatehIran-Images` maps to container `/data/shared`. The client sees only a storage-root alias. Prefer separate read-only input and writable derived mounts if the filesystem layout permits:

- `/data/shared/inbox`: read-only
- `/data/shared/{working,candidates,masks,previews,exports,temp}`: read/write, narrowly assigned
- `/models`: read-only to image workers after administrator installation/verification

Docker/WSL drive sharing, NTFS/exFAT semantics, volume identity, reparse points, permissions, flush/atomic rename, and disconnect behavior are deployment acceptance tests. Do not run the host or containers as administrator solely to avoid permissions work.

## CPU Profile

CPU operation is mandatory. Start one image-worker process with one active image task until model RAM and throughput are measured. Configure scan/export concurrency separately, bound memory/CPU, prefetch one, recycle processes, and retain headroom for PostgreSQL and the host UI. The selected BiRefNet variant must pass memory/latency tests; otherwise the documented fallback/engine decision is revisited rather than causing unsafe swapping or host instability.

## Future NVIDIA GPU Profile

The optional profile requires compatible NVIDIA hardware, host driver, container toolkit/WSL GPU support, pinned CUDA/PyTorch builds, model checksum verification, GPU health metrics, and a dedicated `image.gpu` worker. CPU remains a functional fallback but not a silent per-run substitution: engine/device changes are recorded in a new run. GPU rollout follows reproducibility and tolerance benchmarks.

## Configuration and Secrets

Environment-specific root mappings, URLs, credentials, allowed origins, retention, concurrency, limits, and model installation references live outside source control. Non-secret defaults are versioned later. Secrets use restricted files or an approved local facility and are rotated. Startup validates configuration and refuses unsafe wildcard/root mappings.

## Backup and Restore

- PostgreSQL: scheduled consistent backups with retention, encryption/access control, checksum, and periodic restore drills.
- Artifacts: separate version-aware backup for candidates/exports and manifests/checksums; originals follow the business's source-media backup policy.
- Configuration: protected backup of root aliases/mappings, secrets recovery procedure, model manifest, and deployment version—not plaintext secrets in Git.
- Redis: no business backup requirement.

Restore order is configuration/secrets, PostgreSQL, artifact trees, then model installations by checksum. Run migrations in controlled mode, start without dispatch, reconcile file/database manifests and root identities, then enable workers. Missing files are reported; never mark them present from database records alone.

## Upgrade and Rollback

1. Announce maintenance and stop new batch/export commands.
2. Drain or cooperatively stop workers; reconcile leases/partials.
3. Back up and verify PostgreSQL plus artifact/config manifests.
4. Pull pinned signed/checksummed images and run preflight compatibility checks.
5. Apply backward-compatible expand migrations before new code; deploy API/workers/web; run smoke checks.
6. Enable dispatch gradually and monitor.
7. Contract/remove old schema only in a later release.

Rollback uses previous images while schema remains backward compatible. A destructive migration or artifact-format change requires a tested forward-fix/restore plan and explicit maintenance window. Preset/model revisions are immutable, so existing runs remain explainable.

## Operations

Start automatically after host boot only after the drive/root and database health checks. Graceful shutdown stops claims before container termination. Document operator procedures for drive connect/disconnect, low disk, model install, backup, restore, restart, queue recovery, and log collection. LAN exposure and TLS certificate management are site decisions that must be resolved before production.
