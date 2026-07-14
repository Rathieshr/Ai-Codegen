# Azure DevOps Work Item Intelligence

## Purpose

Milestone 6.3 analyzes synchronized Azure DevOps work items and stores HEI recommendations without changing Azure DevOps. Azure DevOps remains the system of record; recommendation approval is an HEI-only lifecycle transition until a later write-back milestone.

## Context Flow

```text
Synchronized ADO work item or manual requirement
  -> Context Orchestrator
     -> Planning lineage
     -> Repository Intelligence
     -> Knowledge Registry
     -> Engineering Memory
     -> ranking, filtering, and token budget
  -> Planning Intelligence
  -> deterministic requirement analysis
  -> persisted WorkItemRecommendation records
```

The analyzer does not call Azure DevOps read-through or write services. Existing work items are resolved from the centralized synchronization cache. Manual and imported requirements enter through the same context pipeline.

## Outputs

Analysis includes requirement quality, normalized title, business goal, problem statement, missing and ambiguous information, capability and decomposition recommendations, acceptance-criteria quality, duplicate work, dependencies, risks, story points, confidence, and evidence.

Evidence records retain their selected source and reason. Repository modes are explicit:

- `CodeIndexed`: direct Repository Intelligence evidence is available.
- `KnowledgeSnapshot`: metadata is available, but code evidence and file paths are not invented.
- `Unavailable`: analysis continues with lower confidence and a repository warning.

## Recommendation Lifecycle

Recommendations use `Draft`, `NeedsReview`, `Approved`, `Rejected`, `Applied`, and `Stale` states. `Applied` is reserved for future approved write-back.

When the synchronized ADO revision changes, all recommendations for an older revision become `Stale`. Stale recommendations cannot be approved or rejected; they must be regenerated against the current revision.

Approval and rejection store the actor and timestamp only in HEI. They never update work-item fields.

## APIs

- `POST /ado-intelligence/work-items/{id}/analyze`
- `GET /ado-intelligence/work-items/{id}/recommendations`
- `POST /ado-intelligence/recommendations/{id}/approve`
- `POST /ado-intelligence/recommendations/{id}/reject`
- `POST /ado-intelligence/recommendations/{id}/regenerate`

The analyze request may identify a synchronized project and repository, or provide `manualRequirement` / `importedRequirement`. A compact `knowledgeRegistry` override is supported for callers that already hold an approved snapshot.

## Security And Boundaries

- No ADO write API is called.
- No recommendation is applied automatically.
- No broad repository or Knowledge Registry dump bypasses Context Orchestration.
- Repository evidence is never fabricated in snapshot or unavailable modes.
- Unrelated capability, module, and flow context is retained as rejected context rather than leaking into recommendations.
