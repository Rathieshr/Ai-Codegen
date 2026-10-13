const test = require("node:test");
const assert = require("node:assert/strict");

const {
  ApiKeyAuthenticationProvider,
  AuthenticationException,
  HEISdk,
  MemoryDiagnosticsSink,
  MemoryTelemetrySink,
  NetworkException,
  RepositoryException,
  VersionCompatibilityException
} = require("../dist");

class MockTransport {
  name = "mock";
  requests = [];
  constructor(responder = async request => ({ data: { operation: request.operation }, status: 200, headers: {} })) {
    this.responder = responder;
  }
  async send(request) {
    this.requests.push(request);
    return this.responder(request, this.requests.length);
  }
}

const configuration = (overrides = {}) => ({
  baseUrl: "https://hei.example.test/",
  retryDelayMs: 1,
  timeoutMs: 100,
  ...overrides
});

test("SDK initializes and exposes every platform service", async () => {
  const transport = new MockTransport(async request => ({
    data: request.operation === "platform.health" ? { status: "healthy", minimumSdkVersion: "0.1.0" } : {},
    status: 200,
    headers: {}
  }));
  const sdk = new HEISdk(configuration(), { transport });
  await sdk.initialize();
  for (const name of ["planning", "repository", "context", "execution", "prompt", "runtime", "validation", "qa", "memory", "azureDevOps", "platform"]) {
    assert.ok(sdk[name], name);
  }
  assert.equal(sdk.configuration.baseUrl, "https://hei.example.test");
  assert.equal(transport.requests[0].operation, "platform.health");
});

test("authentication and correlation metadata are injected automatically", async () => {
  const transport = new MockTransport();
  const diagnostics = new MemoryDiagnosticsSink();
  const sdk = new HEISdk(configuration(), {
    transport,
    diagnostics,
    authentication: new ApiKeyAuthenticationProvider("secret")
  });
  const result = await sdk.planning.analyzeRequirement({ description: "Device health" }, { correlationId: "corr-511" });
  const request = transport.requests[0];
  assert.equal(request.headers["X-API-Key"], "secret");
  assert.equal(request.headers["X-Correlation-ID"], "corr-511");
  assert.equal(request.headers["X-HEI-SDK-Version"], "0.1.0");
  assert.equal(result.diagnostics.correlationId, "corr-511");
  assert.equal(diagnostics.latest().operation, "planning.analyzeRequirement");
});

test("correlation IDs are generated when the caller does not provide one", async () => {
  const transport = new MockTransport();
  const sdk = new HEISdk(configuration(), { transport });
  const result = await sdk.platform.getCapabilities();
  assert.ok(result.diagnostics.correlationId.startsWith("hei-") || result.diagnostics.correlationId.length >= 20);
  assert.equal(transport.requests[0].headers["X-Correlation-ID"], result.diagnostics.correlationId);
});

test("retry policy emits events and records telemetry", async () => {
  const transport = new MockTransport(async (_request, attempt) => {
    if (attempt === 1) throw new NetworkException("temporary", undefined, 503);
    return { data: { status: "healthy" }, status: 200, headers: {} };
  });
  const telemetry = new MemoryTelemetrySink();
  const sdk = new HEISdk(configuration({ retryCount: 2, enableTelemetry: true }), { transport, telemetry });
  const events = [];
  sdk.events.subscribe("*", event => events.push(event.name));
  const result = await sdk.platform.getHealth();
  assert.equal(result.diagnostics.retries, 1);
  assert.equal(transport.requests.length, 2);
  assert.ok(events.includes("Retry"));
  assert.ok(events.includes("Reconnect"));
  assert.equal(telemetry.list()[0].retries, 1);
  assert.equal(telemetry.list()[0].success, true);
});

test("version-aware cache prevents duplicate transport calls and invalidates on version change", async () => {
  const transport = new MockTransport(async () => ({ data: [{ id: "repo-1" }], status: 200, headers: {} }));
  const sdk = new HEISdk(configuration(), { transport });
  const first = await sdk.repository.listRepositories({ repositorySnapshotVersion: "v1" });
  const second = await sdk.repository.listRepositories({ repositorySnapshotVersion: "v1" });
  const third = await sdk.repository.listRepositories({ repositorySnapshotVersion: "v2" });
  assert.equal(first.diagnostics.cacheStatus, "miss");
  assert.equal(second.diagnostics.cacheStatus, "hit");
  assert.equal(third.diagnostics.cacheStatus, "miss");
  assert.equal(transport.requests.length, 2);
  assert.equal(sdk.invalidateCache("repository"), 1);
});

test("repository failures are exposed as typed SDK exceptions", async () => {
  const transport = new MockTransport(async () => { throw new NetworkException("missing", undefined, 404, { detail: "not found" }); });
  const diagnostics = new MemoryDiagnosticsSink();
  const sdk = new HEISdk(configuration(), { transport, diagnostics });
  await assert.rejects(
    () => sdk.repository.getRepository("missing"),
    error => error instanceof RepositoryException && error.status === 404 && !!error.correlationId
  );
  assert.equal(diagnostics.latest().errors[0], "missing");
});

test("authentication failures publish an event and do not reach transport", async () => {
  const transport = new MockTransport();
  const authentication = { mode: "bearer", getHeaders: async () => { throw new AuthenticationException("expired"); } };
  const sdk = new HEISdk(configuration(), { transport, authentication });
  const events = [];
  sdk.events.subscribe("*", event => events.push(event.name));
  await assert.rejects(() => sdk.platform.getHealth(), AuthenticationException);
  assert.ok(events.includes("AuthenticationFailed"));
  assert.equal(transport.requests.length, 0);
});

test("service contracts hide route construction behind the transport boundary", async () => {
  const transport = new MockTransport();
  const sdk = new HEISdk(configuration(), { transport });
  await sdk.runtime.retryExecution("session/1", { reason: "retry" });
  assert.equal(transport.requests[0].operation, "runtime.retry");
  assert.equal(transport.requests[0].path, "/execution-runtime/session%2F1/retry");
  assert.equal(transport.requests[0].body.reason, "retry");
});

test("Azure DevOps service uses the read-only integration boundary", async () => {
  const transport = new MockTransport();
  const sdk = new HEISdk(configuration(), { transport });
  await sdk.azureDevOps.listPullRequests("connection/1", "Grid Hub", "repo/1");
  const request = transport.requests[0];
  assert.equal(request.operation, "azureDevOps.listPullRequests");
  assert.equal(request.method, "GET");
  assert.equal(request.path, "/integrations/azure-devops/connections/connection%2F1/projects/Grid%20Hub/pull-requests");
  assert.equal(request.query.repositoryId, "repo/1");
});

test("Azure DevOps synchronization hides route fields from request bodies", async () => {
  const transport = new MockTransport();
  const sdk = new HEISdk(configuration(), { transport });
  await sdk.azureDevOps.syncProject("connection/1", "Grid Hub", "IncrementalSync");
  assert.equal(transport.requests[0].path, "/integrations/azure-devops/projects/Grid%20Hub/sync");
  assert.deepEqual(transport.requests[0].body, { connectionId: "connection/1", syncType: "IncrementalSync" });
  await sdk.azureDevOps.reconcileProject("connection/1", "Grid Hub");
  assert.deepEqual(transport.requests[1].body, { connectionId: "connection/1" });
});

test("Azure DevOps agent approval packs use bounded SDK operations", async () => {
  const transport = new MockTransport();
  const sdk = new HEISdk(configuration(), { transport });
  await sdk.azureDevOps.approveActionPack("pack/1", { actor: "product-owner", reason: "Reviewed" });
  assert.equal(transport.requests[0].path, "/ado-agent/action-packs/pack%2F1/approve");
  assert.deepEqual(transport.requests[0].body, { actor: "product-owner", reason: "Reviewed" });
  await sdk.azureDevOps.applyActionPack("pack/1", { actor: "release-manager", idempotencyKey: "apply-1" });
  assert.equal(transport.requests[1].path, "/ado-agent/action-packs/pack%2F1/apply");
  assert.deepEqual(transport.requests[1].body, { actor: "release-manager", idempotencyKey: "apply-1" });
});

test("incompatible platform versions fail during initialization", async () => {
  const transport = new MockTransport(async () => ({ data: { minimumSdkVersion: "2.0.0" }, status: 200, headers: {} }));
  const sdk = new HEISdk(configuration(), { transport });
  await assert.rejects(() => sdk.initialize(), VersionCompatibilityException);
});

test("REST operation catalog remains an internal package detail", () => {
  const publicApi = require("../dist");
  assert.equal(publicApi.OPERATION_CATALOG, undefined);
  assert.equal(publicApi.PlatformGateway, undefined);
});
