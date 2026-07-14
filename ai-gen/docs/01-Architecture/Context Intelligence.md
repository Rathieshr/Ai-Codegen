# Context Intelligence Architecture

Context Intelligence converts permitted source evidence into one bounded Context Capsule.

`Request -> Retrieve once -> Normalize -> Rank -> Filter -> Budget -> Version -> Persist -> Trace`

It preserves selected and rejected evidence, source versions, freshness, confidence, token use, and correlation identity. A stale source remains usable with a warning and lower readiness. Duplicate retrieval is a quality failure.

See the current implementation detail in [Context Orchestrator](../architecture/context-orchestrator.md).
