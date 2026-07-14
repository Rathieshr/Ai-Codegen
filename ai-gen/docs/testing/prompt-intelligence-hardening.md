# Prompt Intelligence Hardening

## Purpose

Milestone 4.10 validates the deterministic Prompt Intelligence platform from immutable Execution Manifest through compilation, token allocation, model adaptation, optimization, diagnostics, routing, and caching.

```text
Execution Package
  -> Execution Manifest
  -> Prompt Cache lookup
  -> Prompt Compiler
  -> Token Intelligence
  -> Model Adapter
  -> Prompt Optimizer
  -> Provider Router decision
  -> Prompt Cache write
  -> Prompt Diagnostics
```

The hardening harness calls no provider and performs no network request. Production readiness in this milestone means the deterministic prompt platform is safe, traceable, repeatable, bounded, and operationally measurable. Live provider availability and transport behavior remain separate runtime concerns.

## Test Architecture

`backend/prompt_intelligence_hardening` runs production components against deterministic repository fixtures and persists a complete benchmark report. It validates:

- small and large `CodeIndexed` repositories
- `KnowledgeSnapshot` truthfulness
- `Unavailable` repository behavior
- every registered deterministic Model Adapter
- every supported Token Intelligence budget
- Prompt Cache reuse and savings
- Prompt Diagnostics lineage
- Provider Router decisions
- deterministic regression fingerprints
- local stage-performance targets

The large-repository fixture supplies 600 directly evidenced repository files. Snapshot and unavailable fixtures supply no file paths, which makes invented evidence immediately detectable.

## Quality Gates

Prompt Intelligence is `Production Ready` only when all gates pass:

1. Repository modes preserve their evidence boundaries.
2. Every registered adapter produces a bounded prompt.
3. Every token budget preserves acceptance criteria, repository evidence, validation guidance, and valid JSON.
4. A repeated route is served from Prompt Cache with the same immutable routing ID.
5. Every Provider Router rule selects the expected model.
6. Prompt Diagnostics contains complete manifest, package, repository, knowledge, memory, model, token, and confidence lineage.
7. Repeated pipeline execution produces the same deterministic fingerprint.
8. Every local deterministic stage remains within its performance target.

## Token Safety

Supported budgets are 1,024, 2,048, 4,096, 8,192, 16,000, 32,000, and 128,000 tokens.

A budget passes the safety gate when protected context and JSON integrity are preserved. A small budget may return `Blocked` when protected context cannot fit. That is a correct production-safe result: Prompt Intelligence must block visibly rather than truncate acceptance criteria, repository evidence, or validation guidance.

## Model Coverage

The benchmark compiles GPT, Codex, Claude, Gemini, GLM, Qwen, and Ollama adapters. Model Registry profiles without a deterministic adapter are excluded from adapter success counts and remain ineligible in Provider Router diagnostics.

## Performance Targets

| Stage | Local target |
| --- | ---: |
| Execution Manifest | 100 ms |
| Prompt Compiler | 100 ms |
| Token Intelligence | 150 ms |
| Model Adapter | 100 ms |
| Prompt Optimizer | 100 ms |
| Prompt Diagnostics | 100 ms |
| Cold Provider Router decision | 250 ms |
| Prompt Cache hit | 50 ms |

These are single-process local baselines. They exclude repository clone, provider, network, and distributed-storage latency.

## APIs

- `POST /prompt-intelligence/hardening/run`
- `GET /prompt-intelligence/hardening/report`
- `GET /prompt-intelligence/hardening/runs/{runId}`

## Commands

Run the production-readiness regression suite:

```sh
bin/test-hei-e2e
```

Regenerate the benchmark report:

```sh
python3 bin/benchmark-prompt-intelligence
```

Generated outputs:

- `docs/testing/prompt-intelligence-benchmark.md`
- `docs/testing/prompt-intelligence-benchmark.json`

## Known Limitations

- Repository fixtures model metadata and evidence boundaries; they do not clone a live repository.
- Provider transport, provider response parsing, cost, and remote latency are outside this deterministic milestone.
- JSON persistence is suitable for local validation but not distributed concurrent benchmark writers.
- Benchmarks are environment-sensitive and should be regenerated on the target deployment class before setting capacity objectives.
- Full repository discovery on 2026-07-13 ran 891 tests and reported 10 failures plus 1 error in legacy Project Intelligence QA, planning/validation alignment, and execution-package normalization. The focused Prompt Intelligence production-readiness suite remains green; these broader failures are not hidden or counted as passing.
