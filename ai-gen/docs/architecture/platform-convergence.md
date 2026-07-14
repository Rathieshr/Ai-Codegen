# Platform Convergence and Consumer Migration

## Current and target architecture

Historically, HEI consumers accepted combinations of planning artifacts, profiles, repository context, Knowledge Registry data, Engineering Memory, and validation options. This produced multiple context assembly paths.

The converged context pipeline is:

`Planning Intelligence -> Context Orchestrator -> Unified Context Capsule -> Execution Package v2 -> Consumers`

Prompt generation adds one immutable projection after the package:

`Execution Package v2 -> Execution Manifest -> Prompt Compiler -> CompiledPrompt -> Token Intelligence -> BudgetedPrompt -> Model Adapter -> Execution Prompt`

Context Orchestrator is the only context authority. Execution Package v2 is the only downstream engineering execution contract. Runtime evidence such as a git diff, changed files, test results, and build results is not context retrieval and may accompany a package during validation.

## Consumer migration inventory

| Consumer | Previous sources | Target source | Status | Risk | Dependencies |
|---|---|---|---|---|---|
| Execution Prompt (`DeveloperPrompt` compatibility identifier) | Legacy story/profile/context endpoints | Execution Manifest derived from Execution Package | Migrated | Low | Prompt Intelligence |
| Implementation Validation | Package plus optional DNA fragments | Execution Package plus runtime evidence | Migrated | Medium | Diff and validation rules |
| QA Intelligence | Story, acceptance, repository, knowledge | Execution Package | Migrated adapter | Medium | Existing test templates |
| Engineering Memory Capture | Independent memory payloads | Execution Package, Validation Result, QA Result, snapshot | Migrated adapter | Medium | Approval and memory writer |
| Agent Runtime | Work item, memory, repository fragments | Execution Package, AgentContext, ExecutionMode | Migrated adapter | Medium | Agent policy/workflow compatibility |
| VS Code Execution Workspace | Profile plus multiple Project Intelligence calls | Execution Package build and consume APIs | Migrated | Medium | Unified Context Capsule availability |
| Azure DevOps automation | Work item and pipeline-specific payloads | Execution Package | Planned consumer | High | Future automation milestone |
| Portal and SDK | Partial project APIs | Execution Package | Future | Medium | Public contract versioning |

## Responsibilities and consumer contract

Consumers may read planning, repository, implementation, validation, QA, memory, warnings, confidence, and versions only from Execution Package. They must not instantiate or call Repository Intelligence, Engineering Memory retrieval, Knowledge Registry, file ranking, repository graphs, or capsule builders.

The shared consumer request contains `ExecutionPackage`, `AgentContext`, `ExecutionMode`, optional runtime evidence, and a correlation ID. Every response exposes package version, capsule version, repository snapshot, knowledge version, memory version, confidence, warnings, correlation ID, activity ID, and duration.

## Migration strategy

Compatibility entry points remain available during incremental migration. Package-first adapters project legacy shapes where necessary; they do not rebuild context. New integrations use `POST /execution-packages/{id}/consume/{consumer}`. Supported consumers are DeveloperPrompt, Validation, QA, MemoryCapture, AgentRuntime, and VSCode. DeveloperPrompt is the sole compatibility consumer that creates or reuses an Execution Manifest, compiles a `CompiledPrompt`, applies Token Intelligence, and only then invokes downstream model adaptation.

VS Code now rebuilds a package with one `POST /execution-packages/build` call using its existing Unified Context Capsule. Execution Prompt compilation uses the package consumer endpoint currently named `DeveloperPrompt`; the endpoint internally follows Package -> Manifest -> Prompt Compiler. No profile or partial-context calls are added.

## Deprecated APIs

The following partial-context endpoints remain backward compatible but are marked deprecated in OpenAPI:

- `/project-intelligence/generate-qa-test-cases`
- `/project-intelligence/build-execution-context`
- `/project-intelligence/build-dev-prompt`
- `/project-intelligence/build-execution-plan`
- `/project-intelligence/build-qa-prompt`
- `/project-intelligence/validate-implementation`

Planning and repository authority APIs remain supported because they feed Context Orchestrator rather than act as downstream execution consumers.

## Events, diagnostics, and performance

Package consumption publishes `ConsumerMigrationStarted`, `ConsumerMigrationCompleted`, and `ExecutionPackageConsumed`; failures publish `ExecutionPackageValidationFailed`. Activity and audit records contain consumer, package ID, duration, warnings, and correlation ID.

Immutable package and snapshot identities allow consumers to reuse stored packages without repeating repository, graph, or memory lookup. Consumer duration is measured independently from context and package build duration, enabling end-to-end performance analysis.

## Milestone 3.5 hardening implementation

The executable regression architecture is intentionally deterministic:

`Scenario -> Context Orchestrator -> Unified Context Capsule -> Execution Package -> package-only consumers`

`backend/platform_hardening` supplies instrumented source adapters, failure injection, persistent JSON run/trace storage, quality gates, and regression APIs. It calls the production orchestrator, package builder, and consumer gateway rather than duplicating their logic. Repository modes and source freshness are adapter inputs; no test fixture may synthesize code evidence in `KnowledgeSnapshot` or `Unavailable` mode.

This differs from the intended production design in two infrastructure details: the regression store is local JSON rather than a multi-writer database, and repository inputs are deterministic fixtures rather than live repository scans. These choices keep CI provider-free and repeatable. They do not change the package boundary or consumer architecture. See [Platform Hardening](../testing/platform-hardening.md) for scenarios, gates, baselines, and limitations.

## Future integration points

Azure DevOps automation, Portal, and SDK integrations should accept package IDs or complete versioned packages. They must use the same consumer gateway and may not add new context retrieval paths.
