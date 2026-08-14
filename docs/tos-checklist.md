# PBI-019 — Commercial ToS / license checklist

Before selling edits to shops, confirm each item.

## Engine / model

- [x] V1 uses **fal Kontext [pro]** (commercial API path), not Dev weights without BFL commercial license.
- [ ] Read current [fal Terms](https://fal.ai/terms) for commercial / redistribution of outputs.
- [ ] Confirm fal commercial-use statement still covers your use case on pricing page.

## Your product ToS (what you tell sellers)

- [ ] You grant the seller a license to use outputs on marketplaces (Digikala, Amazon, etc.).
- [ ] Seller warrants they own / may use the **input** product photos.
- [ ] You do not claim copyright over the physical product design; outputs are editorial/derivative of their photo.
- [ ] No guarantee of marketplace acceptance; Amazon/Digikala rules remain seller responsibility.
- [ ] Refund / re-edit policy for failed QA (define % or count).
- [ ] Privacy: inputs may be uploaded to fal for processing; retention per fal policy.
- [ ] Prohibited: illegal products, IP infringement uploads, adult/violent misuse.

## Ops

- [ ] Store API keys only in env / secret store — never ship in installer.
- [ ] Log file hashes, not full images, when possible for support.
- [ ] Keep `prompt_version` with each batch for dispute resolution.

## Not allowed without extra license

- Shipping **Kontext [dev]** GGUF inside a paid Windows app as the engine.
- Using Photoroom **free** tier for commercial batch (personal-only).
