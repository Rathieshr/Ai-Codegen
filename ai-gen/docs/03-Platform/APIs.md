# APIs

## Azure DevOps Integration

The public Platform SDK maps Azure DevOps connection and read operations to `/integrations/azure-devops`. Credential values are not accepted or returned; clients provide a `secretReference`. The integration supports project/team/iteration discovery, read-only WIQL, work-item hierarchy and revisions, repository and pull-request retrieval, and build status retrieval. See [Azure DevOps Integration Foundation](../integrations/azure-devops-foundation.md).

HEI APIs are grouped by authority:

- Planning and artifact lifecycle.
- Repository registration, synchronization, snapshots, graph, ranking, and monitoring.
- Context orchestration and diagnostics.
- Execution Package build, storage, and consumers.
- Execution Manifest build, immutable retrieval, summary, and diagnostics.
- Validation, QA, PR Review, and lifecycle.
- Engineering Memory and traceability.
- Platform jobs, events, audit, activity, notifications, health, and policies.

Compatibility Project Intelligence endpoints remain during migration. New integrations should use Context Capsule and Execution Package contracts.

## Execution Manifest

| Method | Route | Contract |
| --- | --- | --- |
| `POST` | `/execution-manifests/build` | Build or reuse an immutable manifest from an Execution Package or package ID. |
| `GET` | `/execution-manifests/{id}` | Retrieve the canonical manifest. |
| `GET` | `/execution-manifests/{id}/summary` | Retrieve a compact manifest summary. |
| `GET` | `/execution-manifests/{id}/diagnostics` | Retrieve lineage, token estimates, immutability, and build diagnostics. |

Execution Prompt generation remains available through the compatibility `DeveloperPrompt` package consumer. That path now builds or reuses an Execution Manifest before invoking Prompt Compiler.

## Prompt Compiler

| Method | Route | Contract |
| --- | --- | --- |
| `POST` | `/prompt-compiler/compile` | Compile an Execution Manifest into ordered model-independent sections. |
| `GET` | `/prompt-compiler/{id}` | Retrieve a persisted `CompiledPrompt`. |

Prompt Compiler does not optimize tokens, select a model, format a final prompt, or call an LLM.

## Token Intelligence

| Method | Route | Contract |
| --- | --- | --- |
| `POST` | `/token-intelligence/optimize` | Apply a supported token budget to a `CompiledPrompt`. |
| `GET` | `/token-intelligence/{id}` | Retrieve an immutable `BudgetedPrompt`. |

Token Intelligence does not select providers, adapt model syntax, format a final prompt, or call an LLM.

## Model Registry

| Method | Route | Contract |
| --- | --- | --- |
| `GET` | `/models` | List supported model family profiles and capabilities. |
| `GET` | `/models/{id}` | Retrieve one model profile by stable ID. |

Model Registry is read-only and does not select, configure, probe, or invoke a provider.

## Prompt Intelligence

| Method | Route | Contract |
| --- | --- | --- |
| `POST` | `/provider-router/route` | Select an eligible model and build or reuse its deterministic optimized prompt. |
| `GET` | `/provider-router/decisions/{id}` | Retrieve an immutable routing decision. |
| `GET` | `/provider-router/decisions/{id}/diagnostics` | Retrieve candidate, rejection, budget, and lineage diagnostics. |
| `GET` | `/prompt-cache/metrics` | Retrieve cache hit rate and generation savings. |
| `GET` | `/prompt-cache/entries/{key}` | Retrieve one active or invalidated cache entry. |
| `POST` | `/prompt-cache/invalidate` | Invalidate matching prompt lineage explicitly. |
| `POST` | `/prompt-intelligence/hardening/run` | Execute the deterministic production-readiness benchmark. |
| `GET` | `/prompt-intelligence/hardening/report` | Retrieve the latest benchmark report. |
| `GET` | `/prompt-intelligence/hardening/runs/{id}` | Retrieve one persisted hardening run. |

Provider Router, Prompt Cache, and Prompt Intelligence Hardening do not invoke providers.

## AI Execution Runtime

| Method | Route | Contract |
| --- | --- | --- |
| `POST` | `/execution-runtime/start` | Start and persist an execution session awaiting a provider response. |
| `POST` | `/execution-runtime/{sessionId}/response` | Register and deterministically interpret one provider response. |
| `POST` | `/execution-runtime/{sessionId}/cancel` | Cancel an active execution session. |
| `GET` | `/execution-runtime/{sessionId}` | Retrieve the complete persisted session and structured outcome. |
| `GET` | `/execution-runtime/{sessionId}/summary` | Retrieve a compact outcome without the raw provider response. |
| `GET` | `/execution-runtime/{sessionId}/diagnostics` | Retrieve lineage, token usage, confidence, warnings, and safety counters. |

### Runtime Recovery

| Method | Route | Purpose |
| --- | --- | --- |
| `POST` | `/execution-runtime/{sessionId}/retry` | Reopen a recoverable session as a new provider attempt. |
| `POST` | `/execution-runtime/{sessionId}/resume` | Continue from the persisted failure or partial-response checkpoint. |
| `POST` | `/execution-runtime/{sessionId}/timeout` | Persist an idempotent provider timeout. |
| `POST` | `/execution-runtime/{sessionId}/failure` | Persist a provider, network, or runtime failure. |

Retry and resume do not invoke providers. An external provider boundary supplies the subsequent callback.

## Runtime Observability

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/runtime/traces` | List runtime traces with optional status, provider, and limit filters. |
| `GET` | `/runtime/traces/{id}` | Retrieve a trace by trace ID, session ID, or correlation ID. |

Runtime trace APIs are read-only projections over correlated platform events. They do not invoke providers or downstream engineering services.

## Runtime Hardening

| Method | Route | Purpose |
| --- | --- | --- |
| `POST` | `/runtime/hardening/run` | Execute and persist the bounded Runtime production-hardening benchmark. |
| `GET` | `/runtime/hardening/report` | Retrieve the latest benchmark, metrics, quality gates, and readiness decision. |
| `GET` | `/runtime/hardening/runs/{runId}` | Retrieve one persisted benchmark run. |

Hardening runs use generated metadata and isolated local stores. They never invoke providers, access the network, modify repositories, run Git, or write Azure DevOps.

The runtime does not invoke an AI provider, read or modify repository files, run Git, write Azure DevOps, create pull requests, or invoke downstream Validation and QA services.

## AI Response Interpreter

| Method | Route | Contract |
| --- | --- | --- |
| `POST` | `/runtime/interpreter/interpret` | Interpret a provider response using its Execution Session, Execution Manifest, and optional Repository Snapshot. |
| `GET` | `/runtime/interpreter/{sessionId}` | Retrieve the latest persisted structured interpretation for the session. |

The interpreter extracts only evidence present in the response. Repository snapshots verify claims when available; they are never scanned or modified by this API.

## Engineering Diff

| Method | Route | Contract |
| --- | --- | --- |
| `POST` | `/engineering-diff` | Compare two Repository Snapshots and a structured Execution Result semantically. |
| `GET` | `/engineering-diff/{id}` | Retrieve an immutable semantic Engineering Diff. |

Engineering Diff does not use Git, inspect repository files, invoke a provider, or modify a repository. It compares supplied APIs, modules, services, dependencies, architecture, tests, security, configuration, database, documentation, parsed symbols, and graph facts.

## Validation Trigger

| Method | Route | Contract |
| --- | --- | --- |
| `POST` | `/validation-trigger/evaluate` | Decide whether Validation Intelligence is required, skipped, or blocked. |
| `GET` | `/validation-trigger/{id}` | Retrieve an immutable Validation Trigger decision. |

## QA Trigger

| Method | Route | Purpose |
| --- | --- | --- |
| `POST` | `/qa-trigger/evaluate` | Determine required QA activities from Engineering Diff, Validation Result, and Execution Manifest. |
| `GET` | `/qa-trigger/{id}` | Retrieve an immutable QA Execution Plan. |

The QA Trigger does not generate tests or invoke QA Intelligence. `QARequested` and `QASkipped` record the planning decision only.

## Engineering Memory Candidates

| Method | Route | Purpose |
| --- | --- | --- |
| `POST` | `/memory-candidates/generate` | Generate evidence-backed Engineering Memory candidates for review. |
| `GET` | `/memory-candidates` | List candidate review records. |
| `GET` | `/memory-candidates/{id}` | Retrieve a candidate. |
| `POST` | `/memory-candidates/{id}/approve` | Approve a candidate without storing or indexing memory. |
| `POST` | `/memory-candidates/{id}/reject` | Reject a pending candidate. |

Candidate generation and approval never call `EngineeringMemoryEngine` or `MemoryWriter`. A separate memory-capture workflow must store approved candidates.

## Pull Request Candidates

| Method | Route | Purpose |
| --- | --- | --- |
| `POST` | `/pr-candidates/generate` | Generate an evidence-backed Pull Request candidate. |
| `GET` | `/pr-candidates` | List persisted PR candidates. |
| `GET` | `/pr-candidates/{id}` | Retrieve one PR candidate. |

These routes do not create Git or Azure DevOps pull requests. Actual PR creation remains outside this module.

The trigger evaluates Engineering Diff, Execution Result, Execution Manifest, manual override, and policy precedence. It emits lifecycle events but does not invoke Validation Intelligence.

## Engineering Command Center V1

| Method | Route | Access | Purpose |
| --- | --- | --- | --- |
| `GET` | `/command-center/health` | Viewer+ | Cached platform, service, job, queue, event, SDK, latency, storage, database, memory, version, and notification health. |

## HEI Single Hub

| Method | Route | Access | Purpose |
|---|---|---|---|
| `POST` | `/requirements/intake` | Contributor+ | Build a draft Planning Pack from a requirement through the shared context pipeline. Does not write to Azure DevOps. |
| `GET` | `/requirements` | Viewer+ | List submitted requirements and Planning Pack references. |
| `GET` | `/requirements/{requirementId}` | Viewer+ | Read one requirement intake result. |
| `POST` | `/workspace/diagnostics` | Host application | Record bounded hub startup, navigation, theme, and error diagnostics with a correlation ID. |
| `GET` | `/command-center/performance` | Viewer+ | Snapshot latency, probe latency, refresh mode, and cache state. |
| `GET` | `/command-center/diagnostics` | Admin | Detailed probe warnings and operational record counts. Accepts `X-HEI-Role: admin`. |
| `GET` | `/activity` | Viewer+ | Searchable, filtered, paginated lifecycle activity. |
| `GET` | `/activity/{id}` | Viewer+ | Activity details with sensitive fields redacted. |
| `GET` | `/activity/correlation/{id}` | Viewer+ | Chronological correlation trace. |
| `POST` | `/activity/{id}/replay` | Viewer+ | Reconstruct the historical view only. It has no side effects. |

`force=true` bypasses the short operational snapshot cache. Clients should use it only for explicit user refresh.
