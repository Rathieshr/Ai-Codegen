# AI Execution Runtime Foundation

## Purpose

The AI Execution Runtime owns the lifecycle after an AI provider returns a response. It records the execution session, interprets provider-neutral response shapes, extracts engineering artifacts, and compares artifact metadata with a caller-supplied repository baseline.

It does not execute prompts, call providers, read or modify a repository, run Git commands, write to Azure DevOps, create pull requests, or invoke Validation and QA services.

## Pipeline

```text
Execution Prompt
        |
AI Provider (outside this module)
        |
Execution Runtime
        |
Response Interpreter
        |
Execution Artifacts
        |
Milestone 5.1 Metadata Comparison
        |
Runtime comparison summary
        |
Pending Validation / QA / Memory / PR intents
        |
Platform Events, Activity, and Diagnostics
```

## Module boundaries

The Python-safe package is `backend/execution_runtime` and contains:

- `domain`: session, result, artifact, diff, status, and artifact-type contracts.
- `application`: `IExecutionRuntime`, persisted session repository, and lifecycle orchestration.
- `interpreter`: deterministic provider-response normalization and artifact extraction.
- `comparison`: metadata-only comparison against `runtimeContext.repositoryBaseline`.
- `validation`: downstream intent creation only; no Validation or QA invocation.
- `memory`: unapproved and unindexed Engineering Memory candidate projection.
- `events`: Platform Foundation event and activity publication.
- `diagnostics`: lifecycle lineage and explicit safety counters.
- `observability`: persistent read-only projections over correlated runtime and downstream events.
- `api`: runtime session HTTP contract.

## Lifecycle

```text
AwaitingResponse -> Interpreting -> Completed
       |                 |
       |                 +-----------> Failed ----+
       +-> PartialResponse -----------------------+--> Resume / Retry -> AwaitingResponse
       +-> TimedOut -------------------------------+

AwaitingResponse -> Cancelled ---------------------+
```

`Completed` is final. `Failed`, `TimedOut`, `PartialResponse`, and `Cancelled` are persisted recovery checkpoints. They cannot accept a new response until retry or resume reopens the session. Duplicate callbacks are acknowledged idempotently even after completion.

## Response interpretation

The interpreter accepts:

- OpenAI-compatible `choices[0].message.content` envelopes.
- Provider envelopes with `message.content`, `response`, `content`, `text`, or `output`.
- Structured objects containing `artifacts`, `files`, or `changes`.
- JSON strings, Markdown, fenced code, and plain text.

Interpretation is deterministic and contains no LLM repair step. Unstructured content is retained as evidence and lowers confidence rather than being discarded.

Milestone 5.2 adds the standalone, persisted [AI Response Interpreter](ai-response-interpreter.md). The runtime retains primary artifacts for Engineering Diff compatibility while the standalone contract exposes richer engineering artifact categories.

Milestone 5.3 adds the standalone [Engineering Diff Engine](engineering-diff-engine.md). It consumes complete before and after Repository Snapshots plus a structured Execution Result. This richer semantic comparison does not replace the Milestone 5.1 session compatibility summary yet.

Milestone 5.4 adds the deterministic [Validation Trigger Engine](validation-trigger-engine.md). It evaluates Engineering Diff, Execution Result, Execution Manifest, governance policy, and optional manual override. It publishes a request, skip, or block decision without invoking Validation Intelligence.

Milestone 5.5 adds the deterministic [QA Trigger Engine](qa-trigger-engine.md). It evaluates Engineering Diff, Validation Result, and Execution Manifest, persists a QA Execution Plan, and publishes `QARequested` or `QASkipped` without generating tests or invoking QA Intelligence.

Milestone 5.6 adds the deterministic [Memory Candidate Generator](memory-candidate-generator.md). It proposes reviewable Engineering Memory candidates from Execution, Validation, QA, and Engineering Diff outcomes. Candidate approval remains separate from Engineering Memory storage and indexing.

Milestone 5.7 adds the deterministic [Pull Request Candidate Generator](pr-candidate-generator.md). It projects Engineering Diff, Validation, QA, and Execution Manifest evidence into a reviewable PR summary without running Git, writing Azure DevOps, creating a pull request, or invoking PR Review.

Milestone 5.8 adds [Runtime Observability](runtime-observability.md). It projects correlated platform events into a persistent execution timeline with duration, provider, model, token, confidence, warning, and failure metrics without changing execution state.

Milestone 5.9 adds [Runtime Recovery](runtime-recovery.md). It persists retry, resume, timeout, provider/network failure, partial-response, duplicate-response, and idempotency state across process restarts without invoking providers.

Milestone 5.10 adds [Runtime Hardening](runtime-hardening.md). It executes bounded repository, prompt, response, concurrency, recovery, performance, memory, token, safety, and API-regression workloads and persists a quality-gated benchmark report. It does not invoke providers or use live repositories.

## Repository safety

Repository comparison consumes only metadata supplied at session start. It never opens paths from the artifact response. Diagnostics always record:

- `repositoryModified: false`
- `gitOperations: 0`
- `azureDevOpsWrites: 0`
- `pullRequestsCreated: 0`
- `providerInvoked: false`
- `llmCalls: 0`
- `downstreamServicesInvoked: 0`

## Downstream boundary

On successful interpretation, the runtime creates pending intents for Implementation Validation, QA Analysis, Engineering Memory Candidate review, and PR Candidate review. Each intent has `invoked: false`. Memory remains `Draft` and unindexed; a PR Candidate remains `Draft` with `created: false`.

## Events

- `ExecutionStarted`
- `ExecutionResponseReceived`
- `ExecutionInterpreted`
- `ExecutionCompleted`
- `ExecutionFailed`
- `ExecutionCancelled`
- `ValidationRequested`
- `ValidationSkipped`
- `ValidationBlocked`
- `QARequested`
- `QASkipped`
- `MemoryCandidateCreated`
- `MemoryCandidateRejected`
- `PRCandidateCreated`

Every event preserves the session correlation ID and session ID.
