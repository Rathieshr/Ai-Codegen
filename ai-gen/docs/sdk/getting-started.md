# Getting Started

## Install

During monorepo development:

```json
{
  "dependencies": {
    "@hei/platform-sdk": "file:../sdk"
  }
}
```

## Initialize

```ts
import { BearerTokenAuthenticationProvider, HEISdk } from "@hei/platform-sdk";

const sdk = new HEISdk(
  {
    baseUrl: process.env.HEI_BASE_URL ?? "http://127.0.0.1:8000",
    environment: "development",
    timeoutMs: 30_000,
    retryCount: 2,
    enableCaching: true,
    enableDiagnostics: true
  },
  {
    authentication: new BearerTokenAuthenticationProvider(async () => acquireToken())
  }
);

await sdk.initialize();
```

`initialize()` checks platform health and SDK version compatibility. It does not run planning, repository synchronization, or AI generation.

## Subscribe to events

```ts
const unsubscribe = sdk.events.subscribe("*", event => {
  console.log(event.name, event.correlationId);
});

unsubscribe();
```

## Preserve lineage

```ts
const packageResult = await sdk.execution.buildExecutionPackage(
  { contextCapsule, executionRequest },
  {
    correlationId: "delivery-421",
    contextCapsuleVersion: "capsule-v4",
    repositorySnapshotVersion: "snapshot-v18",
    knowledgeVersion: "knowledge-v7"
  }
);
```

## Handle typed errors

```ts
import { RepositoryException } from "@hei/platform-sdk";

try {
  await sdk.repository.getSnapshot("repo-42");
} catch (error) {
  if (error instanceof RepositoryException) {
    console.error(error.correlationId, error.status, error.message);
  }
}
```

## Replace the transport

Implement `ITransport` and pass it to the constructor. Service contracts and client code remain unchanged.
