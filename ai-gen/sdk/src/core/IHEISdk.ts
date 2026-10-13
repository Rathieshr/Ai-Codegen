import { ISdkCache } from "../cache";
import { ResolvedSdkConfiguration } from "../configuration/SdkConfiguration";
import { IDiagnosticsSink } from "../diagnostics";
import { SdkEventBus } from "../events";
import {
  IHEIAzureDevOpsService, IHEIContextService, IHEIExecutionService, IHEIMemoryService,
  IHEIPlanningService, IHEIPlatformService, IHEIPromptService, IHEIQAService,
  IHEIRepositoryService, IHEIRuntimeService, IHEIValidationService
} from "../services/contracts";

export interface IHEISdk {
  readonly configuration: Readonly<ResolvedSdkConfiguration>;
  readonly planning: IHEIPlanningService;
  readonly repository: IHEIRepositoryService;
  readonly context: IHEIContextService;
  readonly execution: IHEIExecutionService;
  readonly prompt: IHEIPromptService;
  readonly runtime: IHEIRuntimeService;
  readonly validation: IHEIValidationService;
  readonly qa: IHEIQAService;
  readonly memory: IHEIMemoryService;
  readonly azureDevOps: IHEIAzureDevOpsService;
  readonly platform: IHEIPlatformService;
  readonly events: SdkEventBus;
  readonly diagnostics: IDiagnosticsSink;
  readonly cache: ISdkCache;
  initialize(): Promise<void>;
  invalidateCache(scope?: string): number;
}
