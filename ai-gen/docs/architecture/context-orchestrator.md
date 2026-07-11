# Context Orchestrator

## Purpose and responsibilities

The Context Orchestrator is the centralized, deterministic entry point for assembling HEI context. It retrieves through adapters over existing systems, normalizes candidates, ranks and filters them, enforces project and repository boundaries, applies a model-safe token budget, preserves provenance, stores diagnostics, and emits platform activity, audit, and event records. It does not call an LLM and it does not replace existing context builders in Milestone 3.1.

## Pipeline

`Validate request -> resolve/retrieve snapshot -> retrieve sources -> normalize -> rank -> filter policies -> budget -> build/store result -> publish activity and events`

Each source failure is isolated. Permitted planning, memory, or workspace context can still be returned when repository intelligence is unavailable.

## Source adapters

Adapters implement `IContextSource.retrieve(ContextRequest)` and return availability, freshness, version, warnings, diagnostics, and raw items. The shipped adapters reuse Planning request data, Repository Intelligence, Engineering Memory, and local workspace evidence. `StaticServiceContextSource` provides an injection point for existing Knowledge Registry, Engineering Standards, and Validation History services without copying their storage or retrieval logic.

Repository adapters report one explicit mode:

- `CodeIndexed`: files, symbols, APIs, tests, and direct graph evidence are allowed.
- `KnowledgeSnapshot`: only snapshot modules, flows, dependencies, standards, and project knowledge are allowed. File paths and code symbols are never synthesized.
- `Unavailable`: repository candidates are omitted and a warning is returned.

## Ranking and filtering

`ContextRankingEngine` is deterministic. Default weights are intent relevance 30%, repository evidence 20%, artifact lineage 15%, purpose suitability 15%, knowledge/memory match 10%, and freshness 10%. Weights are constructor-configurable.

`ContextFilter` rejects low-confidence, rejected-planning, blocked-module, blocked-flow, duplicate, overly broad repository, and disallowed cross-project memory candidates. Every rejection retains the candidate and a machine-readable reason. Direct repository evidence is preferred over inference.

## Token budgeting

`ContextBudgetManager` reserves system/output tokens, supports purpose-specific allocations, selects whole candidates only, and omits the lowest-ranked candidates first. It never slices candidate content or structured JSON. Results report maximum, reserved, selected, and omitted token estimates. Small model callers (including Phi) set `options.maxTokens` and `options.reservedTokens`.

## Security boundaries

The API returns normalized candidate summaries, not unrestricted backing stores. Cross-project memory is rejected unless `allowOrganizationMemoryReuse` is explicitly enabled. Repository snapshot mode prevents invented code evidence. Correlation IDs flow through stored results, events, activity, and audit records. Source exceptions are sanitized to bounded diagnostics.

## API example

```http
POST /context/orchestrate
Content-Type: application/json

{
  "requestId": "ctx-101",
  "correlationId": "corr-101",
  "purpose": "DeveloperPrompt",
  "projectId": "project-a",
  "repositoryId": "repo-a",
  "artifact": {
    "artifactId": 42,
    "artifactType": "Story",
    "title": "Add contextual diagnostics",
    "description": "Expose selected and omitted context evidence."
  },
  "options": {"maxTokens": 4000, "minimumConfidence": 0.55}
}
```

Read the stored result with `GET /context/requests/{requestId}`, bounded diagnostics with `GET /context/requests/{requestId}/diagnostics`, and subsystem health with `GET /context/health`. Platform health also includes the orchestrator, ranking engine, budget manager, and source statuses.

## Migration strategy

Existing Planning, Implementation Package, Developer Prompt, Validation, QA, Agent Runtime, and editor flows continue using their current builders. Later milestones can migrate one consumer at a time to `IContextOrchestrator`; compatibility adapters can translate orchestration results into a legacy builder contract where required. No existing route or builder is removed by this foundation.
