# Engineering Intelligence Service

## Purpose

`EngineeringIntelligenceService` is HEI's shared engineering-evidence
orchestration boundary. It does not replace or duplicate specialized
intelligence engines. It calls them and normalizes their results into one
versioned `EngineeringContext`.

```text
Requirement Intelligence
        |
        v
EngineeringIntelligenceService
        |
        +-- Repository Intelligence
        +-- Azure DevOps through HEI Platform SDK
        +-- Engineering Memory
        +-- Existing planning similarity and strategy engine
        |
        v
EngineeringContext
        |
        +-- Planning Recommendation
        +-- Execution projection
        +-- Validation projection
        +-- Future agents
```

## Ownership

Specialized providers retain their current responsibilities:

- Repository Intelligence owns snapshots, graph nodes, relationships,
  modules, APIs, files, tests, and repository health.
- Azure DevOps Integration and the HEI Platform SDK own synchronized ADO
  records. Engineering Intelligence never calls an ADO client directly.
- Engineering Memory owns approved historical knowledge and retrieval.
- The deterministic planning engine owns work-item similarity and strategy
  scoring.

Engineering Intelligence owns only orchestration, normalization, context
versioning, and consumer-specific projections.

## Canonical Contract

`EngineeringContext` contains:

- approved Requirement Summary;
- Repository Summary;
- Azure DevOps Summary;
- Engineering Memory Summary;
- Similar Work;
- Architecture and Dependency summaries;
- Repository Recommendation;
- Impact and Reuse summaries;
- Engineering Readiness;
- Planning Recommendation input;
- correlation and source-version metadata.

The context ID is derived from source versions, including the requirement,
repository snapshot, ADO revisions, and memory versions. Repository file
evidence is returned only when it exists in the Repository Intelligence graph.

## Consumer Rules

- Requirement Analysis calls `recommendRepository`; it does not implement a
  second repository selection algorithm.
- Planning Context calls `generatePlanningContext`; provider orchestration is
  no longer performed by the Planning Context service.
- Planning Recommendation receives a compatibility projection of the
  canonical `EngineeringContext`; it performs no repository, ADO, or memory
  queries.
- Execution receives only the bounded execution projection: relevant files,
  APIs, tests, pull requests, modules, architecture, and dependencies.
- Validation receives only affected tests, components, stories, APIs, and
  impact analysis.

The legacy `ProjectIntelligenceService` remains available during migration for
existing project-profile and artifact APIs. New cross-module intelligence
integration must use `EngineeringIntelligenceService`.

## Public Methods

The service exposes both Python-style and contract-style method names:

- `analyzeRequirement`
- `analyzeRepository`
- `analyzeAzureDevOps`
- `findSimilarStories`, `findSimilarFeatures`, `findSimilarEpics`
- `findExistingImplementation`, `findRepository`
- `getEngineeringMemory`
- `findReusableComponents`, `findReusableTests`, `findReusablePRs`
- `analyzeArchitecture`, `analyzeDependencies`
- `recommendRepository`, `recommendPlanningStrategy`
- `generateImpactAnalysis`, `generatePlanningContext`

## Compatibility

Persisted Planning Context records include the canonical
`engineeringContext` and retain existing fields used by current APIs and UI.
The compatibility projection is deterministic and does not retrieve new
evidence.
