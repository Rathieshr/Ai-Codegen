# HEI Platform SDK

## Public platform boundary

The HEI Platform SDK is the supported integration boundary for VS Code, Azure DevOps, the Engineering Command Center, CLI tools, Teams, IDE plugins, MCP servers, and external enterprise integrations.

```text
Client Application
        |
IHEISdk / HEISdk
        |
Business Service Contracts
        |
Platform Gateway
        |
ITransport
        |
REST today | gRPC future | WebSocket future | Local Runtime future
```

REST route names, headers, retries, authentication, correlation IDs, cache behavior, diagnostics, and compatibility checks are implementation details behind the SDK.

## Contract ownership

| Layer | Owns | Must not own |
| --- | --- | --- |
| Client | User experience and client-specific state | Backend routes or retry logic |
| SDK facade | Initialization and platform service discovery | Domain implementation logic |
| Service contracts | Business operations and typed inputs/outputs | HTTP methods and URLs |
| Platform gateway | Correlation, retries, cache, diagnostics, events | Backend business logic |
| Transport | Protocol serialization and delivery | Planning or engineering decisions |
| Backend | Platform intelligence and persisted engineering state | Client-specific presentation |

## Cross-cutting behavior

Every SDK operation can carry:

- correlation ID;
- SDK and API version headers;
- Execution Package, Repository Snapshot, Context Capsule, Knowledge, and Memory versions;
- retry and duration diagnostics;
- cache hit or miss state;
- transport name and warnings.

Events include `RequestStarted`, `RequestCompleted`, `RequestFailed`, `Retry`, `AuthenticationFailed`, `ConnectionLost`, and `Reconnect`.

## Authentication

Implemented providers:

- Anonymous
- API key
- Bearer token, including asynchronous token resolution

Azure AD and PAT are reserved as pluggable provider contracts. They are not implemented in Milestone 5.11.

## Caching

The initial in-memory cache supports Repository Snapshot, Engineering Graph, Context, Execution, Model Registry, and other cacheable reads. Version metadata is part of cache validation. A changed upstream version causes a miss instead of returning stale data.

## Streaming

`IStreamingTransport` reserves an async-stream contract for Runtime events, Prompt streaming, Repository Synchronization, and Agent events. `RestTransport` does not implement streaming in this milestone.

## Migration rule

New clients must use `IHEISdk`. Existing VS Code and Azure DevOps clients can migrate incrementally by replacing direct `fetch` calls with the corresponding service method. The internal operation catalog must never be imported by a client.

See the [service reference](service-reference.md) and [versioning and migration guide](versioning.md).
