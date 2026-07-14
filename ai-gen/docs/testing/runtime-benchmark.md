# Execution Runtime Benchmark

- Run: `runtime-hardening-fb8c562ad1fa`
- Generated: 2026-07-13T09:32:58.996237+00:00
- Runtime version: 5.10
- Readiness: **Production Ready**
- Gates: 10/10 passed

## Workloads

| Scenario | Repository files | Prompt bytes | Response bytes | Latency ms | Peak memory MB | Status |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Small Repository | 8 | 512 | 626 | 10.25 | 0.230 | Passed |
| Large Repository | 2,500 | 4,096 | 15,082 | 142.98 | 3.748 | Passed |
| Small Prompt | 25 | 64 | 375 | 9.16 | 0.036 | Passed |
| Large Prompt | 100 | 128,000 | 2,608 | 18.19 | 0.092 | Passed |
| Large AI Response | 800 | 8,192 | 670,520 | 251.71 | 6.700 | Passed |

## Concurrency

- Sessions: 24
- Completed: 24
- Failed: 0
- Average latency: 528.99 ms
- P95 latency: 899.81 ms
- Average queue time: 294.13 ms
- P95 queue time: 892.25 ms
- Failure rate: 0%

## Performance

- Average workload latency: 86.46 ms
- P95 workload latency: 251.71 ms
- Maximum workload latency: 251.71 ms
- CPU process time: 2,440.51 ms
- Peak traced Python memory: 11.129 MB
- Maximum response size: 670,520 bytes
- Maximum token pressure: 128,000 accounted tokens

## Recovery

- Timeout followed by retry: Passed
- Duplicate callback ignored: Passed
- Partial response persisted: Passed
- Restart followed by resume: Passed
- Attempt history preserved: Passed

## API Regression

- Expected Runtime, Recovery, and Observability routes: 12
- Actual routes: 12
- Missing routes: 0
- Unexpected routes: 0
- Idempotent start: Passed

## Quality Gates

- PASS: Repository profiles
- PASS: Prompt pressure
- PASS: Response and token pressure
- PASS: Concurrent execution
- PASS: Runtime recovery
- PASS: Runtime API regression
- PASS: Latency
- PASS: Memory pressure
- PASS: Failure rate
- PASS: Runtime safety

## Known Limitations

- Measurements cover deterministic local Runtime processing and exclude live provider and network latency.
- Repository workloads use generated metadata and do not clone or traverse live repositories.
- Concurrency validates one process with JSON persistence; distributed multi-process load requires an external transactional store.
- Python `tracemalloc` excludes native allocator and operating-system memory.
- Production Ready applies to the Execution Runtime boundary; repository-wide regression status is reported separately.

## Reproduce

```bash
python3 -m unittest tests.test_runtime_hardening_milestone_5_10 -v
```
