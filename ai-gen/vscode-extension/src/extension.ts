import * as vscode from 'vscode';
import {
  BackendResolution,
  resolveBackendUrl,
  storyPlannerSessionUrl,
  storyPlannerSessionsUrl,
  storyPlannerStageUrl,
} from './backendResolver';
import { AiGenSidebarViewProvider, PlannerSession, PlannerViewState } from './sidebarViewProvider';

let backendResolution: BackendResolution = {
  url: null,
  source: 'none',
  healthy: false,
  mode: 'auto',
  reason: 'Backend has not been resolved yet.',
};

let currentSession: PlannerSession | undefined;
let sidebarProvider: AiGenSidebarViewProvider | undefined;

export function activate(context: vscode.ExtensionContext) {
  sidebarProvider = new AiGenSidebarViewProvider(context.extensionUri, {
    startPlanning,
    saveEdits,
    regenerate,
    approve,
    copyPrompt,
    createWorkItems,
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

async function handleAiGenUri(uri: vscode.Uri): Promise<void> {
  const path = uri.path.replace(/^\/+/, '');
  if (path === 'loadExecutionPackage') {
    const params = new URLSearchParams(uri.query);
    const encodedPayload = String(params.get('payload') || '').trim();
    if (!encodedPayload) {
      vscode.window.showErrorMessage('ai-gen execution package link is missing payload.');
      return;
    }
    let payload: {
      dev_prompt?: string;
      ui_prompt?: string;
      qa_prompt?: string;
      copilot_context?: string;
      execution_context?: Record<string, unknown>;
    };
    try {
      payload = JSON.parse(Buffer.from(encodedPayload, 'base64').toString('utf8'));
    } catch {
      vscode.window.showErrorMessage('ai-gen execution package link could not be decoded.');
      return;
    }
    const devPrompt = String(payload.dev_prompt || '').trim();
    const summary = String(payload.execution_context?.story_summary || 'Execution package loaded from Azure DevOps.');
    if (devPrompt) {
      await vscode.env.clipboard.writeText(devPrompt);
    }
    sidebarProvider?.update(getState(devPrompt ? 'Execution package loaded. Dev Prompt copied to clipboard.' : 'Execution package loaded.'));
    await vscode.commands.executeCommand('workbench.view.extension.aiGen');
    vscode.window.showInformationMessage(devPrompt ? `ai-gen execution package loaded: ${summary}` : `ai-gen execution package loaded without a Dev Prompt: ${summary}`);
    return;
  }
  if (path !== 'loadStoryPrompt') {
    vscode.window.showWarningMessage(`Unsupported ai-gen link: ${path || uri.path}`);
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

function getState(statusMessage = ''): PlannerViewState {
  return {
    backendStatus: backendResolution.healthy ? `Connected (${backendResolution.source})` : 'Disconnected',
    backendUrl: backendResolution.url || '',
    loading: false,
    loadingMessage: statusMessage,
    errorMessage: currentSession?.error_message || '',
    session: currentSession,
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
