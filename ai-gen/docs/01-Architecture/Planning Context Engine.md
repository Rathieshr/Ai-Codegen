# Planning Context Engine

## Position

The Planning Context Engine runs after an approved Requirement Summary and before Planning Intelligence creates a Planning Pack.

```text
Requirement Summary
  -> Planning Context
  -> Human Review
  -> Planning Recommendation
  -> Planning Workspace
  -> Approval
  -> Azure DevOps synchronization
```

Production planning requests must provide a reviewed `planningContextId`. A changed Requirement Summary invalidates the context and requires refresh and review.

## Responsibility

The engine creates a persisted engineering-landscape record from:

- synchronized Azure DevOps work items and iterations through the HEI Platform SDK cache
- the selected Repository Intelligence snapshot and Engineering Graph
- approved, available Engineering Memory
- the approved Requirement Summary

It determines:

- existing and similar work
- repository and reusable engineering assets
- requirement classification
- likely engineering impact
- recommended create, reuse, modify, and do-not-create boundaries
- planning readiness and warnings

It does not generate a Planning Pack or write to Azure DevOps.

## Boundaries

The engine reuses the deterministic comparison logic in `planning_integration.IntelligentPlanningEngine`. The prompt-oriented context in `backend/intelligence/planning` remains a separate artifact-generation concern.

No Planning Context provider calls Azure DevOps directly. Azure DevOps evidence comes from the synchronized HEI Platform SDK cache. Repository evidence comes from Repository Intelligence. Memory is supporting evidence and never overrides current repository facts.

## Persistence

Records are stored in `planning_contexts.json` with:

- requirement and analysis versions
- context version
- repository snapshot version
- synchronized work-item revisions
- memory versions
- classification and manual override provenance
- review status and reviewer
- correlation ID

Refresh rebuilds evidence and resets review to `Pending`.

## API

- `POST /planning/context/build`
- `GET /planning/context/{id}`
- `POST /planning/context/refresh`
- `POST /planning/context/classify`
- `POST /planning/context/analyze`

`POST /planning/context/analyze` with `decision=Accept` marks a non-blocked context reviewed. Planning generation then accepts the context through `planningContextId`.

## Readiness

- `Ready`: sufficient requirement and engineering evidence
- `ReadyWithRecommendations`: planning may continue with visible evidence gaps
- `NeedsUserDecision`: close existing work requires an explicit reuse, modify, or create decision
- `Blocked`: requirement blockers prevent planning
