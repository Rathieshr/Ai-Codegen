# HEI Platform SDK Architecture

## Decision

The HEI Platform SDK is the public API of the HEI platform. REST endpoints are an internal transport implementation.

## Layered model

```text
VS Code | Azure DevOps | Portal | CLI | Teams | MCP | IDE plugins
                              |
                         HEI Platform SDK
                              |
              Planning / Repository / Context / Execution
              Prompt / Runtime / Validation / QA / Memory
                              |
                       Platform Gateway
                              |
                         ITransport
                              |
                   RestTransport (Milestone 5.11)
                              |
                       HEI Backend APIs
```

## Dependency rule

Dependencies point downward only. Client code may depend on `IHEISdk`, service contracts, public models, and public exceptions. It must not depend on `PlatformGateway`, `OperationCatalog`, route strings, or backend implementation modules.

## Protocol independence

Business service methods issue named platform operations. `OperationCatalog` maps those operations to the current REST contract. A future adapter may map the same operations to gRPC methods, local runtime calls, or enterprise message transport without changing service consumers.

## Current limitations

- REST is the only production transport.
- Streaming has an interface but no adapter.
- Azure AD and PAT have extension points but no provider implementation.
- Cache storage is process-local memory.
- Existing VS Code and Azure DevOps extensions still contain direct HTTP calls and require incremental migration.
- Some legacy backend capabilities expose compatibility operations; service contracts remain stable while route mappings converge.
