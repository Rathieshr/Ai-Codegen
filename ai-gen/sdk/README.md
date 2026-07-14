# HEI Platform SDK

The HEI Platform SDK is the public programming interface for HEI clients. Applications consume business-oriented service contracts; transports own backend protocol details.

```text
Application Layer
        |
HEI Platform SDK
        |
Service Contracts
        |
Platform Gateway
        |
Transport Layer
        |
HEI Backend APIs
```

## Services

- `planning`
- `repository`
- `context`
- `execution`
- `prompt`
- `runtime`
- `validation`
- `qa`
- `memory`
- `azureDevOps`
- `platform`

## Quick start

```ts
import { ApiKeyAuthenticationProvider, HEISdk } from "@hei/platform-sdk";

const hei = new HEISdk(
  { baseUrl: "https://hei.example.com", enableDiagnostics: true },
  { authentication: new ApiKeyAuthenticationProvider(process.env.HEI_API_KEY ?? "") }
);

await hei.initialize();
const result = await hei.planning.analyzeRequirement({
  title: "Device Health Dashboard",
  description: "Give operations users a current view of device health."
});

console.log(result.data);
console.log(result.diagnostics.correlationId);
```

Clients must not import `OperationCatalog` or construct backend routes. Use the service facade only.

## Build and test

```bash
npm install
npm test
```

The package has no runtime dependencies. Node 18 or a browser/webview with `fetch` is required by `RestTransport`. Custom transports can support gRPC, WebSocket, local execution, test doubles, or enterprise gateways.
