# Shared HEI Intelligence Entry Points

## Purpose

HEI exposes two Azure DevOps entry points without maintaining two intelligence platforms:

- **HEI Custom Hub** starts with project or requirement context.
- **HEI Work Item Tab** starts with an Epic, Feature, Story, Bug, or Task.

Both paths use `HEIIntelligenceOrchestrator` and produce the same persisted `EngineeringContext` contract.

```text
HEI Custom Hub (project first)       HEI Work Item Tab (item first)
                \                     /
                 HEIIntelligenceOrchestrator
                              |
       +----------------------+----------------------+
       |                      |                      |
Project Intelligence   Work Item Intelligence   Repository Intelligence
       |                      |                      |
       +---------- Markdown / ADO / Memory ----------+
                              |
                  Unified EngineeringContext
                              |
              Reasoning, Planning, AC, Execution
```

## Capability Inventory

| Capability | Existing authority | Shared adapter |
| --- | --- | --- |
| Project profile, approved knowledge, Markdown registry, architecture knowledge, planning history | `ProjectIntelligenceService` | `ProjectIntelligenceProvider` |
| Work-item intent, hierarchy, similar work, recommendations, acceptance quality | `AdoWorkItemIntelligenceService` | `WorkItemIntelligenceProvider` |
| Current files, modules, APIs, graph, snapshot revision | Repository Intelligence | Existing `EngineeringIntelligenceService` repository services |
| Requirement and work-item acceptance criteria | Stabilized Project Intelligence requirement AC flow | `AcceptanceCriteriaProvider` |
| Context normalization and persistence | Engineering Intelligence | `HEIIntelligenceOrchestrator` |

The adapters project existing results. They do not own new prompts or alternate reasoning rules.

## Entry Modes

The orchestrator supports `PROJECT_HUB`, `WORK_ITEM`, `REQUIREMENT`, `PLANNING`, `EXECUTION`, and `VALIDATION`. Entry mode changes the initial facts collected, not the downstream intelligence implementation.

For `WORK_ITEM`, the orchestrator loads the synchronized item and its established analysis first. For project and requirement modes, it starts from the normalized requirement. Both then call the existing Engineering Intelligence planning-context pipeline, including Project Intelligence, Repository Intelligence, Markdown, Azure DevOps, Knowledge Registry, and Engineering Memory.

When Project Intelligence identifies related work, the orchestrator asks Work Item Intelligence for bounded item-level context. The current item is deduplicated from related results.

## Canonical Context

The shared context includes:

- requirement and entry mode;
- project and current work item;
- repository and relevant documentation;
- Project Intelligence and Work Item Intelligence projections;
- related and similar work;
- architecture, dependencies, memory, reuse, impact, conflicts, and unknowns;
- evidence, provenance, lineage, versions, and correlation ID;
- a prompt-safe `promptContext`.

Each evidence record retains source type and ID, project and repository scope, work item or file reference, provider/model metadata when present, confidence, repository revision, knowledge version, and timestamp.

## Scope And Prompt Safety

Project Intelligence rejects knowledge owned by a different project. Work Item Intelligence reads only synchronized items available through the current project cache. Repository Intelligence remains authoritative for current implementation state.

Rejected or broad diagnostic context is retained under lineage for explainability, but `rejectedContext`, `rejected`, and `rawContext` are recursively removed from `promptContext`. Downstream reasoning should consume `promptContext`, not the diagnostic envelope.

## APIs

- `POST /engineering-intelligence/context`
- `GET /engineering-intelligence/contexts/{contextId}`
- `POST /engineering-intelligence/work-items/{workItemId}/analyze`
- `POST /engineering-intelligence/acceptance-criteria/generate`

The final endpoint delegates to the stabilized Project Intelligence acceptance-criteria provider. Deterministic generation remains that provider's degraded fallback policy rather than a second implementation in the shared layer.

## Shared State And Navigation

Contexts are persisted by `engineeringContextId`. Lineage carries project, repository, work item, requirement, proposal, analysis, and knowledge identifiers so either surface can reopen the same artifact.

The existing `hei.open-command-center` contribution opens `?view=planning&workItemId={id}` from a work item. Shared context responses also return this route and related work-item links. No second deep-link mechanism is introduced.

## Migration

1. Existing Project Intelligence and Work Item Intelligence remain operational.
2. Stable provider interfaces expose their mature capabilities.
3. Shared context runs alongside existing surface flows for parity testing.
4. Planning, acceptance criteria, proposals, and execution migrate to the shared context contract incrementally.
5. Duplicate reasoning is removed only after regression parity is demonstrated.

This preserves the product rule: **reuse reasoning, unify context, do not duplicate flows**.
