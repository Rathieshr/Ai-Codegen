import { IAuthenticationProvider } from "../authentication";
import { ISdkCache } from "../cache";
import { ResolvedSdkConfiguration } from "../configuration/SdkConfiguration";
import {
  AuthenticationException, HEIException, NetworkException, PlanningException,
  RepositoryException, RuntimeException, TimeoutException, ValidationException
} from "./errors";
import { IDiagnosticsSink, ITelemetrySink } from "../diagnostics";
import { SdkEventBus } from "../events";
import { HEIRecord, OperationResult, RequestContext, RequestDiagnostics } from "../models";
import { ITransport } from "../transport/ITransport";
import { OPERATION_CATALOG, OperationDefinition } from "../transport/OperationCatalog";

export class PlatformGateway {
  constructor(
    private readonly configuration: ResolvedSdkConfiguration,
    private readonly transport: ITransport,
    private readonly authentication: IAuthenticationProvider,
    private readonly cache: ISdkCache,
    private readonly diagnostics: IDiagnosticsSink,
    private readonly telemetry: ITelemetrySink,
    private readonly events: SdkEventBus
  ) {}

  async execute<T>(operation: string, input: HEIRecord = {}, context: RequestContext = {}): Promise<OperationResult<T>> {
    const definition = OPERATION_CATALOG[operation];
    if (!definition) throw new ValidationException(`Unknown HEI SDK operation: ${operation}.`);
    const correlationId = context.correlationId || createCorrelationId();
    const versions = collectVersions(context);
    const cacheKey = `${operation}:${stableJson(input)}`;
    const useCache = this.configuration.enableCaching && !!definition.cacheable && !context.bypassCache;
    const cached = useCache ? this.cache.get<T>(cacheKey, versions) : undefined;
    if (cached !== undefined) {
      const value = this.buildDiagnostics(operation, correlationId, 0, 0, "hit", versions);
      this.record(value, true, true);
      return { data: cached, diagnostics: value };
    }

    const started = performance.now();
    let retries = 0;
    this.events.publish({ name: "RequestStarted", operation, correlationId });
    try {
      let authenticationHeaders: Record<string, string>;
      try { authenticationHeaders = await this.authentication.getHeaders(); }
      catch (error) {
        this.events.publish({ name: "AuthenticationFailed", operation, correlationId });
        throw error instanceof HEIException ? error : new AuthenticationException("HEI authentication failed.", correlationId, 401, error);
      }

      while (true) {
        try {
          const response = await this.transport.send<T>({
            operation,
            method: definition.method,
            path: typeof definition.path === "function" ? definition.path(input) : definition.path,
            headers: {
              Accept: "application/json",
              "Content-Type": "application/json",
              "X-Correlation-ID": correlationId,
              "X-HEI-SDK-Version": this.configuration.sdkVersion,
              "X-HEI-API-Version": this.configuration.apiVersion,
              ...authenticationHeaders
            },
            query: buildQuery(definition, input),
            body: definition.method === "GET" ? undefined : buildBody(definition, input),
            timeoutMs: this.configuration.timeoutMs,
            correlationId
          });
          if (useCache) this.cache.set(cacheKey, response.data, versions);
          if (definition.method !== "GET") this.cache.invalidate(key => key.startsWith(`${operation.split(".")[0]}.`));
          const value = this.buildDiagnostics(operation, correlationId, performance.now() - started, retries, useCache ? "miss" : context.bypassCache ? "bypass" : "disabled", versions);
          this.record(value, true, false);
          if (retries > 0) this.events.publish({ name: "Reconnect", operation, correlationId, details: { retries } });
          this.events.publish({ name: "RequestCompleted", operation, correlationId, details: { retries, durationMs: value.durationMs } });
          return { data: response.data, diagnostics: value };
        } catch (error) {
          if (retries >= this.configuration.retryCount || !isRetryable(error)) throw error;
          retries += 1;
          this.events.publish({ name: "Retry", operation, correlationId, details: { attempt: retries } });
          await delay(this.configuration.retryDelayMs * retries);
        }
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : `HEI operation ${operation} failed.`;
      const value = this.buildDiagnostics(operation, correlationId, performance.now() - started, retries, "disabled", versions, [message]);
      this.record(value, false, false);
      if (error instanceof NetworkException || error instanceof TimeoutException) this.events.publish({ name: "ConnectionLost", operation, correlationId, details: { message } });
      this.events.publish({ name: "RequestFailed", operation, correlationId, details: { retries, message: (error as Error).message } });
      throw mapException(operation, error, correlationId);
    }
  }

  private buildDiagnostics(operation: string, correlationId: string, durationMs: number, retries: number, cacheStatus: RequestDiagnostics["cacheStatus"], versions: Record<string, string>, errors: string[] = []): RequestDiagnostics {
    return {
      operation, correlationId, sdkVersion: this.configuration.sdkVersion,
      platformVersion: this.configuration.platformVersion,
      durationMs: Math.round(durationMs * 100) / 100, retries, cacheStatus,
      transport: this.transport.name, warnings: [], errors, versions
    };
  }

  private record(value: RequestDiagnostics, success: boolean, cacheHit: boolean): void {
    if (this.configuration.enableDiagnostics) this.diagnostics.record(value);
    if (this.configuration.enableTelemetry) this.telemetry.record({
      operation: value.operation, durationMs: value.durationMs, success,
      retries: value.retries, cacheHit, transport: value.transport
    });
  }
}

function buildQuery(definition: OperationDefinition, input: HEIRecord): Record<string, string | number | boolean | undefined> | undefined {
  if (!definition.queryFields?.length) return undefined;
  return Object.fromEntries(definition.queryFields.map(key => [key, input[key] as string | number | boolean | undefined]));
}

function buildBody(definition: OperationDefinition, input: HEIRecord): HEIRecord {
  if (!definition.bodyFields?.length) return input;
  return Object.fromEntries(definition.bodyFields.map(key => [key, input[key]]).filter(([, value]) => value !== undefined));
}

function collectVersions(context: RequestContext): Record<string, string> {
  const pairs = {
    executionPackage: context.executionPackageVersion,
    repositorySnapshot: context.repositorySnapshotVersion,
    contextCapsule: context.contextCapsuleVersion,
    knowledge: context.knowledgeVersion,
    memory: context.memoryVersion
  };
  return Object.fromEntries(Object.entries(pairs).filter((entry): entry is [string, string] => !!entry[1]));
}

function mapException(operation: string, error: unknown, correlationId: string): HEIException {
  if (error instanceof AuthenticationException || error instanceof TimeoutException) return error;
  const status = error instanceof HEIException ? error.status : undefined;
  const details = error instanceof HEIException ? error.details : error;
  const message = error instanceof Error ? error.message : `HEI operation ${operation} failed.`;
  if (operation.startsWith("repository.")) return new RepositoryException(message, correlationId, status, details);
  if (operation.startsWith("planning.")) return new PlanningException(message, correlationId, status, details);
  if (operation.startsWith("runtime.")) return new RuntimeException(message, correlationId, status, details);
  if (operation.startsWith("validation.")) return new ValidationException(message, correlationId, details);
  return error instanceof HEIException ? error : new NetworkException(message, correlationId, status, details);
}

function isRetryable(error: unknown): boolean {
  return error instanceof TimeoutException || (error instanceof NetworkException && (!error.status || error.status >= 500));
}

function createCorrelationId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `hei-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function stableJson(value: unknown): string {
  if (!value || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(stableJson).join(",")}]`;
  return `{${Object.entries(value as HEIRecord).sort(([a], [b]) => a.localeCompare(b)).map(([key, item]) => `${JSON.stringify(key)}:${stableJson(item)}`).join(",")}}`;
}

const delay = (milliseconds: number): Promise<void> => new Promise(resolve => setTimeout(resolve, milliseconds));
