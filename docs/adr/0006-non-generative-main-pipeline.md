# ADR 0006: Keep the Main Pipeline Non-Generative

- Status: Accepted
- Date: 2026-07-15

## Context

Product photographs contain factual geometry, labels, colors, and components. Generative restoration or completion can create plausible but false product content, conflicting with catalog authenticity and offline/no-paid-API constraints.

## Decision

The production pipeline may segment existing pixels, refine masks conservatively, apply bounded deterministic color/noise/sharpness transforms, scale uniformly, and composite on white. It may optionally derive a low-opacity neutral contact shadow only from the real placed product mask. That `DeterministicContactShadowStage` is preset-controlled, disabled by default pending benchmarks, renders behind the product, and never changes product pixels. The pipeline must not inpaint, reconstruct, hallucinate, add components, warp geometry, or use a generative image model. SubjectMode governs which physically present foreground objects are expected; ambiguity routes to human review/failure rather than synthetic correction.

## Consequences

- Authenticity is prioritized over matching every manually/generatively edited reference.
- Some raw photos cannot reach the visual target automatically and must be re-shot or manually handled outside the pipeline.
- Stage provenance and bounds are testable and explainable.
- A mask-derived shadow is a reproducible compositing effect, not product generation, but can be disabled when it reduces authenticity.
- Segmentation itself remains uncertain; non-generative does not mean semantically infallible.

## Rejected Alternatives

Generative fill/relighting could improve aesthetics but cannot guarantee product truth. A hidden generative fallback would make outputs unauditable and violate the primary requirement.
