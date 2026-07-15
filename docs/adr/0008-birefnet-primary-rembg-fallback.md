# ADR 0008: BiRefNet Primary with rembg Fallback

- Status: Accepted provisionally
- Date: 2026-07-15

## Context

Background removal needs a self-hosted CPU-capable segmentation engine with optional GPU acceleration. Product hard cases and Windows/container resource constraints are not yet benchmarked on the approved reference set.

## Decision

Define a segmentation Strategy and use a verified BiRefNet adapter as the primary planned engine, with a rembg adapter available for an explicit fallback/reprocess policy. Engine, model version/checksum, parameters, device, and warnings are recorded per run. Fallback is not silent blending and receives identical QC and mandatory human review.

This decision is provisional until the Sprint 3 feasibility gate measures license acceptability, model provenance, CPU memory/latency, GPU compatibility, mask authenticity, and hard-case performance. A blocking result reopens this ADR without changing the domain/pipeline contract.

## Consequences

- The architecture can compare engines and preserve previous candidates without vendor/cloud dependency.
- Model weights are large external installations verified by checksum, not Git assets.
- PyTorch/CUDA/Windows-container compatibility and model loading security are material risks.
- Multiple engines increase fixture, deployment, and support matrices.

## Rejected Alternatives

Hard-coding one engine prevents evidence-based replacement. Cloud APIs violate offline/self-hosted constraints. Generative background replacement violates [ADR 0006](0006-non-generative-main-pipeline.md).
