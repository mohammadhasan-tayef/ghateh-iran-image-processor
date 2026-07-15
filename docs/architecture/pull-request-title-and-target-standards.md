# Pull Request Title and Target Standards

## Purpose

This document defines the repository-wide standard for Pull Request base branches, head branches, and titles. Predictable source and target relationships preserve Micro Sprint traceability, while consistent titles make each proposed responsibility clear in repository history.

## One Micro Sprint, One Pull Request

Each Micro Sprint must produce one dedicated Pull Request. Each Pull Request must represent one responsibility owned by that Micro Sprint.

A Pull Request must not contain unrelated work or work planned for a future Sprint.

## Base Branch

The Pull Request base branch is the branch that receives the proposed change.

- Pull Requests normally target `main`.
- A Pull Request must not target another feature branch.
- Stacked Pull Requests are not allowed unless they are separately designed and approved in a later Micro Sprint.

## Head Branch

The Pull Request head branch is the branch that contains the proposed change.

- The head branch must be the dedicated branch for the owning Micro Sprint.
- The head branch must follow [Git Branch and Commit Standards](git-branch-and-commit-standards.md).
- The head branch must start from the latest verified accepted `main` before Micro Sprint work begins.

## Pull Request Title

Use this required format:

```text
<type>: <imperative summary>
```

The title must:

- use a Conventional Commit type approved by [Git Branch and Commit Standards](git-branch-and-commit-standards.md);
- describe the single responsibility of the owning Micro Sprint;
- be concise and specific;
- use an imperative summary;
- not end with a period; and
- not claim future or out-of-scope work.

### Valid examples

```text
docs: define pull request title and target standards
feat: register configured storage roots
fix: preserve preview image orientation
chore: create project skeleton
```

### Invalid examples

| Invalid title | Reason |
| --- | --- |
| `Pull Request standards` | The title does not use the required format or an approved type. |
| `feature: add storage roots` | `feature` is not an approved Conventional Commit type. |
| `docs: updates` | The summary is vague and not imperative. |
| `docs: define pull request standards.` | The title ends with a period. |
| `docs: define pull request standards and add CI` | The title combines responsibilities and claims out-of-scope work. |
| `chore: prepare Sprint 1.2 runtime` | The title claims future-Sprint work. |

## Relationship to Existing Standards

This document complements [Git Branch and Commit Standards](git-branch-and-commit-standards.md). It does not redefine branch naming or commit-message rules.

This document does not define Pull Request descriptions, Draft status, readiness, review, merge, or branch deletion. It does not change application architecture or product behavior.
