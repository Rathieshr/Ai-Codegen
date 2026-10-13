# Runtime Observability

Milestone 5.8 adds a persistent, read-only trace projection for every AI execution. It observes platform events and does not invoke providers, modify repositories, trigger validation or QA, capture Engineering Memory, or create pull requests.

## Pipeline

Runtime and platform services publish events with a shared `correlationId`. `RuntimeObservabilityService` subscribes to the wildcard platform event stream, maps relevant events to a canonical timeline, enriches metrics from the persisted execution session, and stores an independent trace projection.

The canonical timeline is:

1. Execution Started
2. Prompt Generated
3. Provider Called
4. Response Received
5. Interpreted
6. Engineering Diff
7. Validation
8. QA
9. Memory
10. Completed

Repeated events for one stage update that stage while retaining its event history. Unrelated platform events are ignored. Duplicate event IDs are idempotent.

`ProviderCalled` must be published by the provider invocation boundary. A provider routing decision is deliberately not treated as a provider call. Missing events remain absent rather than being inferred.

## Metrics

Each trace includes duration, provider, model, input/output/total tokens, confidence, warnings, failures, and correlation ID. Active traces calculate duration at read time, so long-running executions remain observable without periodic writes.

Trace details contain identifiers and compact stage metadata only. Raw provider responses, source code, prompts, and repository contents are not copied into observability storage.

## Concurrency

Trace updates are serialized inside the projection service. Each correlation ID maps to one deterministic trace ID, preventing concurrent sessions with distinct correlation IDs from overwriting one another.

## API

- `GET /runtime/traces`
- `GET /runtime/traces/{id}`

The list endpoint supports optional `status`, `provider`, and `limit` filters. The detail endpoint accepts a trace ID, session ID, or correlation ID.
