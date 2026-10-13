# Operations

## Operational concerns

- Backend and dependency health.
- Job queues, retries, cancellation, and dead-letter handling.
- Repository synchronization and agent status.
- Provider health, latency, token use, parsing, and failures.
- Audit, activity, notifications, and correlation traces.
- Artifact, snapshot, and Engineering Memory storage.
- Feature flags, policy configuration, and deployment rollback.

Operational dashboards report measured state. They must not label a provider or repository healthy when the underlying dependency was skipped or unavailable.
