import { PlatformGateway } from "../core/PlatformGateway";
import { HEIRecord, RepositoryRegistration, RequestContext } from "../models";
import {
  IHEIAzureDevOpsService, IHEIContextService, IHEIExecutionService, IHEIMemoryService,
  IHEIPlanningService, IHEIPlatformService, IHEIPromptService, IHEIQAService,
  IHEIRepositoryService, IHEIRuntimeService, IHEIValidationService
} from "./contracts";

class ServiceBase {
  constructor(protected readonly gateway: PlatformGateway) {}
  protected call<T = HEIRecord>(operation: string, input: HEIRecord = {}, context?: RequestContext) {
    return this.gateway.execute<T>(operation, input, context);
  }
}

export class HEIPlanningService extends ServiceBase implements IHEIPlanningService {
  analyzeRequirement(input: HEIRecord, context?: RequestContext) { return this.call("planning.analyzeRequirement", input, context); }
  createEpic(input: HEIRecord, context?: RequestContext) { return this.call("planning.createEpic", input, context); }
  createFeature(input: HEIRecord, context?: RequestContext) { return this.call("planning.createFeature", input, context); }
  createStory(input: HEIRecord, context?: RequestContext) { return this.call("planning.createStory", input, context); }
  createTask(input: HEIRecord, context?: RequestContext) { return this.call("planning.createTask", input, context); }
  estimateStory(input: HEIRecord, context?: RequestContext) { return this.call("planning.estimateStory", input, context); }
  buildPlanningPackage(input: HEIRecord, context?: RequestContext) { return this.call("planning.buildPackage", input, context); }
}

export class HEIRepositoryService extends ServiceBase implements IHEIRepositoryService {
  registerRepository(input: RepositoryRegistration, context?: RequestContext) { return this.call("repository.register", { ...input }, context); }
  listRepositories(context?: RequestContext) { return this.call<HEIRecord[]>("repository.list", {}, context); }
  getRepository(repositoryId: string, context?: RequestContext) { return this.call("repository.get", { repositoryId }, context); }
  synchronize(repositoryId: string, input: HEIRecord = {}, context?: RequestContext) { return this.call("repository.synchronize", { ...input, repositoryId }, context); }
  getSnapshot(repositoryId: string, context?: RequestContext) { return this.call("repository.snapshot", { repositoryId }, context); }
  getEngineeringGraph(repositoryId: string, context?: RequestContext) { return this.call("repository.graph", { repositoryId }, context); }
  searchFiles(repositoryId: string, input: HEIRecord, context?: RequestContext) { return this.call("repository.searchFiles", { ...input, repositoryId }, context); }
  searchSymbols(repositoryId: string, query: string, context?: RequestContext) { return this.call("repository.searchSymbols", { repositoryId, query }, context); }
  getRepositoryHealth(repositoryId: string, context?: RequestContext) { return this.call("repository.health", { repositoryId }, context); }
}

export class HEIContextService extends ServiceBase implements IHEIContextService {
  buildContextCapsule(input: HEIRecord, context?: RequestContext) { return this.call("context.build", input, context); }
  getContextCapsule(capsuleId: string, context?: RequestContext) { return this.call("context.get", { capsuleId }, context); }
  searchContext(input: HEIRecord, context?: RequestContext) { return this.call("context.search", input, context); }
  validateContext(capsuleId: string, context?: RequestContext) { return this.call("context.validate", { capsuleId }, context); }
}

export class HEIExecutionService extends ServiceBase implements IHEIExecutionService {
  buildExecutionPackage(input: HEIRecord, context?: RequestContext) { return this.call("execution.buildPackage", input, context); }
  getExecutionPackage(packageId: string, context?: RequestContext) { return this.call("execution.getPackage", { packageId }, context); }
  buildExecutionPlan(packageId: string, input: HEIRecord = {}, context?: RequestContext) { return this.call("execution.buildPlan", { ...input, packageId }, context); }
  getExecutionReadiness(packageId: string, context?: RequestContext) { return this.call("execution.readiness", { packageId }, context); }
}

export class HEIPromptService extends ServiceBase implements IHEIPromptService {
  compilePrompt(input: HEIRecord, context?: RequestContext) { return this.call("prompt.compile", input, context); }
  optimizePrompt(input: HEIRecord, context?: RequestContext) { return this.call("prompt.optimize", input, context); }
  estimateTokens(input: HEIRecord, context?: RequestContext) { return this.call("prompt.estimateTokens", input, context); }
  generateExecutionPrompt(input: HEIRecord, context?: RequestContext) { return this.call("prompt.generate", input, context); }
  selectProvider(input: HEIRecord, context?: RequestContext) { return this.call("prompt.selectProvider", input, context); }
  getModels(context?: RequestContext) { return this.call<HEIRecord[]>("prompt.models", {}, context); }
}

export class HEIRuntimeService extends ServiceBase implements IHEIRuntimeService {
  startExecution(input: HEIRecord, context?: RequestContext) { return this.call("runtime.start", input, context); }
  submitResponse(sessionId: string, input: HEIRecord, context?: RequestContext) { return this.call("runtime.submitResponse", { ...input, sessionId }, context); }
  getExecutionStatus(sessionId: string, context?: RequestContext) { return this.call("runtime.status", { sessionId }, context); }
  getExecutionTrace(traceId: string, context?: RequestContext) { return this.call("runtime.trace", { traceId }, context); }
  retryExecution(sessionId: string, input: HEIRecord = {}, context?: RequestContext) { return this.call("runtime.retry", { ...input, sessionId }, context); }
}

export class HEIValidationService extends ServiceBase implements IHEIValidationService {
  validateImplementation(input: HEIRecord, context?: RequestContext) { return this.call("validation.implementation", input, context); }
  compareAcceptance(input: HEIRecord, context?: RequestContext) { return this.call("validation.acceptance", input, context); }
  architectureValidation(input: HEIRecord, context?: RequestContext) { return this.call("validation.architecture", input, context); }
  regressionValidation(input: HEIRecord, context?: RequestContext) { return this.call("validation.regression", input, context); }
}

export class HEIQAService extends ServiceBase implements IHEIQAService {
  generateTests(input: HEIRecord, context?: RequestContext) { return this.call("qa.generateTests", input, context); }
  generateRegression(input: HEIRecord, context?: RequestContext) { return this.call("qa.regression", input, context); }
  generateReleaseReadiness(input: HEIRecord, context?: RequestContext) { return this.call("qa.releaseReadiness", input, context); }
}

export class HEIMemoryService extends ServiceBase implements IHEIMemoryService {
  searchMemory(input: HEIRecord, context?: RequestContext) { return this.call<HEIRecord[]>("memory.search", input, context); }
  createCandidate(input: HEIRecord, context?: RequestContext) { return this.call("memory.createCandidate", input, context); }
  approveMemory(memoryId: string, input: HEIRecord = {}, context?: RequestContext) { return this.call("memory.approve", { ...input, memoryId }, context); }
  rejectMemory(memoryId: string, input: HEIRecord = {}, context?: RequestContext) { return this.call("memory.reject", { ...input, memoryId }, context); }
  suggestReuse(input: HEIRecord, context?: RequestContext) { return this.call<HEIRecord[]>("memory.suggestReuse", input, context); }
}

export class HEIAzureDevOpsService extends ServiceBase implements IHEIAzureDevOpsService {
  registerConnection(input: HEIRecord, context?: RequestContext) { return this.call("azureDevOps.registerConnection", input, context); }
  listConnections(context?: RequestContext) { return this.call("azureDevOps.listConnections", {}, context); }
  getConnection(connectionId: string, context?: RequestContext) { return this.call("azureDevOps.getConnection", { connectionId }, context); }
  validateConnection(connectionId: string, context?: RequestContext) { return this.call("azureDevOps.validateConnection", { connectionId }, context); }
  getConnectionHealth(connectionId: string, context?: RequestContext) { return this.call("azureDevOps.connectionHealth", { connectionId }, context); }
  listOrganizations(connectionId: string, context?: RequestContext) { return this.call("azureDevOps.listOrganizations", { connectionId }, context); }
  listProjects(connectionId: string, context?: RequestContext) { return this.call("azureDevOps.listProjects", { connectionId }, context); }
  getProject(connectionId: string, projectId: string, context?: RequestContext) { return this.call("azureDevOps.getProject", { connectionId, projectId }, context); }
  listTeams(connectionId: string, projectId: string, context?: RequestContext) { return this.call("azureDevOps.listTeams", { connectionId, projectId }, context); }
  listIterations(connectionId: string, project: string, context?: RequestContext) { return this.call("azureDevOps.listIterations", { connectionId, project }, context); }
  getCurrentSprint(connectionId: string, project: string, context?: RequestContext) { return this.call("azureDevOps.currentSprint", { connectionId, project }, context); }
  queryWorkItems(connectionId: string, input: HEIRecord, context?: RequestContext) { return this.call("azureDevOps.queryWorkItems", { ...input, connectionId }, context); }
  getWorkItemHierarchy(connectionId: string, project: string, workItemId: number, context?: RequestContext) { return this.call("azureDevOps.workItemHierarchy", { connectionId, project, workItemId }, context); }
  getWorkItemRevisions(connectionId: string, project: string, workItemId: number, context?: RequestContext) { return this.call("azureDevOps.workItemRevisions", { connectionId, project, workItemId }, context); }
  listRepositories(connectionId: string, project: string, context?: RequestContext) { return this.call("azureDevOps.listRepositories", { connectionId, project }, context); }
  getRepository(connectionId: string, project: string, repositoryId: string, context?: RequestContext) { return this.call("azureDevOps.getRepository", { connectionId, project, repositoryId }, context); }
  listPullRequests(connectionId: string, project: string, repositoryId = "", context?: RequestContext) { return this.call("azureDevOps.listPullRequests", { connectionId, project, repositoryId }, context); }
  getPullRequest(connectionId: string, project: string, repositoryId: string, pullRequestId: number, context?: RequestContext) { return this.call("azureDevOps.getPullRequest", { connectionId, project, repositoryId, pullRequestId }, context); }
  listBuilds(connectionId: string, project: string, context?: RequestContext) { return this.call("azureDevOps.listBuilds", { connectionId, project }, context); }
  syncProject(connectionId: string, projectId: string, syncType = "ManualSync", context?: RequestContext) { return this.call("azureDevOps.syncProject", { connectionId, projectId, syncType }, context); }
  getSyncStatus(projectId: string, context?: RequestContext) { return this.call("azureDevOps.syncStatus", { projectId }, context); }
  getSyncHistory(projectId: string, context?: RequestContext) { return this.call("azureDevOps.syncHistory", { projectId }, context); }
  receiveWebhook(input: HEIRecord, context?: RequestContext) { return this.call("azureDevOps.receiveWebhook", input, context); }
  reconcileProject(connectionId: string, projectId: string, context?: RequestContext) { return this.call("azureDevOps.reconcileProject", { connectionId, projectId }, context); }
  listAgentRuns(context?: RequestContext) { return this.call("azureDevOps.agentRuns", {}, context); }
  getAgentRun(runId: string, context?: RequestContext) { return this.call("azureDevOps.agentRun", { runId }, context); }
  listActionPacks(context?: RequestContext) { return this.call("azureDevOps.actionPacks", {}, context); }
  getActionPack(packId: string, context?: RequestContext) { return this.call("azureDevOps.actionPack", { packId }, context); }
  approveActionPack(packId: string, input: HEIRecord, context?: RequestContext) { return this.call("azureDevOps.approveActionPack", { ...input, packId }, context); }
  rejectActionPack(packId: string, input: HEIRecord, context?: RequestContext) { return this.call("azureDevOps.rejectActionPack", { ...input, packId }, context); }
  applyActionPack(packId: string, input: HEIRecord, context?: RequestContext) { return this.call("azureDevOps.applyActionPack", { ...input, packId }, context); }
  analyzeWorkItem(input: HEIRecord, context?: RequestContext) { return this.call("azureDevOps.analyzeWorkItem", input, context); }
  suggestStories(input: HEIRecord, context?: RequestContext) { return this.call("azureDevOps.suggestStories", input, context); }
  analyzeSprint(input: HEIRecord, context?: RequestContext) { return this.call("azureDevOps.analyzeSprint", input, context); }
  generatePRSummary(input: HEIRecord, context?: RequestContext) { return this.call("azureDevOps.generatePRSummary", input, context); }
}

export class HEIPlatformService extends ServiceBase implements IHEIPlatformService {
  getHealth(context?: RequestContext) { return this.call("platform.health", {}, context); }
  getRecentActivity(limit = 20, context?: RequestContext) { return this.call("platform.activity", { limit }, context); }
  getCapabilities(context?: RequestContext) { return this.call("platform.capabilities", {}, context); }
}
