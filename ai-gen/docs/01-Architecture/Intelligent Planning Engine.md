# Intelligent Planning Engine

## Purpose

The Intelligent Planning Engine turns an approved Requirement Summary into an evidence-based Planning Proposal. It does not write to Azure DevOps and it does not call Azure DevOps directly.

## Pipeline

```text
Approved Requirement Summary
  -> Planning Context
  -> Synchronized Azure DevOps backlog analysis
  -> Repository Intelligence snapshot
  -> Approved Engineering Memory retrieval
  -> Planning Recommendation
  -> Planning Proposal
  -> Planning Diff
  -> Human approval
  -> Approved Azure DevOps Automation preview/apply
```

The synchronized backlog is read through the HEI Platform SDK cache. Repository Intelligence remains the authority for repository evidence. Engineering Memory is supporting evidence and is limited to approved or indexed memory.

## Planning Modes

- `NEW_INITIATIVE`: no related backlog exists.
- `NEW_FEATURE`: a related Epic exists and can be extended.
- `EXTEND_FEATURE`: a related Feature exists and can be extended.
- `MODIFY_EXISTING`: an existing item closely matches the requirement.
- `BUG_OR_ENHANCEMENT`: the approved requirement expresses corrective work.
- `AI_RECOMMENDED`: evidence exists, but no deterministic boundary is strong enough to select another mode.

## Planning Diff

Planning Diff is the human-readable approval contract between Planning Intelligence and Azure DevOps automation. Each proposed work item is classified as `Create`, `Modify`, `Keep`, `Replace`, `Merge`, `Split`, `Ignore`, or `Link`.

Modify entries retain the synchronized work-item ID and revision and show field-level before/after values. Keep entries remain visible so reviewers can see that HEI considered existing work and intentionally proposed no write.

Synchronization requires both an approved current Planning Diff and an approved, locked Planning Pack. The automation service then performs its existing dry-run, permission, idempotency, revision, and audit checks. A changed source revision blocks the write and requires re-review.

## Public APIs

- `POST /planning/context`
- `POST /planning/analyze`
- `POST /planning/recommend`
- `POST /planning/generate`
- `GET /planning/{planningPackId}/diff`
- `POST /planning/{planningPackId}/diff/approve`
- `POST /planning/{planningPackId}/sync`

`/planning/{planningPackId}/sync` returns an automation preview by default. Applying changes requires `apply: true` and the complete approved automation request, including connection, project, executor, reason, and idempotency key.

## Safety Rules

- Raw input cannot bypass Requirement Intelligence.
- Existing Epics and Features above the duplicate threshold are never proposed as duplicate creates.
- Repository paths are not invented.
- Engineering Memory cannot override current synchronized or repository facts.
- No Planning Intelligence component owns an Azure DevOps client.
- No Azure DevOps write occurs during context, analysis, recommendation, generation, or diff approval.
