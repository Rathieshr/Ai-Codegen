import {
  ContextCapsule, ExecutionPackage, ExecutionSession, HEIRecord, MemoryItem,
  ModelProfile, OperationResult, RepositoryRegistration, RepositorySummary, RequestContext,
  AnalyzeRequirementRequest, PlanningArtifactRequest, ContextCapsuleBuildRequest,
  ExecutionPackageBuildRequest, PromptCompileRequest, PromptOptimizationRequest,
  ProviderSelectionRequest, RuntimeStartRequest, RuntimeResponseRequest,
  ValidationRequest, QARequest, MemorySearchRequest, AzureDevOpsWorkItemRequest,
  AzureDevOpsConnectionRegistration, AzureDevOpsWIQLRequest
} from "../models";

export type Result<T = HEIRecord> = Promise<OperationResult<T>>;

export interface IHEIPlanningService {
  analyzeRequirement(input: AnalyzeRequirementRequest, context?: RequestContext): Result;
  createEpic(input: PlanningArtifactRequest, context?: RequestContext): Result;
  createFeature(input: PlanningArtifactRequest, context?: RequestContext): Result;
  createStory(input: PlanningArtifactRequest, context?: RequestContext): Result;
  createTask(input: PlanningArtifactRequest, context?: RequestContext): Result;
  estimateStory(input: PlanningArtifactRequest, context?: RequestContext): Result;
  buildPlanningPackage(input: HEIRecord, context?: RequestContext): Result;
}

export interface IHEIRepositoryService {
  registerRepository(input: RepositoryRegistration, context?: RequestContext): Result<RepositorySummary>;
  listRepositories(context?: RequestContext): Result<RepositorySummary[]>;
  getRepository(repositoryId: string, context?: RequestContext): Result<RepositorySummary>;
  synchronize(repositoryId: string, input?: HEIRecord, context?: RequestContext): Result;
  getSnapshot(repositoryId: string, context?: RequestContext): Result;
  getEngineeringGraph(repositoryId: string, context?: RequestContext): Result;
  searchFiles(repositoryId: string, input: HEIRecord, context?: RequestContext): Result;
  searchSymbols(repositoryId: string, query: string, context?: RequestContext): Result;
  getRepositoryHealth(repositoryId: string, context?: RequestContext): Result;
}

export interface IHEIContextService {
  buildContextCapsule(input: ContextCapsuleBuildRequest, context?: RequestContext): Result<ContextCapsule>;
  getContextCapsule(capsuleId: string, context?: RequestContext): Result<ContextCapsule>;
  searchContext(input: HEIRecord, context?: RequestContext): Result;
  validateContext(capsuleId: string, context?: RequestContext): Result;
}

export interface IHEIExecutionService {
  buildExecutionPackage(input: ExecutionPackageBuildRequest, context?: RequestContext): Result<ExecutionPackage>;
  getExecutionPackage(packageId: string, context?: RequestContext): Result<ExecutionPackage>;
  buildExecutionPlan(packageId: string, input?: HEIRecord, context?: RequestContext): Result;
  getExecutionReadiness(packageId: string, context?: RequestContext): Result;
}

export interface IHEIPromptService {
  compilePrompt(input: PromptCompileRequest, context?: RequestContext): Result;
  optimizePrompt(input: PromptOptimizationRequest, context?: RequestContext): Result;
  estimateTokens(input: PromptOptimizationRequest, context?: RequestContext): Result;
  generateExecutionPrompt(input: ProviderSelectionRequest, context?: RequestContext): Result;
  selectProvider(input: ProviderSelectionRequest, context?: RequestContext): Result;
  getModels(context?: RequestContext): Result<ModelProfile[]>;
}

export interface IHEIRuntimeService {
  startExecution(input: RuntimeStartRequest, context?: RequestContext): Result<ExecutionSession>;
  submitResponse(sessionId: string, input: RuntimeResponseRequest, context?: RequestContext): Result<ExecutionSession>;
  getExecutionStatus(sessionId: string, context?: RequestContext): Result<ExecutionSession>;
  getExecutionTrace(traceId: string, context?: RequestContext): Result;
  retryExecution(sessionId: string, input?: HEIRecord, context?: RequestContext): Result<ExecutionSession>;
}

export interface IHEIValidationService {
  validateImplementation(input: ValidationRequest, context?: RequestContext): Result;
  compareAcceptance(input: HEIRecord, context?: RequestContext): Result;
  architectureValidation(input: HEIRecord, context?: RequestContext): Result;
  regressionValidation(input: HEIRecord, context?: RequestContext): Result;
}

export interface IHEIQAService {
  generateTests(input: QARequest, context?: RequestContext): Result;
  generateRegression(input: QARequest, context?: RequestContext): Result;
  generateReleaseReadiness(input: QARequest, context?: RequestContext): Result;
}

export interface IHEIMemoryService {
  searchMemory(input: MemorySearchRequest, context?: RequestContext): Result<MemoryItem[]>;
  createCandidate(input: HEIRecord, context?: RequestContext): Result<MemoryItem>;
  approveMemory(memoryId: string, input?: HEIRecord, context?: RequestContext): Result<MemoryItem>;
  rejectMemory(memoryId: string, input?: HEIRecord, context?: RequestContext): Result<MemoryItem>;
  suggestReuse(input: HEIRecord, context?: RequestContext): Result<MemoryItem[]>;
}

export interface IHEIAzureDevOpsService {
  registerConnection(input: AzureDevOpsConnectionRegistration, context?: RequestContext): Result;
  listConnections(context?: RequestContext): Result;
  getConnection(connectionId: string, context?: RequestContext): Result;
  validateConnection(connectionId: string, context?: RequestContext): Result;
  getConnectionHealth(connectionId: string, context?: RequestContext): Result;
  listOrganizations(connectionId: string, context?: RequestContext): Result;
  listProjects(connectionId: string, context?: RequestContext): Result;
  getProject(connectionId: string, projectId: string, context?: RequestContext): Result;
  listTeams(connectionId: string, projectId: string, context?: RequestContext): Result;
  listIterations(connectionId: string, project: string, context?: RequestContext): Result;
  getCurrentSprint(connectionId: string, project: string, context?: RequestContext): Result;
  queryWorkItems(connectionId: string, input: AzureDevOpsWIQLRequest, context?: RequestContext): Result;
  getWorkItemHierarchy(connectionId: string, project: string, workItemId: number, context?: RequestContext): Result;
  getWorkItemRevisions(connectionId: string, project: string, workItemId: number, context?: RequestContext): Result;
  listRepositories(connectionId: string, project: string, context?: RequestContext): Result;
  getRepository(connectionId: string, project: string, repositoryId: string, context?: RequestContext): Result;
  listPullRequests(connectionId: string, project: string, repositoryId?: string, context?: RequestContext): Result;
  getPullRequest(connectionId: string, project: string, repositoryId: string, pullRequestId: number, context?: RequestContext): Result;
  listBuilds(connectionId: string, project: string, context?: RequestContext): Result;
  syncProject(connectionId: string, projectId: string, syncType?: string, context?: RequestContext): Result;
  getSyncStatus(projectId: string, context?: RequestContext): Result;
  getSyncHistory(projectId: string, context?: RequestContext): Result;
  receiveWebhook(input: HEIRecord, context?: RequestContext): Result;
  reconcileProject(connectionId: string, projectId: string, context?: RequestContext): Result;
  listAgentRuns(context?: RequestContext): Result;
  getAgentRun(runId: string, context?: RequestContext): Result;
  listActionPacks(context?: RequestContext): Result;
  getActionPack(packId: string, context?: RequestContext): Result;
  approveActionPack(packId: string, input: HEIRecord, context?: RequestContext): Result;
  rejectActionPack(packId: string, input: HEIRecord, context?: RequestContext): Result;
  applyActionPack(packId: string, input: HEIRecord, context?: RequestContext): Result;
  /** @deprecated Use the read-only integration methods above. */
  analyzeWorkItem(input: AzureDevOpsWorkItemRequest, context?: RequestContext): Result;
  suggestStories(input: HEIRecord, context?: RequestContext): Result;
  analyzeSprint(input: HEIRecord, context?: RequestContext): Result;
  generatePRSummary(input: HEIRecord, context?: RequestContext): Result;
}

export interface IHEIPlatformService {
  getHealth(context?: RequestContext): Result;
  getRecentActivity(limit?: number, context?: RequestContext): Result;
  getCapabilities(context?: RequestContext): Result;
}
