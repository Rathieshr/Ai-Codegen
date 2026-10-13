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
        +-- Project Intelligence fact adapter
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
- Project Intelligence remains the compatibility owner for project profile,
  Knowledge Registry cache, and versioned planning artifacts created by the
  workflow-automation implementation.
- The deterministic planning engine owns work-item similarity and strategy
  scoring.

Engineering Intelligence owns only orchestration, normalization, context
versioning, and consumer-specific projections.

## Service Architecture

The implementation is split into reusable fact services under
`backend/engineering_intelligence/services`. These services adapt existing
providers; they do not rescan, recalculate, or invoke an AI model.

| Service | Responsibility | Existing authority |
| --- | --- | --- |
| `RepositoryService` | Repository summary, relevant modules/files, technology stack | Repository Intelligence |
| `MarkdownService` | Recursively discover, section-index, classify, and retrieve repository Markdown | Repository content and revision |
| `ArchitectureService` | Architecture context from repository graph facts | Repository Intelligence graph |
| `DependencyService` | Dependency context and affected modules | Engineering Graph |
| `EngineeringDiscoveryService` | Evidence-backed discovery report, source state, conflicts, unknowns, and confidence | Canonical `EngineeringContext` |
| `AzureDevOpsService` | Normalized project, open work, and similar stories | HEI Platform SDK synchronized cache |
| `SimilarityService` | Similar requirement and reusable implementation projections | Planning context and retrieved evidence |
| `MemoryService` | Approved memory search, lessons, and candidate storage | Engineering Memory |
| `ContextBuilder` | Bounded, optimized context projection | Canonical `EngineeringContext` |
| `IntelligenceOrchestrator` | Requirement, Planning, Execution, and Validation entry points | The services above |
| `ProjectIntelligenceProvider` | Relevant Knowledge Registry facts and approved historical artifacts | Project Intelligence read APIs |

The `interfaces` package contains structural contracts. `dto` re-exports the
canonical transport-neutral models. `cache` contains version-keyed context
cache primitives. `providers` is deliberately free of model-provider code.

```text
Repository Intelligence ----+
Markdown/Documents ----------+
HEI Platform SDK / ADO ------+--> fact services --> EngineeringContext
Engineering Memory ----------+                          |
Engineering Graph -----------+                          v
Project Intelligence --------+
                                               IntelligenceOrchestrator
                                                  |   |   |   |
                                      Requirement Planning Execution Validation
```

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
- a bounded `projectIntelligence` evidence block containing project
  background, intent-selected Knowledge Registry facts, approved historical
  artifacts, and rejected-context diagnostics.

The canonical contract also exposes non-opaque source collections:

- `requirement_context`
- `repository_code_context`
- `repository_markdown_context`
- `project_intelligence_context`
- `azure_devops_context`
- `engineering_memory_context`

Repository Markdown is not merged into Project Intelligence. The Markdown
collection contains selected sections, rejected-result diagnostics, source
conflicts, paths, headings, evidence IDs, classifications, authority,
content hashes, and repository revision. `knowledge_synthesis` records the
claims available from each source and the authority rules used for each claim
type.

## Engineering Discovery V2

Engineering Discovery is a deterministic projection of the canonical
`EngineeringContext`. It does not scan repositories or invoke an AI provider.
It answers what the project already knows about a requirement by combining
only relevance-selected facts from Repository Intelligence, repository
Markdown, Project Intelligence, Knowledge Registry, synchronized Azure DevOps,
and approved Engineering Memory.

Every discovery evidence item includes its source, source reference, selection
reason, confidence, and source-specific metadata. The report separates:

- `conflicts`, where two authoritative sources disagree;
- `unknowns`, where requirement information remains unresolved; and
- `sourceStatus`, where a source is pending or completed without a relevant
  match.

`DiscoveryPending` therefore means that required source synchronization has
not completed. `NoRelevantEvidence` means the source was searched successfully
but did not match the requirement. This distinction is preserved in the UI and
prevents empty search results from being presented as platform failures.

The context ID is derived from source versions, including the requirement,
repository snapshot, ADO revisions, memory versions, and Project Intelligence
knowledge version. Repository file evidence is returned only when it exists in
the Repository Intelligence graph. Knowledge-cache source-document paths are
identified separately as documentation evidence and never promoted to ranked
code files.

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

The legacy `ProjectIntelligenceService` remains available during migration.
`ProjectIntelligenceProvider` calls only `get_profile`,
`get_knowledge_cache`, and `list_artifacts`. It never invokes legacy
generation, refinement, context-capsule, repository-analysis, or provider
methods. New cross-module intelligence integration must use
`EngineeringIntelligenceService`.

Selection rules:

- Project Profile is background only.
- Knowledge Registry is fact evidence and is selected by requirement intent.
- Only approved or locked artifacts may influence similarity and reuse.
- Draft, review, rejected, archived, unrelated, and project-mismatched context
  is excluded and recorded in `rejectedContext`.
- Repository Intelligence remains authoritative for code files, services,
  APIs, graph relationships, and current repository state.
- Repository Markdown discovery recursively includes Markdown below the
  selected repository and excludes dependency, generated, vendor, build, and
  cache directories. Repository metadata may override include/exclude
  patterns, section limits, and token budget.
- Retrieval operates on document sections. It enforces project and repository
  scope, relevance, authority, deduplication, and a prompt token budget.
  Rejected sections remain diagnostics and never enter reasoning prompts.
- ADR or architecture claims that conflict with current code are reported and
  excluded from factual resolution until reviewed.

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
- `analyzeRepository`, `getRepositorySummary`
- `findRelevantModules`, `findRelevantFiles`, `findTechnologyStack`
- `indexMarkdown`, `searchDocumentation`, `getArchitectureSummary`
- `analyzeArchitecture`, `getArchitectureContext`
- `analyzeDependencies`, `findAffectedModules`
- `analyzeProject`, `findOpenWork`
- `findSimilarRequirement`, `findReusableImplementation`
- `searchMemory`, `saveInsight`, `findLessonsLearned`
- `buildRequirementContext`, `buildPlanningContext`
- `buildExecutionContext`, `buildValidationContext`

## Compatibility

Persisted Planning Context records include the canonical
`engineeringContext` and retain existing fields used by current APIs and UI.
The compatibility projection is deterministic and does not retrieve new
evidence.

`EngineeringIntelligenceService` remains the public compatibility facade.
Existing snake_case and camelCase methods continue to work. New consumers
should use `IntelligenceOrchestrator` through the facade's four `build*Context`
methods. `ProjectIntelligenceService` remains available for legacy profile,
artifact, and generation APIs while those callers migrate incrementally.

## AI Boundary

Engineering Intelligence returns facts and evidence only. It has no Phi,
OpenAI, Claude, Gemini, or other model dependency. Reasoning engines receive
the optimized context after orchestration. Missing evidence remains missing;
repository files, APIs, dependencies, and memory are never invented.
Planning Reasoning receives only selected Markdown sections, with evidence
lineage and conflict diagnostics. It must cite their evidence IDs when those
sections influence an output.

## AI-Driven Requirement Analysis

Requirement Refinement and Requirement Analysis use the shared Reasoning
Engine without moving provider code into Engineering Intelligence:

```text
User Requirement
        |
        v
Requirement Refinement V2 (provider selected by the Provider Layer)
        |
        v
Refined Requirement + RequirementIntent search hints
        |
        v
Engineering Intelligence discovery
        |
        v
Versioned EngineeringContext
        |
        v
Requirement Evidence Synthesis (Phi by default)
        |
        v
Deterministically validated Requirement Analysis
```

The refinement pass receives only the original requirement and bounded
project/product terminology. It cannot query repositories, Azure DevOps,
Markdown, Engineering Memory, or Engineering Context. The persisted artifact
always preserves the original text. The V2 artifact separately records the
executive summary, problem statement, business goal, user intent, expected
outcome, actors, capabilities, entities, engineering concepts, domain terms,
repository/Markdown/Azure DevOps search hints, possible module and feature
names, changes, reasoning, ambiguities, clarification candidates, provider,
model, prompt version, acceptance status, timestamp, and revision history.
Search hints remain discovery candidates rather than repository facts. Users
may accept, edit, regenerate, or skip; skipping keeps the stage in the lineage
while using the original text as canonical input.

`RequirementIntent` values produced during refinement are explicitly
hypotheses and search hints; they are never stored as repository facts.
Engineering Intelligence uses the hints to narrow repository, Markdown,
Project Intelligence, Knowledge Registry, Engineering Memory, Azure DevOps,
architecture, graph, similarity, and dependency retrieval.

The evidence-synthesis pass receives the refined canonical requirement, the
intent projection embedded in it, and bounded
`EngineeringContext` evidence. The response validator rejects unknown
evidence references. The deterministic Requirement Analysis and Acceptance
Criteria engines remain the validation and availability fallback.

Persisted analyses record the refinement ID/version, provider, model, prompt
versions, Engineering Context ID/version, Knowledge version, repository
revision, analysis version, and timestamp. A provider outage is represented as
deterministic refinement/analysis mode rather than a workflow failure.
