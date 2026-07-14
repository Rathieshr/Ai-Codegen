# Execution Runtime Hardening

## Purpose

Milestone 5.10 adds a repeatable production-hardening boundary around the deterministic AI Execution Runtime. It validates runtime lifecycle behavior without calling an AI provider, cloning a repository, running Git, writing Azure DevOps, or modifying source files.

## Architecture

```text
Runtime Hardening API
        |
RuntimeHardeningHarness
        |-- Workload profiles
        |-- Concurrent execution
        |-- Recovery scenarios
        |-- Runtime API regression
        |-- Performance measurement
        |-- Safety assertions
        |
Persisted Benchmark Report
        |
Quality Gates and Readiness Decision
```

The harness creates isolated Platform Foundation, runtime session, and observability stores for each workload. Runs are explicit and persisted by run ID. Importing or starting the backend does not execute a benchmark.

## Workload profiles

- Small repository metadata: 8 files.
- Large repository metadata: 2,500 files.
- Small prompt: 64 bytes.
- Large prompt: 128 KB.
- Large provider response: 600 artifacts with 128,000 accounted tokens.
- Concurrent execution: 24 sessions across 8 workers.

Inputs are generated metadata. They are bounded and reproducible, so CI does not require repository credentials, provider credentials, or network access.

## Recovery coverage

The recovery benchmark verifies:

- timeout followed by retry and completion;
- duplicate callback acknowledgement without duplicate processing;
- partial-response persistence;
- process restart followed by resume and completion;
- observability attempt history preservation.

## Measurements

Every run captures:

- workload latency, average latency, P95 latency, and maximum latency;
- CPU process time;
- traced Python peak memory;
- response size and artifact count;
- token accounting;
- average and P95 queue time;
- workload and concurrent failure rate.

## Quality gates

| Gate | Default requirement |
| --- | --- |
| Workloads | Every bounded workload completes safely. |
| Concurrent execution | 24/24 sessions complete and P95 queue time is at most 2,000 ms. |
| Recovery | Timeout, retry, restart, duplicate, and partial response scenarios pass. |
| Runtime APIs | All 12 Runtime, Recovery, and Observability routes remain present. |
| Latency | Maximum deterministic workload latency is at most 3,000 ms. |
| Memory | Traced Python peak memory is at most 192 MB. |
| Failure rate | Workload and concurrent failure rates are zero. |
| Safety | Provider, network, repository, Git, and Azure DevOps write counters remain zero. |

`Production Ready` is returned only when every hardening gate passes. Repository-wide regression is reported separately and does not get concealed by the runtime result.

## APIs

- `POST /runtime/hardening/run` executes and persists a bounded benchmark.
- `GET /runtime/hardening/report` returns the latest report.
- `GET /runtime/hardening/runs/{runId}` returns a specific report.

## Operational boundary

The benchmark certifies deterministic single-process runtime behavior with JSON persistence. Live provider latency, network failures outside persisted callback handling, native memory, multi-process contention, and distributed transactional storage require deployment-level load testing.
