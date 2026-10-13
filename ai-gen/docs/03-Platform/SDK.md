# HEI Platform SDK

The HEI Platform SDK is the public programming interface for HEI clients. It exposes versioned business services for Planning, Repository, Context, Execution, Prompt, Runtime, Validation, QA, Engineering Memory, Azure DevOps, and Platform operations.

Clients consume `IHEISdk` and never import backend implementation modules, internal route catalogs, or transport-specific request models. Authentication, retries, correlation IDs, caching, telemetry, diagnostics, and compatibility checks are shared SDK concerns.

REST is the first transport adapter and is not the public contract. Future gRPC, WebSocket, MCP, and local-runtime integrations attach below the service contracts.

See [the SDK architecture](../sdk/README.md) and [getting started](../sdk/getting-started.md).
