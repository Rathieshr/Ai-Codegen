# Prompt Intelligence Benchmark

Generated: 2026-07-13T07:45:14.976502+00:00

Readiness: **Production Ready**

## Quality Gates

| Gate | Status | Details |
| --- | --- | --- |
| Repository modes | PASS | Large, small, snapshot, and unavailable modes preserve truthful evidence. |
| Model adapters | PASS | Every registered deterministic adapter produces a bounded prompt. |
| Token safety | PASS | Every supported budget preserves protected JSON context. |
| Prompt cache | PASS | Repeated generation is served from cache with immutable routing identity. |
| Provider routing | PASS | Every routing rule selects the expected eligible model. |
| Prompt diagnostics | PASS | Prompt lineage and model diagnostics are complete. |
| Regression stability | PASS | Two identical runs produce the same deterministic fingerprint. |
| Performance | PASS | Every deterministic stage remains within its local benchmark target. |

## Repository Scenarios

| Scenario | Mode | Files | Status | Duration |
| --- | --- | ---: | --- | ---: |
| small-code-indexed (Small Repository) | CodeIndexed | 4 | Passed | 3.36 ms |
| large-code-indexed (Large Repository) | CodeIndexed | 600 | Passed | 13.12 ms |
| knowledge-snapshot (Small Repository) | KnowledgeSnapshot | 0 | Passed | 2.73 ms |
| repository-unavailable (Unavailable Repository) | Unavailable | 0 | Passed | 2.37 ms |

## Model Adapters

| Model | Status | Tokens | Duration |
| --- | --- | ---: | ---: |
| gpt | Passed | 1487 | 1.10 ms |
| codex | Passed | 1483 | 1.41 ms |
| claude | Passed | 1488 | 1.31 ms |
| gemini | Passed | 1490 | 1.38 ms |
| glm | Passed | 1485 | 1.17 ms |
| qwen | Passed | 1481 | 1.32 ms |
| ollama | Passed | 1437 | 1.11 ms |

## Token Budgets

| Budget | Safety Gate | Engine Result | Prompt Tokens | Remaining |
| ---: | --- | --- | ---: | ---: |
| 1024 | Passed | Blocked | 923 | -155 |
| 2048 | Passed | Ready | 1339 | 325 |
| 4096 | Passed | Ready | 1339 | 1989 |
| 8192 | Passed | Ready | 1339 | 5829 |
| 16000 | Passed | Ready | 1339 | 12613 |
| 32000 | Passed | Ready | 1339 | 26565 |
| 128000 | Passed | Ready | 1339 | 118469 |

## Cache

- First request: Miss
- Repeated request: Hit
- Hit rate: 50.0%
- Generations avoided: 1
- Estimated tokens saved: 1483

## Routing And Diagnostics

- Routing rules passed: 6/6
- Diagnostics status: Passed
- Regression stability: Passed

## Performance

| Stage | Average | Maximum | Target | Status |
| --- | ---: | ---: | ---: | --- |
| manifest | 0.47 ms | 0.97 ms | 100.00 ms | PASS |
| compile | 1.62 ms | 4.97 ms | 100.00 ms | PASS |
| tokenBudget | 0.83 ms | 2.54 ms | 150.00 ms | PASS |
| adapter | 0.55 ms | 1.38 ms | 100.00 ms | PASS |
| optimizer | 0.88 ms | 1.97 ms | 100.00 ms | PASS |
| diagnostics | 0.24 ms | 0.24 ms | 100.00 ms | PASS |
| routingCold | 5.27 ms | 5.27 ms | 250.00 ms | PASS |
| routingCacheHit | 0.70 ms | 0.70 ms | 50.00 ms | PASS |

## Limitations

- Benchmarks measure deterministic local processing and exclude provider, network, and repository clone latency.
- Large repository coverage uses generated repository metadata rather than a live source checkout.
- JSON-backed benchmark persistence is intended for single-process validation, not distributed load testing.
- Production Ready applies to the deterministic Prompt Intelligence boundary; full repository regression status is reported separately.
