# Service Contracts

## Contract rules

- Contracts are versioned and transport-neutral.
- IDs, source versions, correlation IDs, confidence, warnings, and blockers are preserved.
- A consumer receives one canonical upstream artifact, not a collection of raw source services.
- Runtime evidence such as diffs, changed files, tests, and builds may accompany validation without becoming context retrieval.
- Compatibility aliases must project the canonical result and must not rebuild it.

## Canonical contracts

| Producer | Contract | Consumers |
| --- | --- | --- |
| Engineering Intelligence | Versioned `EngineeringContext` and bounded workflow projections | Requirement, Planning, Execution, Validation, Approvals, Agents |
| Project Intelligence compatibility adapter | Project background + intent-selected Knowledge Registry evidence + approved artifacts | Engineering Intelligence only |
| Planning Recommendation | Reviewed Planning Context + canonical EngineeringContext + Reasoning result | Versioned, explainable recommendation; human review; Planning Proposal |
| Planning Proposal | Approved Planning Recommendation + canonical EngineeringContext + preserved Acceptance Criteria lineage | Versioned editable hierarchy, validation, planning diff, and zero-write Azure DevOps preview |
| Engineering Review | Version-pinned Planning Proposal + configurable approval chain | Auditable review decision and Azure DevOps synchronization authorization |
| Context Intelligence | Context Capsule | Execution Package Builder |
| Execution Intelligence | Execution Package | Execution Manifest Builder, Validation, QA, Memory, Agents, VS Code |
| Execution Manifest Builder | Execution Manifest | Prompt Compiler |
| Prompt Compiler | CompiledPrompt | Token Intelligence |
| Token Intelligence | BudgetedPrompt | Model Adapter |
| Model Registry | ModelProfile | Future model selection and adapters |
| Model Adapter | BudgetedPrompt + ModelProfile | ExecutionPrompt |
| Prompt Optimizer | ExecutionPrompt + execution mode | OptimizedExecutionPrompt |
| Prompt Diagnostics | OptimizedExecutionPrompt + Execution Manifest + optional Execution Package | PromptDiagnostics |
| Provider Router | Execution Manifest + routing signals + available models | ProviderRoutingResult with OptimizedExecutionPrompt |
| Prompt Cache | Execution lineage + model + execution mode + routing target | Cached ProviderRoutingResult or cache miss |
| Prompt Intelligence Hardening | Deterministic repository scenarios + production components | Persisted readiness and benchmark report |
| Prompt Intelligence | Execution Prompt | Coding assistant |
| AI Provider | Provider response | AI Execution Runtime |
| AI Response Interpreter | Execution Session + provider response + Execution Manifest + optional Repository Snapshot | Structured Execution Result and evidence-backed Engineering Artifacts |
| Engineering Diff Engine | Repository Snapshot Before + Repository Snapshot After + Structured Execution Result | Immutable semantic Engineering Diff and dependency graph changes |
| Validation Trigger Engine | Engineering Diff + Structured Execution Result + Execution Manifest + policy and optional override | Immutable ValidationTriggerDecision and request, skip, or block event |
| AI Execution Runtime | Execution Session, Execution Result, Execution Artifacts, Engineering Diff, pending downstream intents | Future Validation, QA, Memory approval, PR review, Portal |
| Validation Intelligence | Validation Report | QA, PR Review, lifecycle, memory |
| QA Trigger Engine | QA Execution Plan | QA Intelligence, lifecycle, diagnostics |
| QA Intelligence | QA Report | Release recommendation, lifecycle, memory |
| Memory Candidate Generator | Pending or rejected memory candidates | Human approval, future Engineering Memory capture |
| Pull Request Candidate Generator | Draft PR candidate | Human review, future Git or Azure DevOps PR workflow |
| Engineering Memory | Memory Context | Planning, Execution, QA as supporting evidence |

API details are indexed in [APIs](../03-Platform/APIs.md).

Project Intelligence is not a workflow input by itself. Its read-only adapter
feeds the canonical Engineering Context. Project Profile remains background,
Knowledge Registry facts are relevance-selected, and current repository facts
always come from Repository Intelligence.
## Reasoning AI

`ReasoningEngine` is the canonical provider-neutral service for engineering
judgment. Its input is `EngineeringContext`; its output contains recommendation,
reasoning, alternatives, evidence references, risks, trade-offs, impact,
confidence, prompt version, and telemetry.

Public operations:

- `analyze(workflowType, engineeringContext)`
- `reason(workflowType, engineeringContext)`
- `recommend(workflowType, engineeringContext)`
- `refine(workflowType, engineeringContext)`
- `summarize(workflowType, engineeringContext)`
- `explain(workflowType, engineeringContext)`

Reasoning providers are replaceable implementations of `IReasoningProvider`.
Workflows must not invoke provider clients directly. See
`Reasoning AI Layer.md` for the complete boundary and fallback behavior.
