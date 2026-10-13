# HEI Platform Hardening

## Purpose

Milestone 3.5 verifies that HEI's major engineering workflows use one traceable context pipeline and remain safe across repository availability, token pressure, weak inputs, and stage failures. The suite is deterministic and backend-only so it can run in CI without Azure DevOps, a repository clone, or an AI provider.

## Test architecture

The regression harness executes the production context, package, prompt, validation, QA, and memory-consumer components through instrumented source adapters:

`Scenario -> Planning Lineage -> Context Orchestrator -> Unified Context Capsule -> Execution Package v2 -> Execution Manifest -> CompiledPrompt -> BudgetedPrompt -> Execution Prompt / Validation / QA -> Memory Capture Draft`

The harness is implemented in `backend/platform_hardening`. It uses:

- `ContextOrchestrator` as the only context retrieval and selection authority.
- `ExecutionPackageBuilder` as a deterministic capsule-only package builder.
- `ExecutionPackageConsumerService` as the package-only gateway for Execution Manifest, Prompt Compiler, Token Intelligence (`DeveloperPrompt` compatibility identifier), Validation, QA, and Memory Capture.
- `HardeningRunStore` for persistent JSON run and trace records.
- `PlatformFoundation` for activity, audit, and event evidence.

Every run receives a unique run ID and correlation ID. The trace records stage start, completion or failure, duration, capsule/package lineage, repository snapshot version, warnings, and blockers. The harness never calls an LLM.

## Test scenarios

The required scenario set covers unrelated business domains so generic or leaked context is visible:

| Scenario | Primary context | Key isolation check |
| --- | --- | --- |
| Device Health Dashboard | Asset Health, Telemetry, Operational Awareness, Alert Management | Complete dashboard flow and repository evidence |
| Centralized Alarm Notification Center | Alert, Notification, Event Management | Alarm acceptance mapping and QA generation |
| User Administration | User Management, Authentication, Authorization, Audit | No Telemetry, Fault Monitoring, or Firmware context |
| Firmware Rollout Management | Firmware, Deployment, Compliance, Device Management | Firmware-specific planning and failure recovery |
| Energy Consumption Analytics | Analytics, Reporting, Telemetry, Trend Analysis | Analytics context remains distinct from administration |

The suite also runs the same five scenarios twice and compares scenario status, readiness, and quality assertions. Run IDs, correlation IDs, timestamps, and timings are intentionally not compared.

## Quality gates

A scenario passes only when all applicable gates pass:

- One context orchestration request per lifecycle.
- Each enabled source is retrieved no more than once.
- Capsule and package versions remain aligned.
- Correlation ID survives prompt, validation, QA, memory, and trace stages.
- Rejected or blocked context is absent from active implementation output.
- `KnowledgeSnapshot` and `Unavailable` modes produce no file or API evidence.
- `CodeIndexed` mode preserves direct file evidence.
- BudgetedPrompt and the downstream Execution Prompt stay within their respective deterministic and provider transport budgets.
- Acceptance criteria are complete, non-duplicate, independently verifiable statements.
- A failed stage records a sanitized failure event and stops downstream work.

Acceptance criteria are rejected for fragments, leading conjunctions, duplicates, or multi-behavior conjunctions. Rejected criteria block execution readiness. Criteria needing refinement cap readiness at `Needs Review`.

## Readiness rules

Execution readiness is deterministic and weighted across planning completeness, repository confidence, Engineering Memory confidence, Knowledge Registry completeness, acceptance completeness, validation completeness, and repository freshness.

- `Ready`: score is at least 75, acceptance quality is approved, and no hard blocker exists.
- `Needs Review`: the package is usable but evidence, freshness, or acceptance quality needs review.
- `Blocked`: required story/acceptance context is missing, acceptance quality is rejected, or a hard blocker exists.

Package confidence is capped by the readiness score. Missing or stale repository evidence therefore cannot produce higher confidence than a fully supported package.

## Repository modes

| Mode | Permitted evidence | Expected behavior |
| --- | --- | --- |
| `CodeIndexed` | Files, APIs, modules, dependencies, graph references | Direct file evidence is allowed when supplied by the capsule |
| `KnowledgeSnapshot` | Modules, flows, standards, approved project knowledge | File paths, APIs, symbols, and tests are never invented |
| `Unavailable` | Planning, Knowledge Registry, and approved memory only | Repository evidence is empty and readiness/confidence is reduced |

A stale available source sets capsule freshness to `Stale`, adds a refresh warning, and lowers readiness. Repository absence remains recoverable when sufficient planning and knowledge context exists.

## Token-budget tests

The context hardening suite exercises 1,200, 4,000, 8,000, and 16,000-token windows. Context Intelligence selects whole ranked candidates before building the package. Prompt Compiler then preserves all manifest content in ordered sections. Token Intelligence supports 1,024, 2,048, 4,096, 8,192, 16,000, 32,000, and 128,000-token profiles and removes only complete lower-value JSON values after reserving output tokens.

Acceptance criteria, repository evidence, and validation guidance are never removed. If those protected values exceed the selected input budget, Token Intelligence returns `Blocked` and retains them intact. The downstream provider adapter remains responsible for its exact transport limit, including the legacy 1,200-token Phi profile.

The 1,200-token check must complete without parse errors, prompt overflow, or provider fallback. Because the hardening flow is deterministic, provider response parsing is outside this test boundary.

## Failure recovery

Failure injection is supported at Planning, Context Orchestration, Context Capsule, Execution Package, Execution Manifest, Validation, QA, and Memory Capture Draft. The harness stage retains the compatibility name `DeveloperPrompt` until the API migration is versioned.

For every injected failure:

- The run becomes `Blocked`.
- No downstream stage executes.
- A trace event records stage, bounded error type, retry guidance, and correlation ID.
- Platform activity and audit evidence are retained.
- Raw traceback content is not returned.
- Previously completed artifacts remain available in the run record.

The harness does not automatically retry injected failures. Production retry policy remains the responsibility of the caller or agent workflow.

## Performance baselines

The regression summary records observed average and maximum duration per stage and compares maximum duration with these deterministic targets:

| Stage | Target |
| --- | ---: |
| Context Orchestration | 2,000 ms |
| Context Capsule | 1,000 ms |
| Execution Package | 2,000 ms |
| Execution Manifest | 2,000 ms |
| Validation | 5,000 ms |
| QA | 5,000 ms |

The local Milestone 3.5 baseline is single-process and JSON-backed. It measures application work only; it is not a production capacity or network latency benchmark. Query `GET /platform/regression/summary` after a run for the current measured average, maximum, sample count, and target result.

Observed locally on 2026-07-13 for five `KnowledgeSnapshot` scenarios at a 1,200-token budget:

| Stage | Average | Maximum |
| --- | ---: | ---: |
| Context Orchestration | 2.20 ms | 2.67 ms |
| Context Capsule | 0.20 ms | 0.29 ms |
| Execution Package | 0.41 ms | 0.46 ms |
| Execution Manifest | 3.02 ms | 4.01 ms |
| Validation | 3.12 ms | 4.70 ms |
| QA | 3.10 ms | 3.86 ms |

## APIs

- `POST /platform/regression/run` runs one named scenario or all scenarios.
- `GET /platform/runs/{correlation_id}/trace` returns lifecycle trace evidence.
- `GET /platform/regression/summary` returns quality and performance summary.
- `GET /platform/regression/runs` lists persisted runs.
- `GET /platform/regression/runs/{run_id}` returns one complete run.

`POST /platform/regression/run` accepts `scenarioId`, `repositoryMode`, `repositoryFreshness`, `tokenBudget`, and optional `failureStage`.

## CI command

Run the milestone regression suite plus its existing context, package, convergence, and memory contract suites:

```sh
bin/test-hei-e2e
```

Run the complete repository test suite separately:

```sh
python3 -m unittest discover -s tests -v
```

The separation is intentional: the milestone command gives a fast, stable hardening signal, while full discovery continues to expose legacy regressions outside the converged pipeline.

## Manual milestone check

1. Run all five scenarios in `KnowledgeSnapshot` mode.
2. Confirm User Administration contains no Telemetry, Fault Monitoring, or Firmware capability.
3. Confirm every Knowledge Snapshot package has empty `relevantFiles` and `relevantAPIs`.
4. Run Device Health with a 1,200-token budget and confirm success with no parse or overflow blocker.
5. Open one correlation trace and verify the same capsule ID reaches the package and the same package ID reaches Execution Manifest, Validation, QA, and Memory Capture.
6. Run the five-scenario suite twice and compare status, readiness, and assertions.

## Known limitations

- Scenario source adapters are deterministic fixtures; they do not scan a live Azure DevOps or GitHub repository.
- Persistence is local JSON and is not designed for concurrent distributed writers.
- Performance baselines exclude network, repository clone, Azure DevOps, and LLM latency.
- Memory Capture produces a Draft. Approval and indexing remain separate governed actions.
- Runtime validation uses supplied changed-file/test evidence and does not execute a build.
- The regression harness proves package-only consumer boundaries, but legacy compatibility endpoints still exist during migration.
- Full test discovery on 2026-07-13 ran 891 tests and reported 10 failures plus 1 error in legacy Project Intelligence, QA, planning/validation alignment, and execution-package normalization tests. These remain visible and are not treated as passing by the hardening command.
