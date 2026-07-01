import * as vscode from 'vscode';
import {
  BackendResolution,
  resolveBackendUrl,
  storyPlannerSessionUrl,
  storyPlannerSessionsUrl,
  storyPlannerStageUrl,
} from './backendResolver';
import { AiGenSidebarViewProvider, ExecutionWorkspaceState, PlannerSession, PlannerViewState } from './sidebarViewProvider';

let backendResolution: BackendResolution = {
  url: null,
  source: 'none',
  healthy: false,
  mode: 'auto',
  reason: 'Backend has not been resolved yet.',
};

let currentSession: PlannerSession | undefined;
let currentExecutionWorkspace: ExecutionWorkspaceState | undefined;
let sidebarProvider: AiGenSidebarViewProvider | undefined;

export function activate(context: vscode.ExtensionContext) {
  sidebarProvider = new AiGenSidebarViewProvider(context.extensionUri, {
    startPlanning,
    saveEdits,
    regenerate,
    approve,
    copyPrompt,
    createWorkItems,
    generateExecutionPlan,
    rebuildExecutionPackage,
    openPlanning,
    refreshState,
    getState,
  });

  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider(AiGenSidebarViewProvider.viewType, sidebarProvider)
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('ai-gen.openStoryPlanner', async () => {
      await vscode.commands.executeCommand('workbench.view.extension.aiGen');
    }),
    vscode.commands.registerCommand('ai-gen.refreshBackendResolution', async () => {
      await refreshBackendResolution();
      sidebarProvider?.update(getState('Backend connection refreshed.'));
    }),
    vscode.commands.registerCommand('ai-gen.openExecution', async (payload?: unknown) => {
      if (payload && typeof payload === 'object') {
        currentExecutionWorkspace = executionWorkspaceFromPayload(payload as Record<string, unknown>);
      }
      await vscode.commands.executeCommand('workbench.view.extension.aiGen');
      sidebarProvider?.update(getState('Execution Workspace opened.'));
    }),
    vscode.commands.registerCommand('ai-gen.generateExecutionPlan', async () => {
      await generateExecutionPlan();
      sidebarProvider?.update(getState('Execution Plan generated.'));
    }),
    vscode.commands.registerCommand('ai-gen.openContextCapsule', async () => {
      await vscode.commands.executeCommand('workbench.view.extension.aiGen');
      sidebarProvider?.update(getState('Context Capsule opened in Execution Workspace.'));
    })
  );

  context.subscriptions.push(
    vscode.window.registerUriHandler({
      handleUri: async (uri: vscode.Uri) => {
        await handleAiGenUri(uri);
      },
    })
  );

  void refreshBackendResolution();
}

export function deactivate() {
  currentSession = undefined;
}

async function startPlanning(requirement: string): Promise<PlannerViewState> {
  const backendUrl = await ensureBackendUrl();
  const session = await postJson<PlannerSession>(storyPlannerSessionsUrl(backendUrl), { requirement });
  currentSession = session;
  return getState('Story planning started.');
}

async function saveEdits(stage: string, payload: Record<string, unknown>): Promise<PlannerViewState> {
  const session = requireSession();
  const backendUrl = await ensureBackendUrl();
  currentSession = await postJson<PlannerSession>(storyPlannerStageUrl(backendUrl, session.session_id, 'edit'), {
    stage,
    payload,
  });
  return getState('Edits saved.');
}

async function regenerate(stage: string, userInput: string): Promise<PlannerViewState> {
  const session = requireSession();
  const backendUrl = await ensureBackendUrl();
  currentSession = await postJson<PlannerSession>(storyPlannerStageUrl(backendUrl, session.session_id, 'regenerate'), {
    stage,
    user_input: userInput,
  });
  return getState('Stage regenerated.');
}

async function approve(stage: string): Promise<PlannerViewState> {
  const session = requireSession();
  const backendUrl = await ensureBackendUrl();
  currentSession = await postJson<PlannerSession>(storyPlannerStageUrl(backendUrl, session.session_id, 'approve'), {
    stage,
  });
  return getState('Stage approved.');
}

async function copyPrompt(): Promise<PlannerViewState> {
  if (currentExecutionWorkspace) {
    if (!currentExecutionWorkspace.executionPlan) {
      throw new Error('Generate the Execution Plan before copying it.');
    }
    await vscode.env.clipboard.writeText(currentExecutionWorkspace.executionPlan);
    return getState('Execution Plan copied.');
  }
  const session = requireSession();
  if (!session.code_generation_prompt) {
    throw new Error('Final code-generation prompt is not ready yet.');
  }
  await vscode.env.clipboard.writeText(session.code_generation_prompt);
  return getState('Final code-generation prompt copied.');
}

async function createWorkItems(): Promise<PlannerViewState> {
  const session = requireSession();
  const backendUrl = await ensureBackendUrl();
  currentSession = await postJson<PlannerSession>(storyPlannerStageUrl(backendUrl, session.session_id, 'create-work-items'), {});
  return getState('Azure DevOps creation completed.');
}

async function refreshState(): Promise<PlannerViewState> {
  await refreshBackendResolution();
  if (currentSession && backendResolution.url) {
    currentSession = await getJson<PlannerSession>(storyPlannerSessionUrl(backendResolution.url, currentSession.session_id));
  }
  return getState('State refreshed.');
}

async function generateExecutionPlan(): Promise<PlannerViewState> {
  if (!currentExecutionWorkspace?.executionPackage) {
    return await executionPackageMissing('Execution Package not found.');
  }
  const backendUrl = await ensureBackendUrl();
  const profile = await getJson<Record<string, unknown>>(`${backendUrl}/project-intelligence/profile`);
  const result = await postJson<Record<string, unknown>>(`${backendUrl}/project-intelligence/build-execution-plan`, {
    profile,
    knowledge_profile: profile.knowledge_registry || {},
    story: storyFromExecutionWorkspace(currentExecutionWorkspace),
    execution_mode: 'implement',
    mode: 'deterministic_only',
  });
  currentExecutionWorkspace = {
    ...currentExecutionWorkspace,
    status: 'ready',
    statusMessage: 'Execution Plan generated.',
    executionPlan: String(result.plan || result.finalPlan || result.prompt || ''),
  };
  if (currentExecutionWorkspace.executionPlan) {
    await vscode.env.clipboard.writeText(currentExecutionWorkspace.executionPlan);
  }
  return getState(currentExecutionWorkspace.executionPlan ? 'Execution Plan generated and copied.' : 'Execution Plan generated.');
}

async function rebuildExecutionPackage(): Promise<PlannerViewState> {
  if (!currentExecutionWorkspace) {
    throw new Error('Open an Execution Workspace first.');
  }
  const rebuilt = await requestExecutionPackage(currentExecutionWorkspace);
  currentExecutionWorkspace = rebuilt;
  return getState('Execution Package rebuilt.');
}

async function openPlanning(): Promise<PlannerViewState> {
  currentExecutionWorkspace = undefined;
  await vscode.commands.executeCommand('workbench.view.extension.aiGen');
  return getState('Planning workspace opened.');
}

async function handleAiGenUri(uri: vscode.Uri): Promise<void> {
  const command = aiGenCommandFromUri(uri);
  if (command === 'loadExecutionPackage' || command === 'openExecution' || command === 'generateExecutionPlan' || command === 'openContextCapsule') {
    let loaded: ExecutionWorkspaceState;
    try {
      loaded = await openExecutionFromUri(uri, command);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      currentExecutionWorkspace = missingExecutionWorkspace('', '', message || 'Malformed execution link.');
      loaded = currentExecutionWorkspace;
      await executionPackageMissing(message || 'Malformed execution link.');
    }
    sidebarProvider?.update(getState(loaded.statusMessage));
    await vscode.commands.executeCommand('workbench.view.extension.aiGen');
    if (command === 'generateExecutionPlan') {
      await generateExecutionPlan();
      sidebarProvider?.update(getState('Execution Plan generated.'));
    }
    vscode.window.showInformationMessage(loaded.statusMessage);
    return;
  }
  if (command !== 'loadStoryPrompt') {
    vscode.window.showErrorMessage(`Unknown ai-gen link action: ${command || uri.toString()}`);
    return;
  }
  const params = new URLSearchParams(uri.query);
  const backendUrl = normalizeUrlParam(params.get('backendUrl'));
  const sessionId = String(params.get('sessionId') || '').trim();
  if (!backendUrl || !sessionId) {
    vscode.window.showErrorMessage('ai-gen prompt link is missing backendUrl or sessionId.');
    return;
  }
  currentSession = await getJson<PlannerSession>(storyPlannerSessionUrl(backendUrl, sessionId));
  if (!currentSession.code_generation_prompt) {
    vscode.window.showErrorMessage('The linked Story Planner session does not have a final code-generation prompt yet.');
    sidebarProvider?.update(getState('Story prompt link loaded, but no prompt is ready yet.'));
    await vscode.commands.executeCommand('workbench.view.extension.aiGen');
    return;
  }
  backendResolution = {
    url: backendUrl,
    source: 'uri',
    healthy: true,
    mode: 'auto',
    reason: 'Loaded from Azure DevOps Story Planner link.',
  };
  await vscode.env.clipboard.writeText(currentSession.code_generation_prompt);
  sidebarProvider?.update(getState('Exact Story Planner prompt copied from Azure DevOps.'));
  await vscode.commands.executeCommand('workbench.view.extension.aiGen');
  vscode.window.showInformationMessage('ai-gen code-generation prompt copied from Azure DevOps.');
}

function aiGenCommandFromUri(uri: vscode.Uri): string {
  const path = uri.path.replace(/^\/+/, '').trim();
  const authority = uri.authority.trim();
  if (path) {
    return path;
  }
  return authority;
}

async function openExecutionFromUri(uri: vscode.Uri, command: string): Promise<ExecutionWorkspaceState> {
  const params = new URLSearchParams(uri.query);
  const backendUrl = normalizeUrlParam(params.get('backendUrl'));
  if (backendUrl) {
    backendResolution = {
      url: backendUrl,
      source: 'uri',
      healthy: true,
      mode: 'auto',
      reason: 'Loaded from HEI execution link.',
    };
  }

  const payload = payloadFromParams(params);
  if (payload) {
    currentExecutionWorkspace = executionWorkspaceFromPayload(payload);
    if (command === 'loadExecutionPackage') {
      currentExecutionWorkspace.statusMessage = 'Legacy execution link redirected to Execution Workspace.';
    }
    return currentExecutionWorkspace;
  }

  const artifactType = String(params.get('artifactType') || params.get('type') || '').trim();
  const artifactId = String(params.get('artifactId') || params.get('id') || '').trim();
  if (!artifactType || !artifactId) {
    currentExecutionWorkspace = missingExecutionWorkspace(artifactType, artifactId, 'Malformed execution link. Missing artifactType or artifactId.');
    await executionPackageMissing(currentExecutionWorkspace.statusMessage);
    return currentExecutionWorkspace;
  }

  try {
    currentExecutionWorkspace = await requestExecutionPackage({ artifactType, artifactId, title: String(params.get('title') || `${artifactType} #${artifactId}`) } as ExecutionWorkspaceState);
    return currentExecutionWorkspace;
  } catch (error) {
    currentExecutionWorkspace = missingExecutionWorkspace(artifactType, artifactId, error instanceof Error ? error.message : String(error));
    await executionPackageMissing('Execution Package not found.');
    return currentExecutionWorkspace;
  }
}

function payloadFromParams(params: URLSearchParams): Record<string, unknown> | undefined {
  const encodedPayload = String(params.get('payload') || '').trim();
  if (!encodedPayload) {
    return undefined;
  }
  try {
    return JSON.parse(Buffer.from(encodedPayload, 'base64').toString('utf8')) as Record<string, unknown>;
  } catch {
    throw new Error('Malformed execution link. The payload could not be decoded.');
  }
}

function executionWorkspaceFromPayload(payload: Record<string, unknown>): ExecutionWorkspaceState {
  const executionContext = objectValue(payload.execution_context);
  const executionPackage = objectValue(executionContext.execution_package_v2) || objectValue(executionContext.executionPackageV2) || objectValue(payload.execution_package) || objectValue(payload.executionPackage);
  const contextCapsule = objectValue(executionContext.context_capsule) || objectValue(executionContext.contextCapsule) || objectValue(payload.context_capsule);
  const executionSource = objectValue(executionContext.execution_source) || objectValue(executionContext.executionSource);
  const artifactType = String(executionSource.artifactType || executionContext.artifact_type || executionPackage.artifactType || (executionPackage.taskId ? 'Task' : 'Story'));
  const artifactId = String(executionSource.artifactId || executionContext.artifact_id || executionPackage.artifactId || executionPackage.taskId || executionPackage.storyId || '');
  const title = String(executionSource.title || objectValue(executionContext.parent_story).title || objectValue(executionPackage.businessContext).taskObjective || objectValue(executionPackage.businessContext).storyTitle || 'Execution artifact');
  const executionPlan = String(payload.execution_plan || payload.executionPlan || payload.dev_prompt || '').trim();
  const relatedFiles = relatedFilesFromPackage(executionPackage);
  const workspace: ExecutionWorkspaceState = {
    artifactType,
    artifactId,
    title,
    status: executionPackage && Object.keys(executionPackage).length ? 'ready' : 'missing',
    statusMessage: executionPackage && Object.keys(executionPackage).length ? 'Execution Package loaded in workspace.' : 'Execution Package not found.',
    executionPackage,
    executionContext,
    contextCapsule,
    executionPlan,
    repositoryContext: objectValue(executionPackage.repositoryContext),
    relatedFiles,
    currentBranch: String(objectValue(executionContext.repository).branch || ''),
  };
  return workspace;
}

async function requestExecutionPackage(workspace: ExecutionWorkspaceState): Promise<ExecutionWorkspaceState> {
  const backendUrl = await ensureBackendUrl();
  const profile = await getJson<Record<string, unknown>>(`${backendUrl}/project-intelligence/profile`);
  const executionContext = await postJson<Record<string, unknown>>(`${backendUrl}/project-intelligence/build-execution-context`, {
    profile,
    knowledge_profile: profile.knowledge_registry || {},
    story: storyFromExecutionWorkspace(workspace),
    mode: 'deterministic_only',
  });
  return executionWorkspaceFromPayload({ execution_context: executionContext });
}

function storyFromExecutionWorkspace(workspace: ExecutionWorkspaceState): Record<string, unknown> {
  const businessContext = objectValue(workspace.executionPackage?.businessContext);
  return {
    id: workspace.artifactId,
    type: workspace.artifactType,
    work_item_type: workspace.artifactType,
    artifactType: workspace.artifactType,
    title: workspace.title || businessContext.taskObjective || businessContext.storyTitle || `${workspace.artifactType} #${workspace.artifactId}`,
    description: businessContext.storyUserGoal || businessContext.taskObjective || workspace.statusMessage || '',
    acceptance_criteria: acceptanceFromPackage(workspace.executionPackage || {}),
    executable_artifact: {
      id: workspace.artifactId,
      type: workspace.artifactType,
      title: workspace.title,
      description: businessContext.taskObjective || businessContext.storyUserGoal || '',
      acceptance_criteria: acceptanceFromPackage(workspace.executionPackage || {}),
    },
  };
}

function acceptanceFromPackage(executionPackage: Record<string, unknown>): string[] {
  const mapping = Array.isArray(executionPackage.acceptanceMapping) ? executionPackage.acceptanceMapping : [];
  return mapping
    .map((item) => objectValue(item).acceptanceText)
    .filter((item): item is string => typeof item === 'string' && item.trim().length > 0);
}

function relatedFilesFromPackage(executionPackage: Record<string, unknown>): string[] {
  const repository = objectValue(executionPackage.repositoryContext);
  const files = Array.isArray(repository.relevantFiles) ? repository.relevantFiles : [];
  return files
    .map((item) => {
      const file = objectValue(item);
      return String(file.name || file.path || '').trim();
    })
    .filter(Boolean);
}

function objectValue(value: unknown): Record<string, any> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, any> : {};
}

function missingExecutionWorkspace(artifactType: string, artifactId: string, message: string): ExecutionWorkspaceState {
  return {
    artifactType: artifactType || 'Artifact',
    artifactId: artifactId || '',
    title: artifactId ? `${artifactType || 'Artifact'} #${artifactId}` : 'Unknown execution artifact',
    status: 'missing',
    statusMessage: message,
    relatedFiles: [],
  };
}

async function executionPackageMissing(message: string): Promise<PlannerViewState> {
  const action = await vscode.window.showErrorMessage(message, 'Reload', 'Rebuild Package', 'Open Planning');
  if (action === 'Reload') {
    await refreshState();
  }
  if (action === 'Rebuild Package') {
    await rebuildExecutionPackage();
  }
  if (action === 'Open Planning') {
    await openPlanning();
  }
  return getState(message);
}

function getState(statusMessage = ''): PlannerViewState {
  return {
    backendStatus: backendResolution.healthy ? `Connected (${backendResolution.source})` : 'Disconnected',
    backendUrl: backendResolution.url || '',
    loading: false,
    loadingMessage: statusMessage,
    errorMessage: currentSession?.error_message || '',
    session: currentSession,
    executionWorkspace: currentExecutionWorkspace,
  };
}

async function refreshBackendResolution(): Promise<void> {
  backendResolution = await resolveBackendUrl();
}

async function ensureBackendUrl(): Promise<string> {
  if (!backendResolution.url) {
    await refreshBackendResolution();
  }
  if (!backendResolution.url) {
    throw new Error('Unable to reach the AI Story Planner backend. Check the backend URL and health endpoint.');
  }
  return backendResolution.url;
}

function normalizeUrlParam(value: string | null): string {
  const normalized = String(value || '').trim().replace(/\/+$/, '');
  return normalized;
}

function requireSession(): PlannerSession {
  if (!currentSession) {
    throw new Error('Start planning from a requirement first.');
  }
  return currentSession;
}

async function getJson<T>(url: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, { method: 'GET' });
  } catch {
    throw new Error(`Unable to reach backend at ${url}.`);
  }
  if (!response.ok) {
    throw new Error(`Backend returned HTTP ${response.status}: ${await response.text()}`);
  }
  return await response.json() as T;
}

async function postJson<T>(url: string, body: Record<string, unknown>): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  } catch {
    throw new Error(`Unable to reach backend at ${url}.`);
  }
  if (!response.ok) {
    throw new Error(`Backend returned HTTP ${response.status}: ${await response.text()}`);
  }
  return await response.json() as T;
}
