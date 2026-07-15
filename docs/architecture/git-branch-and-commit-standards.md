# Git Branch and Commit Standards

## Purpose

This document defines the repository-wide standards for Git branch names and commit messages. Predictable standards improve reviewability, preserve clear repository history, provide Sprint traceability, support automation readiness, and strengthen long-term maintainability.

Keeping these workflow rules in one authoritative document prevents them from being scattered across architecture, ownership, and Sprint-planning documents, preserving the responsibility of each existing source of truth.

## Scope

This document governs Git branch naming and commit-message conventions only. It does not define pull-request lifecycle, review-package content, merge strategy, branch deletion, GitHub templates, CI checks, Git hooks or other automation, contribution guidelines, versioning, releases, or repository settings.

## One Micro Sprint, One Branch

Each Micro Sprint must use its own branch. A branch must contain only work owned by that Micro Sprint and must not include unrelated work or work planned for a future Sprint.

Follow-up commits made while the same Micro Sprint is under review may remain on that branch when they stay within its approved scope.

## Branch Naming

### Allowed prefixes

Only these branch prefixes are allowed:

| Prefix | Use |
| --- | --- |
| `feature/` | Product or application functionality owned by the Micro Sprint. |
| `docs/` | Documentation-only work. |
| `fix/` | Correction of a defect in existing work. |
| `chore/` | Repository maintenance, project skeleton, or tooling work that does not add product behavior. |

### Required format

```text
<type>/sprint-<number-with-hyphens>-<short-kebab-case-description>
```

Rules:

- Convert periods in the Micro Sprint number to hyphens. For example, Sprint `1.1.3` becomes `1-1-3`.
- Use a short, specific, lowercase kebab-case description.
- Do not use spaces, underscores, uppercase letters, or ambiguous abbreviations.
- The branch name must identify the owning Micro Sprint through its Sprint number.
- Do not combine unrelated or future-Sprint work in the branch.

Valid examples:

```text
feature/sprint-2-1-storage-root
docs/sprint-1-1-3-git-branch-commit-standards
chore/sprint-1-2-editorconfig
fix/sprint-7-3-mask-refinement
```

### Invalid branch examples

| Invalid branch | Reason |
| --- | --- |
| `feature/sprint-2.1-storage-root-registration` | The Sprint number contains periods instead of hyphens. |
| `feature/Sprint-2-1-storage-root-registration` | Uppercase letters are not allowed. |
| `feature/sprint-2-1-storage_root_registration` | Underscores are not allowed. |
| `feature/storage-root-registration` | The owning Micro Sprint number is missing. |
| `hotfix/sprint-2-1-storage-root-registration` | `hotfix` is not an allowed prefix. |
| `docs/sprint-1-1-3-stds` | The description uses an ambiguous abbreviation. |
| `feature/sprint-2-1-storage-and-export-work` | The description combines unrelated work. |

## Commit Messages

Use Conventional Commit messages in this format:

```text
<type>: <imperative summary>
```

Only these commit types are allowed:

| Type | Use |
| --- | --- |
| `feat` | Add product or application behavior. |
| `fix` | Correct a defect in existing behavior or content. |
| `docs` | Change documentation only. |
| `chore` | Perform repository maintenance, skeleton, configuration, or tooling work without adding product behavior. |
| `test` | Add or change tests without changing product behavior. |
| `refactor` | Restructure existing implementation without changing its behavior. |

### Subject rules

- Begin the summary with lowercase text unless the first word is a proper name.
- Use the imperative mood.
- Describe the actual change clearly and specifically.
- Do not end the summary with a period.
- Do not use vague summaries such as `updates`, `changes`, `work`, or `fix stuff`.
- Do not claim work outside the owning Micro Sprint.

Valid examples:

```text
feat: register configured storage roots
fix: preserve preview image orientation
docs: define git branch and commit standards
chore: align repository structure with architecture
test: cover storage path traversal rejection
refactor: isolate storage key validation
```

### Review commits

Multiple in-scope review commits are allowed before a Micro Sprint is approved. Every review commit must:

- use a valid Conventional Commit message;
- remain within the Micro Sprint scope;
- clearly describe the correction; and
- avoid unrelated cleanup or future-Sprint work.

This document does not define how commits are combined when a branch is merged.

### Invalid commit examples

| Invalid commit | Reason |
| --- | --- |
| `update docs` | It does not use the required format and is vague. |
| `docs: updates` | The summary is vague and not imperative. |
| `feature: add storage roots` | `feature` is not an allowed commit type; use `feat`. |
| `fix: fix stuff` | The summary does not identify the actual correction. |
| `docs: Define Git standards` | The summary begins with uppercase text without a proper-name reason. |
| `docs: define git standards.` | The summary ends with a period. |
| `chore: prepare Sprint 1.2 runtime` | The message claims unrelated future-Sprint work. |

## Relationship to Existing Architecture

These standards govern Git history and developer workflow only. They do not redefine application architecture, folder ownership, module boundaries, deployment behavior, runtime configuration, or product behavior. Those decisions remain authoritative in their respective architecture documents, ADRs, and specifications.
