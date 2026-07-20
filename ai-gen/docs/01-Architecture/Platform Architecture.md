# Platform Architecture

## Azure DevOps Boundary

Azure DevOps is integrated through `backend/integrations/azure_devops`, then surfaced through the HEI Platform SDK. Intelligence services must consume the SDK contracts instead of importing Azure DevOps clients. The boundary is read-only and normalizes provider DTOs before they cross into HEI. Milestone 6.2 centralizes incremental synchronization through Platform Jobs, persists cursors and stable mappings, and reconciles missed service-hook events without making Azure DevOps writes. See [Azure DevOps Integration Foundation](../integrations/azure-devops-foundation.md) and [Azure DevOps Synchronization](../integrations/azure-devops-synchronization.md).

```text
HEI Engineering Platform

Experience Layer
VS Code | Azure DevOps | Portal | CLI | Teams | MCP | Future IDEs
                         |
HEI Platform SDK | Business Service Contracts | Transport Layer
                         |
Backend APIs (transport implementation)
                         |
Engineering Intelligence
Planning | Repository | Context | Execution | Prompt | AI Execution Runtime | Validation | QA | Memory
                         |
Agent Runtime
Planning | Repository | Execution | Validation | QA | Memory | Azure DevOps
                         |
Platform Foundation
Jobs | Events | Audit | Notifications | Activity | Health | Policies
                         |
Enterprise Systems
Azure DevOps | Git | Repositories | Knowledge Registry | AI Providers
```

## Data flow

`Enterprise evidence -> Engineering Intelligence -> Versioned artifacts -> Experience surfaces`

The Agent Runtime may trigger or sequence intelligence operations, but it does not become a knowledge source. Experience surfaces render and operate the same contracts rather than implementing their own planning or context logic.

The [HEI Platform SDK](../architecture/hei-platform-sdk.md) is the public client integration boundary. Experience surfaces consume business service contracts through the SDK; backend REST routes are transport implementation details rather than client contracts.

## Canonical execution flow

`Approved artifact -> Context Intelligence -> Context Capsule -> Execution Package -> Implementation Plan -> Execution Manifest -> Prompt Intelligence -> AI Provider -> AI Execution Runtime -> Response Interpreter -> Engineering Diff -> Validation Trigger -> Validation -> QA Trigger -> QA -> Memory Candidate / PR Candidate -> Human Review -> Engineering Memory / PR Workflow`

The AI Execution Runtime interprets and records provider outcomes. It publishes pending downstream intents but does not invoke providers, modify repositories, or invoke Validation and QA in Milestone 5.1. See [AI Execution Runtime](../architecture/ai-execution-runtime.md).

The standalone Engineering Diff Engine compares two supplied Repository Snapshots with a structured Execution Result. It understands semantic changes without reading a working tree or running Git. See [Engineering Diff Engine](../architecture/engineering-diff-engine.md).

The Validation Trigger Engine applies governance, manual override, impact, engineering-category, and skip rules before Validation Intelligence is allowed to run. See [Validation Trigger Engine](../architecture/validation-trigger-engine.md).

The QA Trigger Engine translates Engineering Diff and Validation Result evidence into a deterministic QA Execution Plan before QA Intelligence runs. See [QA Trigger Engine](../architecture/qa-trigger-engine.md).

The Memory Candidate Generator proposes reusable knowledge only after Execution, Validation, and QA outcomes exist. Approval is required, and storage remains a separate Engineering Memory responsibility. See [Memory Candidate Generator](../architecture/memory-candidate-generator.md).

The Pull Request Candidate Generator creates a deterministic engineering summary without creating a branch or pull request. Existing PR Review remains a separate consumer for real pull requests. See [Pull Request Candidate Generator](../architecture/pr-candidate-generator.md).

## Command Center Production Read Model

Command Center V1 uses `backend/command_center_hardening` as a bounded, read-only operational projection. It probes Platform Health, Jobs, Events, Notifications, Activity, Audit, Agent Runtime, Repository Intelligence, Context Intelligence, Runtime, Workspace, and Azure DevOps independently. A failed probe degrades its service row without failing the workspace.

```text
Platform and Intelligence Services
             |
Isolated bounded probes
             |
10-second operational snapshot cache
             |
Health / Performance / Admin Diagnostics APIs
             |
Visibility-aware Command Center refresh

## Azure DevOps Single Hub Host

Azure DevOps hosts one HEI project hub at `dist/hei/index.html`. The hub starts the shared HEI React application and routes internally without reloading the Azure DevOps page. Existing work-item contributions remain entry points and deep-link to the same application rather than implementing another planning or execution UI.

Host-specific concerns are isolated behind `HEIHostAdapter`. `AzureDevOpsHostAdapter` owns Extension SDK initialization, identity, project/team context, theme, route parameters, and access-token retrieval. `StandaloneHostAdapter` implements the same contract for the portal. Shared views, state, SDK clients, and validation logic remain host-independent.

New Requirement uses Requirement Intelligence to ingest, parse, analyze, detect the repository, and produce an approved Requirement Summary. The Planning Agent consumes only that summary, then uses the existing Context Orchestrator to select Planning, Repository, Knowledge Registry, and Engineering Memory evidence before generating an estimated, reviewable draft Planning Pack. Human approval is mandatory before the Azure DevOps automation layer can prepare or apply writes. See [Requirement Planning Integration](./Requirement%20Planning%20Integration.md).
```

The projection never executes jobs or changes engineering artifacts. Viewer health responses contain only safe summaries. Detailed warnings are restricted to admins. Storage responses expose aggregate counts and size, never filesystem paths.
