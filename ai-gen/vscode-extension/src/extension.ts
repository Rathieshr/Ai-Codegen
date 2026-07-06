import * as path from 'path';
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
let recentEngineeringPackages: string[] = [];
let lastSyncAt: number | undefined;

export function activate(context: vscode.ExtensionContext) {
  sidebarProvider = new AiGenSidebarViewProvider(context.extensionUri, {
    startPlanning,
    saveEdits,
    regenerate,
    approve,
    copyPrompt,
    createWorkItems,
    generateExecutionPlan,
    generateDeveloperPrompt,
    rebuildExecutionPackage,
    openCopilotChat,
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
        rememberRecentEngineeringPackage(currentExecutionWorkspace.title);
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

  context.subscriptions.push(
    vscode.window.onDidChangeActiveTextEditor(() => {
      sidebarProvider?.update(getState());
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
  rememberRecentEngineeringPackage(session.story?.title || requirement);
  markSynced();
  return getState('Story planning started.');
}

async function saveEdits(stage: string, payload: Record<string, unknown>): Promise<PlannerViewState> {
  const session = requireSession();
  const backendUrl = await ensureBackendUrl();
  currentSession = await postJson<PlannerSession>(storyPlannerStageUrl(backendUrl, session.session_id, 'edit'), {
    stage,
    payload,
  });
  markSynced();
  return getState('Edits saved.');
}

async function regenerate(stage: string, userInput: string): Promise<PlannerViewState> {
  const session = requireSession();
  const backendUrl = await ensureBackendUrl();
  currentSession = await postJson<PlannerSession>(storyPlannerStageUrl(backendUrl, session.session_id, 'regenerate'), {
    stage,
    user_input: userInput,
  });
  markSynced();
  return getState('Stage regenerated.');
}

async function approve(stage: string): Promise<PlannerViewState> {
  const session = requireSession();
  const backendUrl = await ensureBackendUrl();
  currentSession = await postJson<PlannerSession>(storyPlannerStageUrl(backendUrl, session.session_id, 'approve'), {
    stage,
  });
  markSynced();
  return getState('Stage approved.');
}

async function copyPrompt(): Promise<PlannerViewState> {
  if (currentExecutionWorkspace) {
    if (!currentExecutionWorkspace.developerPrompt) {
      await generateDeveloperPrompt();
    }
    if (!currentExecutionWorkspace?.developerPrompt) {
      throw new Error('Generate the Developer Prompt before copying it.');
    }
    await vscode.env.clipboard.writeText(currentExecutionWorkspace.developerPrompt);
    return getState('Developer Prompt copied.');
  }
  const session = requireSession();
  if (!session.code_generation_prompt) {
    throw new Error('The Developer Prompt is not ready yet.');
  }
  await vscode.env.clipboard.writeText(session.code_generation_prompt);
  return getState('Developer Prompt copied.');
}

async function createWorkItems(): Promise<PlannerViewState> {
  const session = requireSession();
  const backendUrl = await ensureBackendUrl();
  currentSession = await postJson<PlannerSession>(storyPlannerStageUrl(backendUrl, session.session_id, 'create-work-items'), {});
  markSynced();
  return getState('Azure DevOps creation completed.');
}

async function refreshState(): Promise<PlannerViewState> {
  await refreshBackendResolution();
  if (currentSession && backendResolution.url) {
    currentSession = await getJson<PlannerSession>(storyPlannerSessionUrl(backendResolution.url, currentSession.session_id));
  }
  markSynced();
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
  markSynced();
  if (currentExecutionWorkspace.executionPlan) {
    await vscode.env.clipboard.writeText(currentExecutionWorkspace.executionPlan);
  }
  return getState('Implementation Plan generated.');
}

async function generateDeveloperPrompt(): Promise<PlannerViewState> {
  if (!currentExecutionWorkspace?.executionPackage) {
    return await executionPackageMissing('Implementation Package not found.');
  }
  const backendUrl = await ensureBackendUrl();
  const profile = await getJson<Record<string, unknown>>(`${backendUrl}/project-intelligence/profile`);
  const result = await postJson<Record<string, unknown>>(`${backendUrl}/project-intelligence/build-dev-prompt`, {
    profile,
    knowledge_profile: profile.knowledge_registry || {},
    story: storyFromExecutionWorkspace(currentExecutionWorkspace),
    mode: 'deterministic_only',
  });
  currentExecutionWorkspace = {
    ...currentExecutionWorkspace,
    status: 'ready',
    statusMessage: 'Developer Prompt generated.',
    developerPrompt: String(result.prompt || result.finalPrompt || ''),
  };
  markSynced();
  if (currentExecutionWorkspace.developerPrompt) {
    await vscode.env.clipboard.writeText(currentExecutionWorkspace.developerPrompt);
  }
  return getState(currentExecutionWorkspace.developerPrompt ? 'Developer Prompt generated and copied.' : 'Developer Prompt generated.');
}

async function rebuildExecutionPackage(): Promise<PlannerViewState> {
  if (!currentExecutionWorkspace) {
    throw new Error('Open an Execution Workspace first.');
  }
  const rebuilt = await requestExecutionPackage(currentExecutionWorkspace);
  currentExecutionWorkspace = rebuilt;
  markSynced();
  return getState('Implementation Package reloaded.');
}

async function openCopilotChat(): Promise<PlannerViewState> {
  const commands = [
    'workbench.panel.chat.view.copilot.focus',
    'github.copilot-chat.focus',
    'workbench.action.chat.open',
  ];
  for (const command of commands) {
    try {
      await vscode.commands.executeCommand(command);
      return getState('Copilot Chat opened.');
    } catch {
      // try next command
    }
  }
  throw new Error('Unable to open Copilot Chat from this VS Code environment.');
}

async function openPlanning(): Promise<PlannerViewState> {
  currentExecutionWorkspace = undefined;
  await vscode.commands.executeCommand('workbench.view.extension.aiGen');
  return getState('Planning workspace opened.');
}

async function handleAiGenUri(uri: vscode.Uri): Promise<void> {
  const command = aiGenCommandFromUri(uri);
  const normalizedCommand = normalizeAiGenCommand(command, uri);
  if (normalizedCommand === 'loadExecutionPackage' || normalizedCommand === 'openExecution' || normalizedCommand === 'generateExecutionPlan' || normalizedCommand === 'openContextCapsule') {
    let loaded: ExecutionWorkspaceState;
    try {
      loaded = await openExecutionFromUri(uri, normalizedCommand);
      rememberRecentEngineeringPackage(loaded.title);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      currentExecutionWorkspace = missingExecutionWorkspace('', '', message || 'Malformed execution link.');
      loaded = currentExecutionWorkspace;
      await executionPackageMissing(message || 'Malformed execution link.');
    }
    sidebarProvider?.update(getState(loaded.statusMessage));
    await vscode.commands.executeCommand('workbench.view.extension.aiGen');
    if (normalizedCommand === 'generateExecutionPlan') {
      await generateExecutionPlan();
      sidebarProvider?.update(getState('Execution Plan generated.'));
    }
    vscode.window.showInformationMessage(loaded.statusMessage);
    return;
  }
  if (normalizedCommand !== 'loadStoryPrompt') {
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
    vscode.window.showErrorMessage('The linked HEI session does not have an AI Prompt yet.');
    sidebarProvider?.update(getState('HEI session loaded, but no AI Prompt is ready yet.'));
    await vscode.commands.executeCommand('workbench.view.extension.aiGen');
    return;
  }
  backendResolution = {
    url: backendUrl,
    source: 'uri',
    healthy: true,
    mode: 'auto',
    reason: 'Loaded from HEI Azure DevOps link.',
  };
  await vscode.env.clipboard.writeText(currentSession.code_generation_prompt);
  markSynced();
  sidebarProvider?.update(getState('AI Prompt copied from Azure DevOps.'));
  await vscode.commands.executeCommand('workbench.view.extension.aiGen');
  vscode.window.showInformationMessage('HEI AI Prompt copied from Azure DevOps.');
}

function aiGenCommandFromUri(uri: vscode.Uri): string {
  const path = uri.path.replace(/^\/+/, '').trim();
  const authority = uri.authority.trim();
  if (path) {
    return path;
  }
  return authority;
}

function normalizeAiGenCommand(command: string, uri: vscode.Uri): string {
  const raw = String(command || '').trim();
  const normalized = raw.replace(/^\/+/, '').replace(/\/+$/, '').trim();
  const folded = normalized.toLowerCase();
  if (folded === 'openexecution') {
    return 'openExecution';
  }
  if (folded === 'loadexecutionpackage') {
    return 'loadExecutionPackage';
  }
  if (folded === 'generateexecutionplan') {
    return 'generateExecutionPlan';
  }
  if (folded === 'opencontextcapsule') {
    return 'openContextCapsule';
  }
  if (folded === 'loadstoryprompt') {
    return 'loadStoryPrompt';
  }
  const params = new URLSearchParams(uri.query);
  if (params.get('payload') || params.get('artifactType') || params.get('artifactId') || params.get('type') || params.get('id')) {
    return 'openExecution';
  }
  return normalized;
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
  const directJson = tryParseJsonObject(encodedPayload);
  if (directJson) {
    return directJson;
  }
  const normalizedVariants = [
    encodedPayload,
    encodedPayload.replace(/ /g, '+'),
    encodedPayload.replace(/-/g, '+').replace(/_/g, '/'),
    safeDecodeURIComponent(encodedPayload),
  ].filter((value, index, list): value is string => Boolean(value) && list.indexOf(value) === index);

  for (const variant of normalizedVariants) {
    const decoded = decodeExecutionPayload(variant);
    if (decoded) {
      return decoded;
    }
  }

  throw new Error('Malformed execution link. The payload could not be decoded.');
}

function decodeExecutionPayload(encodedPayload: string): Record<string, unknown> | undefined {
  const base64Candidates = [
    encodedPayload,
    encodedPayload.padEnd(encodedPayload.length + ((4 - (encodedPayload.length % 4)) % 4), '='),
  ].filter((value, index, list) => list.indexOf(value) === index);

  for (const candidate of base64Candidates) {
    try {
      const utf8Text = Buffer.from(candidate, 'base64').toString('utf8');
      const parsedUtf8 = tryParseJsonObject(utf8Text);
      if (parsedUtf8) {
        return parsedUtf8;
      }
    } catch {
      // try next strategy
    }

    try {
      const binaryText = Buffer.from(candidate, 'base64').toString('latin1');
      const repairedUtf8 = safeDecodeURIComponent(binaryText.split('').map((char) => `%${char.charCodeAt(0).toString(16).padStart(2, '0')}`).join(''));
      const parsedBinary = tryParseJsonObject(repairedUtf8);
      if (parsedBinary) {
        return parsedBinary;
      }
    } catch {
      // try next strategy
    }
  }

  return undefined;
}

function tryParseJsonObject(value: string): Record<string, unknown> | undefined {
  const trimmed = String(value || '').trim();
  if (!trimmed || (!trimmed.startsWith('{') && !trimmed.startsWith('['))) {
    return undefined;
  }
  try {
    const parsed = JSON.parse(trimmed) as unknown;
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed as Record<string, unknown> : undefined;
  } catch {
    return undefined;
  }
}

function safeDecodeURIComponent(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
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
  const developerPrompt = String(payload.dev_prompt || payload.prompt || '').trim();
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
    developerPrompt,
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
  const activeFile = vscode.window.activeTextEditor?.document?.fileName;
  return {
    workspaceName: vscode.workspace.name || 'Workspace',
    backendStatus: backendResolution.healthy ? `Connected (${backendResolution.source})` : 'Disconnected',
    backendUrl: backendResolution.url || '',
    backendSource: backendResolution.source,
    backendReason: backendResolution.reason,
    currentFileName: activeFile ? path.basename(activeFile) : '',
    currentBranch: currentExecutionWorkspace?.currentBranch || '',
    lastSyncLabel: formatRelativeTime(lastSyncAt),
    loading: false,
    loadingMessage: statusMessage,
    errorMessage: currentSession?.error_message || '',
    recentEngineeringPackages,
    session: currentSession,
    executionWorkspace: currentExecutionWorkspace,
  };
}

function rememberRecentEngineeringPackage(title: string): void {
  const cleaned = String(title || '').trim();
  if (!cleaned) {
    return;
  }
  recentEngineeringPackages = [cleaned, ...recentEngineeringPackages.filter((item) => item !== cleaned)].slice(0, 6);
}

async function refreshBackendResolution(): Promise<void> {
  backendResolution = await resolveBackendUrl();
  markSynced();
}

function markSynced(): void {
  lastSyncAt = Date.now();
}

function formatRelativeTime(timestamp?: number): string {
  if (!timestamp) {
    return '—';
  }
  const seconds = Math.max(0, Math.floor((Date.now() - timestamp) / 1000));
  if (seconds < 10) return 'Just now';
  if (seconds < 60) return `${seconds} sec ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} hr ago`;
  const days = Math.floor(hours / 24);
  return `${days} day${days === 1 ? '' : 's'} ago`;
}

async function ensureBackendUrl(): Promise<string> {
  if (!backendResolution.url) {
    await refreshBackendResolution();
  }
  if (!backendResolution.url) {
    throw new Error('Unable to reach the HEI Engineering Assistant backend. Check the backend URL and health endpoint.');
  }
  return backendResolution.url;
}

function normalizeUrlParam(value: string | null): string {
  const normalized = String(value || '').trim().replace(/\/+$/, '');
  return normalized;
}

function requireSession(): PlannerSession {
  if (!currentSession) {
    throw new Error('Start with an engineering request first.');
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
