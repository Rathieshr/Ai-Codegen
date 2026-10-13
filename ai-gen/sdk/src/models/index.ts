export type HEIRecord = Record<string, unknown>;

export interface RequestContext {
  correlationId?: string;
  executionPackageVersion?: string;
  repositorySnapshotVersion?: string;
  contextCapsuleVersion?: string;
  knowledgeVersion?: string;
  memoryVersion?: string;
  bypassCache?: boolean;
}

export interface OperationResult<T> {
  data: T;
  diagnostics: RequestDiagnostics;
}

export interface RequestDiagnostics {
  operation: string;
  correlationId: string;
  sdkVersion: string;
  platformVersion?: string;
  durationMs: number;
  retries: number;
  cacheStatus: "hit" | "miss" | "bypass" | "disabled";
  transport: string;
  warnings: string[];
  errors: string[];
  versions: Record<string, string>;
}

export interface RepositoryRegistration {
  name: string;
  url: string;
  defaultBranch: string;
  repositoryType: "AzureDevOps" | "GitHub";
  authenticationType: string;
}

export interface RepositorySummary extends HEIRecord {
  id?: string;
  name?: string;
  status?: string;
}

export interface ContextCapsule extends HEIRecord { capsuleId?: string; }
export interface ExecutionPackage extends HEIRecord { packageId?: string; }
export interface ExecutionManifest extends HEIRecord { manifestId?: string; }
export interface ExecutionSession extends HEIRecord { sessionId?: string; status?: string; }
export interface MemoryItem extends HEIRecord { id?: string; approvalStatus?: string; }
export interface ModelProfile extends HEIRecord { id?: string; provider?: string; }

export interface StreamRequest<T = HEIRecord> {
  operation: string;
  input: T;
  context?: RequestContext;
}

export * from "./service-contracts";
