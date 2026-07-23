# Planning Recommendation Engine

## Purpose

The Planning Recommendation Engine is the decision boundary between Planning Context and Planning Proposal generation.

It answers:

- what should be created;
- what should be reused;
- what should be modified;
- what should remain unchanged;
- why the selected strategy is safer than the alternatives.

It does not create planning hierarchy artifacts or write to Azure DevOps.

## Pipeline

```text
Approved Requirement Summary
  -> Reviewed Planning Context
  -> Planning Recommendation
  -> Human Approval
  -> Planning Proposal
  -> Planning Approval
  -> Azure DevOps preview and synchronization
```

The production `RequirementPlanningService` requires both a reviewed Planning Context and an approved, current Planning Recommendation. A recommendation is rejected when its context identifier or context version no longer matches.

## Inputs

The engine consumes the persisted Planning Context only. That context already contains normalized evidence from:

- Requirement Analysis;
- Azure DevOps work items, hierarchy, sprint, active development, and open pull requests;
- Repository Intelligence and repository-ranked engineering structure;
- Engineering Memory and architecture decisions;
- similarity, impact, classification, and readiness analysis.

The engine does not rebuild context from raw requirement text or broad project data.

## Output

`PlanningRecommendation` is persisted and versioned. It includes:

- selected strategy and confidence dimensions;
- engineering reasons and rejected alternatives;
- recommended actions;
- similar work, active development, pull requests, dependencies, architecture decisions, and reusable components;
- business, engineering, repository, sprint, and risk impact;
- at least one alternative with advantages and trade-offs;
- a pre-proposal Planning Diff;
- approval and override history;
- project and correlation lineage.

Supported strategies are `NEW_INITIATIVE`, `NEW_FEATURE`, `EXTEND_EXISTING_FEATURE`, `EXTEND_EXISTING_EPIC`, `MODIFY_EXISTING_STORY`, `BUG_FIX`, `ENHANCEMENT`, `TECHNICAL_DEBT`, `REFACTOR`, `SPIKE`, and `AI_RECOMMENDED`.

## Planning Diff

The recommendation diff is an intended change set, not a generated hierarchy. Operations are:

- `Create`
- `Modify`
- `Reuse`
- `Ignore`
- `Merge`
- `Split`
- `Delete`
- `Move`

It exists before Planning Proposal generation so reviewers can understand scope and duplicate avoidance without creating artifacts.

## Approval Rules

- A recommendation can only be built from a completed, reviewed Planning Context.
- A Planning Proposal cannot be generated without an approved recommendation.
- Context refresh or classification changes invalidate the UI's current recommendation.
- A stale recommendation cannot be used when its Planning Context version changes.
- Regeneration and override create a new recommendation version and return it to `PendingReview`.
- Overrides require an actor and a reason.

## API

```text
POST /planning/recommendation
GET  /planning/recommendation/{id}
POST /planning/recommendation/regenerate
POST /planning/recommendation/approve
POST /planning/recommendation/override
```

The workspace exposes a dedicated review stage with recommendation summary, impact, Planning Diff, existing work, alternatives, reasoning, override, approval, and a separately unlocked `Continue to Planning Proposal` action.
