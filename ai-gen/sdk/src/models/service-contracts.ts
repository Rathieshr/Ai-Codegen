import { ContextCapsule, ExecutionManifest, HEIRecord } from ".";

export interface AnalyzeRequirementRequest extends HEIRecord {
  title?: string;
  description: string;
  projectId?: string;
  repositoryId?: string;
}

export interface PlanningArtifactRequest extends HEIRecord {
  title: string;
  description?: string;
  parentId?: string | number;
  acceptanceCriteria?: string[];
  projectId?: string;
}

export interface ContextCapsuleBuildRequest extends HEIRecord {
  artifact: HEIRecord;
  parentArtifact?: HEIRecord;
  repositorySnapshotVersion?: string;
  knowledgeVersion?: string;
}

export interface ExecutionPackageBuildRequest extends HEIRecord {
  contextCapsule: ContextCapsule;
  executionRequest?: HEIRecord;
  correlationId?: string;
}

export interface PromptCompileRequest extends HEIRecord {
  executionManifest?: ExecutionManifest;
  executionManifestId?: string;
  correlationId?: string;
}

export interface PromptOptimizationRequest extends HEIRecord {
  compiledPrompt?: HEIRecord;
  compiledPromptId?: string;
  budgetTokens?: number;
  reservedOutputTokens?: number;
  actualTokens?: number;
  correlationId?: string;
}

export interface ProviderSelectionRequest extends HEIRecord {
  executionManifest?: ExecutionManifest;
  executionManifestId?: string;
  executionMode?: string;
  repositoryMode?: string;
  targetTask?: HEIRecord;
  userPreference?: string;
  availableModels?: string[];
  correlationId?: string;
}

export interface RuntimeStartRequest extends HEIRecord {
  executionPrompt: HEIRecord | string;
  executionPlanVersion: string;
  executionPackageVersion: string;
  repositorySnapshotVersion?: string;
  provider: string;
  model: string;
  correlationId?: string;
  idempotencyKey?: string;
}

export interface RuntimeResponseRequest extends HEIRecord {
  providerResponse: unknown;
  metadata?: HEIRecord;
}

export interface ValidationRequest extends HEIRecord {
  executionPackage: HEIRecord;
  changedFiles?: HEIRecord[];
  repositoryDiff?: HEIRecord;
  testResults?: HEIRecord;
}

export interface QARequest extends HEIRecord {
  executionPackage: HEIRecord;
  validationResult?: HEIRecord;
  engineeringDiff?: HEIRecord;
}

export interface MemorySearchRequest extends HEIRecord {
  query: string;
  projectId?: string;
  categories?: string[];
  modules?: string[];
  limit?: number;
}

export interface AzureDevOpsWorkItemRequest extends HEIRecord {
  id: number;
  workItemType: string;
  title: string;
  description?: string;
  acceptanceCriteria?: string[];
  projectId?: string;
}

export interface AzureDevOpsConnectionRegistration extends HEIRecord {
  organizationUrl: string;
  organizationName?: string;
  projectId?: string;
  projectName?: string;
  authenticationMode: "PAT" | "OAuth" | "ManagedIdentity";
  secretReference: string;
  permissions?: string[];
}

export interface AzureDevOpsWIQLRequest extends HEIRecord {
  project: string;
  query: string;
}
