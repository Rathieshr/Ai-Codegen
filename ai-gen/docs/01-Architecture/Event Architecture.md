# Event Architecture

Platform events record state changes and trigger governed workflows.

## Event envelope

Every event should include event type, source, timestamp, project/repository identifiers where applicable, correlation ID, artifact identifiers, schema version, and bounded payload.

## Event classes

- Repository: registered, synchronization requested, snapshot completed, graph refreshed.
- Planning: analyzed, generated, reviewed, approved, rejected.
- Execution: capsule created, package built, manifest compiled.
- Validation and QA: validation completed, gaps detected, release recommendation produced.
- Memory: capture drafted, approved, indexed, deprecated.
- Operations: job queued, retry scheduled, health changed, policy blocked.

Events do not grant permission. Consumers must re-evaluate policy and artifact state before acting.
