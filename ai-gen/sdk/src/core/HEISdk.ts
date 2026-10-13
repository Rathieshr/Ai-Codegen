import { AnonymousAuthenticationProvider, IAuthenticationProvider } from "../authentication";
import { ISdkCache, MemorySdkCache } from "../cache";
import { ResolvedSdkConfiguration, SdkConfiguration, resolveConfiguration } from "../configuration/SdkConfiguration";
import { IDiagnosticsSink, ITelemetrySink, MemoryDiagnosticsSink, NoopTelemetrySink } from "../diagnostics";
import { SdkEventBus } from "../events";
import { HEIRecord } from "../models";
import {
  HEIAzureDevOpsService, HEIContextService, HEIExecutionService, HEIMemoryService,
  HEIPlanningService, HEIPlatformService, HEIPromptService, HEIQAService,
  HEIRepositoryService, HEIRuntimeService, HEIValidationService
} from "../services/PlatformServices";
import { ITransport } from "../transport/ITransport";
import { RestTransport } from "../transport/RestTransport";
import { VersionCompatibilityException } from "./errors";
import { IHEISdk } from "./IHEISdk";
import { PlatformGateway } from "./PlatformGateway";

export interface HEISdkDependencies {
  transport?: ITransport;
  authentication?: IAuthenticationProvider;
  cache?: ISdkCache;
  diagnostics?: IDiagnosticsSink;
  telemetry?: ITelemetrySink;
  events?: SdkEventBus;
}

export class HEISdk implements IHEISdk {
  readonly configuration: Readonly<ResolvedSdkConfiguration>;
  readonly events: SdkEventBus;
  readonly diagnostics: IDiagnosticsSink;
  readonly cache: ISdkCache;
  readonly planning: HEIPlanningService;
  readonly repository: HEIRepositoryService;
  readonly context: HEIContextService;
  readonly execution: HEIExecutionService;
  readonly prompt: HEIPromptService;
  readonly runtime: HEIRuntimeService;
  readonly validation: HEIValidationService;
  readonly qa: HEIQAService;
  readonly memory: HEIMemoryService;
  readonly azureDevOps: HEIAzureDevOpsService;
  readonly platform: HEIPlatformService;

  constructor(configuration: SdkConfiguration, dependencies: HEISdkDependencies = {}) {
    this.configuration = Object.freeze(resolveConfiguration(configuration));
    this.events = dependencies.events ?? new SdkEventBus();
    this.diagnostics = dependencies.diagnostics ?? new MemoryDiagnosticsSink();
    this.cache = dependencies.cache ?? new MemorySdkCache();
    const gateway = new PlatformGateway(
      this.configuration,
      dependencies.transport ?? new RestTransport(this.configuration.baseUrl),
      dependencies.authentication ?? new AnonymousAuthenticationProvider(),
      this.cache,
      this.diagnostics,
      dependencies.telemetry ?? new NoopTelemetrySink(),
      this.events
    );
    this.planning = new HEIPlanningService(gateway);
    this.repository = new HEIRepositoryService(gateway);
    this.context = new HEIContextService(gateway);
    this.execution = new HEIExecutionService(gateway);
    this.prompt = new HEIPromptService(gateway);
    this.runtime = new HEIRuntimeService(gateway);
    this.validation = new HEIValidationService(gateway);
    this.qa = new HEIQAService(gateway);
    this.memory = new HEIMemoryService(gateway);
    this.azureDevOps = new HEIAzureDevOpsService(gateway);
    this.platform = new HEIPlatformService(gateway);
  }

  async initialize(): Promise<void> {
    const health = await this.platform.getHealth({ bypassCache: true });
    assertVersionCompatibility(this.configuration.sdkVersion, health.data as HEIRecord);
  }

  invalidateCache(scope?: string): number {
    return this.cache.invalidate(scope ? key => key.startsWith(`${scope}.`) : undefined);
  }
}

export function assertVersionCompatibility(sdkVersion: string, platform: HEIRecord): void {
  const minimum = String(platform.minimumSdkVersion ?? platform.minimum_sdk_version ?? "");
  const supported = platform.supportedSdkMajor ?? platform.supported_sdk_major;
  const sdkMajor = Number(sdkVersion.split(".")[0]);
  if ((minimum && compareVersions(sdkVersion, minimum) < 0) || (supported !== undefined && Number(supported) !== sdkMajor)) {
    throw new VersionCompatibilityException(`HEI SDK ${sdkVersion} is not compatible with this platform.`, { minimumSdkVersion: minimum, supportedSdkMajor: supported });
  }
}

function compareVersions(left: string, right: string): number {
  const a = left.split(".").map(Number); const b = right.split(".").map(Number);
  for (let index = 0; index < Math.max(a.length, b.length); index += 1) {
    if ((a[index] ?? 0) !== (b[index] ?? 0)) return (a[index] ?? 0) - (b[index] ?? 0);
  }
  return 0;
}
