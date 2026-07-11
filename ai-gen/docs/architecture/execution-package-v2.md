# Execution Package v2

## Pipeline

Execution Package v2 is the canonical, deterministic engineering execution artifact:

`Planning + Repository Intelligence + Knowledge + Engineering Memory -> Context Orchestrator -> Unified Context Capsule -> Execution Package Builder -> Execution Package`

The canonical `ExecutionPackageBuilder` accepts exactly two inputs: a Unified Context Capsule and an `ExecutionRequest`. It performs no source retrieval and makes no LLM calls. Context selection, freshness, rejection, token budgeting, and provenance remain the Context Orchestrator's responsibility.

## Context Capsule relationship

The builder reads normalized candidates and diagnostics from the capsule. Planning, repository, memory, knowledge, standards, and validation sections are projections of capsule content. It never queries their backing services. The compatibility adapter in the existing `build_execution_package_v2` function translates the established Project Intelligence inputs into this strict contract, retaining legacy aliases used by Developer Prompt and VS Code.

An `ExecutionRequest` supplies execution-local intent only: purpose, story/task identifiers, repository snapshot version, branch, target platform, execution mode (`Implement`, `Refactor`, `BugFix`, `Spike`, or `POC`), selected and changed files, local workspace context, and developer preferences.

## Package sections and versioning

Packages contain metadata, planning context, repository context, engineering memory, knowledge, deterministic implementation guidance, validation guidance, QA guidance, prompt token estimates, and bounded diagnostics. Metadata independently records capsule, repository snapshot, knowledge, planning, and engineering-memory versions. A stable package ID is derived from capsule identity and execution request identity; `generatedAt` records the build occurrence.

## Execution readiness

Readiness is a weighted deterministic score using planning completeness, repository confidence, memory confidence, knowledge completeness, acceptance completeness, validation completeness, and repository freshness. Results are:

- `Ready`: score is at least 75 and no blocked modules remain.
- `Needs Review`: usable context exists but confidence, completeness, freshness, or boundaries require review.
- `Blocked`: story or acceptance context required for safe implementation is missing.

Diagnostics expose every signal, warnings, missing context, excluded and rejected context, repository mode, and source list.

## Repository modes

- `CodeIndexed` permits capsule-provided files, APIs, modules, dependencies, and graph references.
- `KnowledgeSnapshot` permits modules, flows, dependencies, standards, and project knowledge but removes file and API evidence.
- `Unavailable` returns no repository evidence and lowers readiness without discarding permitted planning context.

The builder never synthesizes repository paths, symbols, APIs, or tests.

## APIs

`POST /execution-packages/build` accepts `{ contextCapsule, executionRequest, correlationId }`. Stored packages are available from `GET /execution-packages/{id}`, with compact views at `/summary` and `/diagnostics`. Builds publish `ExecutionPackageRequested`, `ExecutionPackageBuilt`, `ExecutionPackageReady`, or `ExecutionPackageFailed`, and record generation activity with duration, confidence, snapshot, capsule version, and warnings.

## Future consumers

Developer Prompt, Validation, QA, PR Review, Agent Runtime, VS Code, and Azure DevOps automation can migrate incrementally to the canonical sections. Legacy aliases remain available during that migration; no current editor workflow needs a coordinated cutover.
