# Command Center User Guide

## Check Platform Readiness

1. Open **Health**.
2. Confirm Platform, Queue, SDK, Storage, Database, and Memory status.
3. Review service latency and any service marked Degraded or Unavailable.
4. Use **Refresh Now** after resolving an issue.

The workspace refreshes in the background while visible. When offline, the last snapshot remains available and automatic refresh resumes after reconnection.

## Investigate a Failure

1. Open the Jobs or Events tab in Health.
2. Open **Activity** for the chronological record.
3. Search by artifact, actor, event, or correlation ID.
4. Open **Correlation Trace** to follow the lifecycle across systems.
5. Use **Replay View** to reconstruct recorded context. Replay never reruns a job, provider call, approval, repository operation, or Azure DevOps write.

Admins can open Diagnostics in Health for probe warnings and operational counts. Sensitive credentials, tokens, and raw provider responses are never displayed.
