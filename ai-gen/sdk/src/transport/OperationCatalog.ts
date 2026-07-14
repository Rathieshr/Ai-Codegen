export type PathInput = Record<string, unknown>;
export interface OperationDefinition {
  method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  path: string | ((input: PathInput) => string);
  cacheable?: boolean;
  queryFields?: string[];
  bodyFields?: string[];
}

const id = (input: PathInput, key: string): string => encodeURIComponent(String(input[key] ?? ""));

export const OPERATION_CATALOG: Record<string, OperationDefinition> = {
  "planning.analyzeRequirement": { method: "POST", path: "/project-intelligence/analyze-description" },
  "planning.createEpic": { method: "POST", path: "/story-planner/sessions" },
  "planning.createFeature": { method: "POST", path: "/project-intelligence/refine-feature" },
  "planning.createStory": { method: "POST", path: "/project-intelligence/refine-story" },
  "planning.createTask": { method: "POST", path: "/assist/pipeline/create" },
  "planning.estimateStory": { method: "POST", path: "/project-intelligence/analyze-story-impact" },
  "planning.buildPackage": { method: "POST", path: "/assist/pipeline/create" },

  "repository.register": { method: "POST", path: "/repositories" },
  "repository.list": { method: "GET", path: "/repositories", cacheable: true },
  "repository.get": { method: "GET", path: input => `/repositories/${id(input, "repositoryId")}`, cacheable: true },
  "repository.synchronize": { method: "POST", path: input => `/repositories/${id(input, "repositoryId")}/scan` },
  "repository.snapshot": { method: "GET", path: input => `/repositories/${id(input, "repositoryId")}/snapshots/current`, cacheable: true },
  "repository.graph": { method: "GET", path: input => `/repositories/${id(input, "repositoryId")}/graph`, cacheable: true },
  "repository.searchFiles": { method: "POST", path: input => `/repositories/${id(input, "repositoryId")}/file-ranking` },
  "repository.searchSymbols": { method: "GET", path: input => `/repositories/${id(input, "repositoryId")}/symbols`, cacheable: true, queryFields: ["query"] },
  "repository.health": { method: "GET", path: input => `/repositories/${id(input, "repositoryId")}/monitoring`, cacheable: true },

  "context.build": { method: "POST", path: "/context/orchestrate" },
  "context.get": { method: "GET", path: input => `/context/requests/${id(input, "capsuleId")}`, cacheable: true },
  "context.search": { method: "POST", path: "/context" },
  "context.validate": { method: "GET", path: input => `/context/requests/${id(input, "capsuleId")}/diagnostics`, cacheable: true },

  "execution.buildPackage": { method: "POST", path: "/execution-packages/build" },
  "execution.getPackage": { method: "GET", path: input => `/execution-packages/${id(input, "packageId")}`, cacheable: true },
  "execution.buildPlan": { method: "POST", path: input => `/execution-packages/${id(input, "packageId")}/consume/ImplementationPlan` },
  "execution.readiness": { method: "GET", path: input => `/execution-packages/${id(input, "packageId")}`, cacheable: true },

  "prompt.compile": { method: "POST", path: "/prompt-compiler/compile" },
  "prompt.optimize": { method: "POST", path: "/token-intelligence/optimize" },
  "prompt.estimateTokens": { method: "POST", path: "/token-intelligence/optimize" },
  "prompt.generate": { method: "POST", path: "/provider-router/route" },
  "prompt.selectProvider": { method: "POST", path: "/provider-router/route" },
  "prompt.models": { method: "GET", path: "/models", cacheable: true },

  "runtime.start": { method: "POST", path: "/execution-runtime/start" },
  "runtime.submitResponse": { method: "POST", path: input => `/execution-runtime/${id(input, "sessionId")}/response` },
  "runtime.status": { method: "GET", path: input => `/execution-runtime/${id(input, "sessionId")}`, cacheable: true },
  "runtime.trace": { method: "GET", path: input => `/runtime/traces/${id(input, "traceId")}`, cacheable: true },
  "runtime.retry": { method: "POST", path: input => `/execution-runtime/${id(input, "sessionId")}/retry` },

  "validation.implementation": { method: "POST", path: "/project-intelligence/validate-implementation" },
  "validation.acceptance": { method: "POST", path: "/validation-trigger/evaluate" },
  "validation.architecture": { method: "POST", path: "/validation-trigger/evaluate" },
  "validation.regression": { method: "POST", path: "/engineering-diff" },

  "qa.generateTests": { method: "POST", path: "/project-intelligence/generate-qa-test-cases" },
  "qa.regression": { method: "POST", path: "/qa-trigger/evaluate" },
  "qa.releaseReadiness": { method: "POST", path: "/qa-trigger/evaluate" },

  "memory.search": { method: "POST", path: "/project-intelligence/engineering-memory/search" },
  "memory.createCandidate": { method: "POST", path: "/memory-candidates/generate" },
  "memory.approve": { method: "POST", path: input => `/memory-candidates/${id(input, "memoryId")}/approve` },
  "memory.reject": { method: "POST", path: input => `/memory-candidates/${id(input, "memoryId")}/reject` },
  "memory.suggestReuse": { method: "POST", path: "/project-intelligence/engineering-memory/relevant" },

  "azureDevOps.registerConnection": { method: "POST", path: "/integrations/azure-devops/connections" },
  "azureDevOps.listConnections": { method: "GET", path: "/integrations/azure-devops/connections", cacheable: true },
  "azureDevOps.getConnection": { method: "GET", path: input => `/integrations/azure-devops/connections/${id(input, "connectionId")}`, cacheable: true },
  "azureDevOps.validateConnection": { method: "POST", path: input => `/integrations/azure-devops/connections/${id(input, "connectionId")}/validate` },
  "azureDevOps.connectionHealth": { method: "GET", path: input => `/integrations/azure-devops/connections/${id(input, "connectionId")}/health`, cacheable: true },
  "azureDevOps.listOrganizations": { method: "GET", path: input => `/integrations/azure-devops/connections/${id(input, "connectionId")}/organizations`, cacheable: true },
  "azureDevOps.listProjects": { method: "GET", path: input => `/integrations/azure-devops/connections/${id(input, "connectionId")}/projects`, cacheable: true },
  "azureDevOps.getProject": { method: "GET", path: input => `/integrations/azure-devops/connections/${id(input, "connectionId")}/projects/${id(input, "projectId")}`, cacheable: true },
  "azureDevOps.listTeams": { method: "GET", path: input => `/integrations/azure-devops/connections/${id(input, "connectionId")}/projects/${id(input, "projectId")}/teams`, cacheable: true },
  "azureDevOps.listIterations": { method: "GET", path: input => `/integrations/azure-devops/connections/${id(input, "connectionId")}/projects/${id(input, "project")}/iterations`, cacheable: true },
  "azureDevOps.currentSprint": { method: "GET", path: input => `/integrations/azure-devops/connections/${id(input, "connectionId")}/projects/${id(input, "project")}/iterations/current`, cacheable: true },
  "azureDevOps.queryWorkItems": { method: "POST", path: input => `/integrations/azure-devops/connections/${id(input, "connectionId")}/work-items/query` },
  "azureDevOps.workItemHierarchy": { method: "GET", path: input => `/integrations/azure-devops/connections/${id(input, "connectionId")}/projects/${id(input, "project")}/work-items/${id(input, "workItemId")}/hierarchy`, cacheable: true },
  "azureDevOps.workItemRevisions": { method: "GET", path: input => `/integrations/azure-devops/connections/${id(input, "connectionId")}/projects/${id(input, "project")}/work-items/${id(input, "workItemId")}/revisions`, cacheable: true },
  "azureDevOps.listRepositories": { method: "GET", path: input => `/integrations/azure-devops/connections/${id(input, "connectionId")}/projects/${id(input, "project")}/repositories`, cacheable: true },
  "azureDevOps.getRepository": { method: "GET", path: input => `/integrations/azure-devops/connections/${id(input, "connectionId")}/projects/${id(input, "project")}/repositories/${id(input, "repositoryId")}`, cacheable: true },
  "azureDevOps.listPullRequests": { method: "GET", path: input => `/integrations/azure-devops/connections/${id(input, "connectionId")}/projects/${id(input, "project")}/pull-requests`, cacheable: true, queryFields: ["repositoryId"] },
  "azureDevOps.getPullRequest": { method: "GET", path: input => `/integrations/azure-devops/connections/${id(input, "connectionId")}/projects/${id(input, "project")}/repositories/${id(input, "repositoryId")}/pull-requests/${id(input, "pullRequestId")}`, cacheable: true },
  "azureDevOps.listBuilds": { method: "GET", path: input => `/integrations/azure-devops/connections/${id(input, "connectionId")}/projects/${id(input, "project")}/builds`, cacheable: true },
  "azureDevOps.syncProject": { method: "POST", path: input => `/integrations/azure-devops/projects/${id(input, "projectId")}/sync`, bodyFields: ["connectionId", "syncType"] },
  "azureDevOps.syncStatus": { method: "GET", path: input => `/integrations/azure-devops/projects/${id(input, "projectId")}/sync-status`, cacheable: true },
  "azureDevOps.syncHistory": { method: "GET", path: input => `/integrations/azure-devops/projects/${id(input, "projectId")}/sync-history`, cacheable: true },
  "azureDevOps.receiveWebhook": { method: "POST", path: "/integrations/azure-devops/webhooks" },
  "azureDevOps.reconcileProject": { method: "POST", path: input => `/integrations/azure-devops/projects/${id(input, "projectId")}/reconcile`, bodyFields: ["connectionId"] },
  "azureDevOps.analyzeWorkItem": { method: "POST", path: "/project-intelligence/refine-story" },
  "azureDevOps.suggestStories": { method: "POST", path: "/project-intelligence/refine-feature" },
  "azureDevOps.analyzeSprint": { method: "POST", path: "/project-intelligence/analyze-description" },
  "azureDevOps.generatePRSummary": { method: "POST", path: "/pr-candidates/generate" },
  "azureDevOps.agentRuns": { method: "GET", path: "/ado-agent/runs", cacheable: true },
  "azureDevOps.agentRun": { method: "GET", path: input => `/ado-agent/runs/${id(input, "runId")}`, cacheable: true },
  "azureDevOps.actionPacks": { method: "GET", path: "/ado-agent/action-packs", cacheable: true },
  "azureDevOps.actionPack": { method: "GET", path: input => `/ado-agent/action-packs/${id(input, "packId")}`, cacheable: true },
  "azureDevOps.approveActionPack": { method: "POST", path: input => `/ado-agent/action-packs/${id(input, "packId")}/approve`, bodyFields: ["actor", "reason"] },
  "azureDevOps.rejectActionPack": { method: "POST", path: input => `/ado-agent/action-packs/${id(input, "packId")}/reject`, bodyFields: ["actor", "reason"] },
  "azureDevOps.applyActionPack": { method: "POST", path: input => `/ado-agent/action-packs/${id(input, "packId")}/apply`, bodyFields: ["actor", "reason", "idempotencyKey"] },

  "platform.health": { method: "GET", path: "/platform/health", cacheable: true },
  "platform.activity": { method: "GET", path: "/platform/activity/recent", cacheable: true, queryFields: ["limit"] },
  "platform.capabilities": { method: "GET", path: "/capabilities", cacheable: true }
};
