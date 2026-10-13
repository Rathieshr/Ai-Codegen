# Runtime Recovery

Milestone 5.9 makes AI execution sessions recoverable without granting HEI provider, Git, repository, or Azure DevOps write authority.

## Recovery model

Every persisted session records:

- attempt and retry limit
- retry and resume counts
- last checkpoint and last failure
- response identities and dispositions
- partial provider responses
- duplicate response count
- recovery transition history

Recoverable states are `Failed`, `TimedOut`, `PartialResponse`, and `Cancelled`. `Completed` remains terminal. Retry and resume reopen a session as `AwaitingResponse`; they publish intent events but do not invoke a provider.

## Idempotency

Session start accepts `idempotencyKey`. Replaying the same key returns the persisted session and does not publish another `ExecutionStarted` event.

Provider callbacks accept `metadata.idempotencyKey` or `metadata.responseId`. If neither is supplied, HEI derives an identity from the response. A duplicate callback is acknowledged as `DuplicateIgnored` and is not interpreted again. This remains effective after process restart because response identities are persisted with the session.

Failure reports may also include `idempotencyKey`, preventing duplicate provider or network failure transitions.

## Partial responses

A callback with `metadata.partial: true` is retained as a partial checkpoint and does not produce an Execution Result. The session may be resumed and later completed with a distinct final response. Partial content is not treated as completed engineering evidence.

## Events

- `ExecutionResumed`
- `ExecutionRetried`
- `ExecutionTimedOut`
- `ExecutionRecovered`
- `ExecutionPartialResponseReceived`
- `ExecutionDuplicateResponseIgnored`

Existing `ExecutionFailed`, `ExecutionCancelled`, and completion events remain authoritative.

## API

- `POST /execution-runtime/{sessionId}/retry`
- `POST /execution-runtime/{sessionId}/resume`
- `POST /execution-runtime/{sessionId}/timeout`
- `POST /execution-runtime/{sessionId}/failure`

The failure endpoint supports `ProviderFailure`, `NetworkFailure`, and `RuntimeFailure`. Timeout has a dedicated command and event.
