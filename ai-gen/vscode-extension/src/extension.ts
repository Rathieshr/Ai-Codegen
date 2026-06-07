import * as childProcess from 'child_process';
import * as util from 'util';
import * as vscode from 'vscode';
import {
  BackendResolution,
  capabilitiesUrl,
  contextUrl,
  handoffByIdUrl,
  handoffListUrl,
  handoffMarkdownUrl,
  resolveBackendUrl,
  snapshotUrl,
  storyPlannerSessionUrl,
  validateUrl
} from './backendResolver';
import { AiGenSidebarViewProvider, SidebarRequestOptions, SidebarResult, SidebarState } from './sidebarViewProvider';

const DEFAULT_QUERY = 'Explain the relevant business flow for this context';

const execFile = util.promisify(childProcess.execFile);

type EditorContext = {
  file_path: string;
  selected_text: string;
  workspace_root: string;
  open_files: string[];
  current_file: string;
  branch_name: string;
  session_id: string;
};

type BackendResponse = {
  optimized_prompt?: string;
  matched_logic?: string[];
  token_estimate?: number;
  execution_target?: string;
  execution_reason?: string;
  available_targets?: Record<string, boolean>;
  planning_enabled?: boolean;
  plan?: ExecutionPlan;
  plan_summary?: string;
  local_provider?: string;
  local_model?: string;
  local_output?: string;
  resolved_repo_id?: string;
  resolved_branch_name?: string;
  retrieval_bias_applied?: boolean;
  session_bias_summary?: Record<string, unknown>;
  repo_identity_mode?: string;
  repo_identity_source?: string;
  prompt_mode?: string;
  prompt_mode_reason?: string;
  execution_confidence?: number;
  execution_confidence_level?: string;
  execution_confidence_signals?: string[];
  selected_execution_files?: string[];
  execution_validation?: Record<string, unknown>;
  drift_detected?: boolean;
  constraint_violations?: string[];
  risky_changes?: string[];
  related_flows?: string[];
  likely_bug_hotspots?: Array<Record<string, unknown>>;
  retry_required?: boolean;
  retry_plan?: Record<string, unknown>;
  corrected_execution_prompt?: string;
  semantic_mapping_applied?: boolean;
  refinement_used?: boolean;
  refinement_source?: string;
  refinement_provider?: string;
  refinement_reason?: string;
  phi_used?: boolean;
  phi_status?: string;
  refined_base_flows?: string[];
  refined_variants?: string[];
  refined_surfaces?: string[];
  refined_base_flow?: string;
  refined_variant?: string;
  refined_surface?: string;
  refined_fields?: string[];
  refined_validations?: string[];
  refined_scope?: string[];
  refined_actors?: string[];
  refined_states?: string[];
  refinement_unknowns?: string[];
  refinement_confidence?: string;
};

type ExecutionValidationResponse = {
  execution_validation?: Record<string, unknown>;
  drift_detected?: boolean;
  constraint_violations?: string[];
  risky_changes?: string[];
  retry_required?: boolean;
  retry_plan?: Record<string, unknown>;
  corrected_execution_prompt?: string;
};

type BackendCapabilities = {
  backend_up?: boolean;
  codex_available?: boolean;
  local_enabled?: boolean;
  local_provider?: string | null;
  local_model?: string | null;
  local_available?: boolean;
  local_base_url?: string | null;
  cloud_enabled?: boolean;
  warnings?: string[];
  available_targets?: Record<string, boolean>;
  refiner?: {
    enabled?: boolean;
    provider?: string | null;
    model?: string | null;
    configured?: boolean;
  };
};

type PlanStep = {
  id: string;
  title: string;
  purpose: string;
  risk: string;
};

type ExecutionPlan = {
  needs_planning: boolean;
  plan_type: string;
  steps: PlanStep[];
};

type HandoffRecord = {
  handoff_id?: string;
  pipeline_id?: string;
  work_item_id?: string;
  stage?: string;
  version?: number;
  status?: string;
  summary?: string;
  created_at?: string;
  approved_at?: string | null;
  execution_packet?: string;
  selected_files?: string[];
  content?: Record<string, unknown>;
  refinement?: Record<string, unknown>;
  repo_context?: Record<string, unknown>;
  constraints?: string[];
  open_questions?: string[];
  next_actions?: string[];
};

type StoryPlannerSession = {
  session_id: string;
  requirement?: string;
  story?: {
    title?: string;
    description?: string;
    business_value?: string;
  };
  acceptance_criteria?: string[];
  tasks?: Array<{ title?: string; description?: string }>;
  code_generation_prompt?: string;
  updated_at?: string;
};

type PromptMetadata = {
  detectedIntent: string;
  hasLinkedFlows: boolean;
  hasImpactedComponents: boolean;
  hasCriticalConstraints: boolean;
  planningEnabled: boolean;
  planSummary: string;
  executionTarget: string;
  executionReason: string;
  availableTargets: Record<string, boolean>;
};

type LastPromptState = PromptMetadata & {
  query: string;
  prompt: string;
  timestamp: Date;
  response: BackendResponse;
  editorContext: EditorContext;
};

type LastExecutionState = {
  repoId: string;
  branchName: string;
  sessionId: string;
  workspaceRoot: string;
  selectedFiles: string[];
  constraints: string[];
  likelyBreakpoints: string[];
  baselineHashes: Record<string, string>;
  promptMode: string;
  timestamp: Date;
};

type LastHandoffRequest =
  | { kind: 'id'; handoffId: string }
  | { kind: 'work_item'; workItemId: string; stage: string };

let lastPromptState: LastPromptState | undefined;
let lastExecutionState: LastExecutionState | undefined;
let lastHandoffRequest: LastHandoffRequest | undefined;
let lastLoadedHandoff: HandoffRecord | undefined;
let lastSidebarView: 'prompt' | 'handoff' = 'prompt';
let backendResolution: BackendResolution = {
  url: null,
  source: 'none',
  healthy: false,
  mode: 'auto',
  reason: 'Backend has not been resolved yet.'
};
let backendStatus = 'unknown';
let codexAvailable = false;
let localEnabled = false;
let localAvailable = false;
let localProvider = '';
let localModel = '';
let localBaseUrl = '';
let cloudEnabled = false;
let refinerEnabled = false;
let refinerProvider = '';
let refinerModel = '';
let refinerConfigured = false;
let statusWarnings: string[] = [];
let sidebarProvider: AiGenSidebarViewProvider | undefined;
const ideSessionId = `vscode_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;

export function activate(context: vscode.ExtensionContext) {
  const outputChannel = vscode.window.createOutputChannel('ai-gen');
  sidebarProvider = new AiGenSidebarViewProvider(context.extensionUri, {
    previewTask: async (query, options) => {
      if (!query) {
        return getSidebarState('Enter a task before previewing.', 'Task is required.');
      }
      const state = await requestAndStorePrompt(query, options);
      showPromptOutput(outputChannel, state.prompt, state.response, state);
      return getSidebarState('Preview ready.', '');
    },
    explainTask: async (options) => {
      const state = await requestAndStorePrompt(DEFAULT_QUERY, options);
      showPromptOutput(outputChannel, state.prompt, state.response, state);
      return getSidebarState('Flow explanation ready.', '');
    },
    copyPrompt: async () => {
      const message = await copyLastPrompt();
      return getSidebarState(message, '');
    },
    sendToCodex: async () => {
      const message = await sendLastPromptToCodex();
      return getSidebarState(message, '');
    },
    refreshHandoff: async () => {
      const message = await refreshLastHandoff(outputChannel);
      return getSidebarState(message, '');
    },
    reloadPipeline: async () => {
      const message = await reloadLastPromptFromBackend(outputChannel);
      return getSidebarState(message, '');
    },
    snapshotExecution: async () => {
      const message = await snapshotLastExecution();
      return getSidebarState(message, '');
    },
    retryExecution: async () => {
      const message = await retryLastExecution();
      return getSidebarState(message, '');
    },
    validateExecution: async () => {
      const message = await validateLastExecution();
      return getSidebarState(message, '');
    },
    checkBackend: async () => {
      const message = await checkBackend();
      return getSidebarState(message, '');
    },
    refreshStatus: async () => {
      await refreshAvailability();
      return getSidebarState('Status refreshed.', '');
    },
    getState: () => getSidebarState('', '')
  });

  context.subscriptions.push(
    outputChannel,
    vscode.window.registerWebviewViewProvider(AiGenSidebarViewProvider.viewType, sidebarProvider),
    vscode.window.registerUriHandler({
      handleUri: async (uri: vscode.Uri) => {
        const storyPromptParams = parseStoryPromptParamsFromUri(uri);
        if (storyPromptParams) {
          try {
            await loadAndShowStoryPrompt(storyPromptParams.backendUrl, storyPromptParams.sessionId, outputChannel);
            vscode.window.showInformationMessage('Story Planner prompt copied from Azure DevOps.');
            await vscode.commands.executeCommand('aiGen.sidebar.focus');
          } catch (error) {
            const message = error instanceof Error ? error.message : String(error);
            sidebarProvider?.update(getSidebarState('Unable to load Story Planner prompt.', message));
            vscode.window.showErrorMessage(`Unable to load Story Planner prompt. ${message}`);
          }
          return;
        }
        const handoffId = parseHandoffIdFromUri(uri);
        if (!handoffId) {
          const message = `Unable to parse handoff link: ${uri.toString(true)}`;
          sidebarProvider?.update(getSidebarState('Failed to open handoff link.', message));
          vscode.window.showErrorMessage(message);
          return;
        }
        try {
          await loadAndShowHandoffById(handoffId, outputChannel);
          vscode.window.showInformationMessage(`Handoff loaded: ${handoffId}`);
          await vscode.commands.executeCommand('aiGen.sidebar.focus');
        } catch (error) {
          const message = error instanceof Error ? error.message : String(error);
          sidebarProvider?.update(getSidebarState(`Unable to load handoff ${handoffId}.`, message));
          vscode.window.showErrorMessage(`Unable to load handoff ${handoffId}. ${message}`);
        }
      }
    }),
    vscode.commands.registerCommand('ai-gen.ask', async () => {
      const query = await vscode.window.showInputBox({
        title: 'ai-gen',
        prompt: 'What should ai-gen prepare for Codex?',
        placeHolder: 'Add OTP login',
        ignoreFocusOut: true
      });

      if (!query) {
        return;
      }

      await requestAndPreviewPrompt(query, outputChannel);
    }),
    vscode.commands.registerCommand('ai-gen.explainFlow', async () => {
      await requestAndPreviewPrompt(DEFAULT_QUERY, outputChannel);
    }),
    vscode.commands.registerCommand('ai-gen.generateSafely', async () => {
      const query = await vscode.window.showInputBox({
        title: 'ai-gen: Generate Safely',
        prompt: 'Describe the safe code generation task.',
        placeHolder: 'Fix login bug without breaking existing auth flow',
        ignoreFocusOut: true
      });

      if (!query) {
        return;
      }

      await requestAndPreviewPrompt(query, outputChannel);
    }),
    vscode.commands.registerCommand('ai-gen.copyPrompt', async () => {
      const message = await copyLastPrompt();
      sidebarProvider?.update(getSidebarState(message, ''));
    }),
    vscode.commands.registerCommand('ai-gen.sendToCodex', async () => {
      const message = await sendLastPromptToCodex();
      sidebarProvider?.update(getSidebarState(message, ''));
    }),
    vscode.commands.registerCommand('ai-gen.refreshHandoff', async () => {
      const message = await refreshLastHandoff(outputChannel);
      sidebarProvider?.update(getSidebarState(message, ''));
    }),
    vscode.commands.registerCommand('ai-gen.reloadPipeline', async () => {
      const message = await reloadLastPromptFromBackend(outputChannel);
      sidebarProvider?.update(getSidebarState(message, ''));
    }),
    vscode.commands.registerCommand('ai-gen.snapshotExecution', async () => {
      const message = await snapshotLastExecution();
      sidebarProvider?.update(getSidebarState(message, ''));
    }),
    vscode.commands.registerCommand('ai-gen.validateExecution', async () => {
      const message = await validateLastExecution();
      sidebarProvider?.update(getSidebarState(message, ''));
    }),
    vscode.commands.registerCommand('ai-gen.retryExecution', async () => {
      const message = await retryLastExecution();
      sidebarProvider?.update(getSidebarState(message, ''));
    }),
    vscode.commands.registerCommand('ai-gen.checkBackend', async () => {
      const message = await checkBackend();
      sidebarProvider?.update(getSidebarState(message, ''));
    }),
    vscode.commands.registerCommand('ai-gen.refreshBackendResolution', async () => {
      const resolution = await refreshBackendResolution();
      const message = resolution.healthy && resolution.url
        ? `ai-gen active backend: ${resolution.source} (${resolution.url})`
        : resolution.reason;
      vscode.window.showInformationMessage(message);
      sidebarProvider?.update(getSidebarState(message, resolution.healthy ? '' : resolution.reason));
    }),
    vscode.commands.registerCommand('ai-gen.loadHandoffById', async () => {
      const handoffId = await vscode.window.showInputBox({
        title: 'ai-gen: Load Handoff by ID',
        prompt: 'Enter the handoff id',
        placeHolder: '123:dev:v1',
        ignoreFocusOut: true
      });
      if (!handoffId) {
        return;
      }
      await loadAndShowHandoffById(handoffId, outputChannel);
    }),
    vscode.commands.registerCommand('ai-gen.loadHandoffForWorkItem', async () => {
      const workItemId = await vscode.window.showInputBox({
        title: 'ai-gen: Load Approved Handoff',
        prompt: 'Enter the work item id',
        placeHolder: '123',
        ignoreFocusOut: true
      });
      if (!workItemId) {
        return;
      }
      const stage = await vscode.window.showInputBox({
        title: 'ai-gen: Handoff Stage',
        prompt: 'Enter the stage to load',
        placeHolder: 'dev',
        value: 'dev',
        ignoreFocusOut: true
      });
      await loadAndShowHandoffForWorkItem(workItemId, stage || 'dev', outputChannel);
    }),
    vscode.commands.registerCommand('ai-gen.loadLatestDevHandoffForWorkItem', async () => {
      const workItemId = await vscode.window.showInputBox({
        title: 'ai-gen: Load Latest Dev Handoff',
        prompt: 'Enter the work item id',
        placeHolder: '123',
        ignoreFocusOut: true
      });
      if (!workItemId) {
        return;
      }
      await loadAndShowHandoffForWorkItem(workItemId, 'dev', outputChannel);
    })
  );
}

export function deactivate() {
  // Nothing to clean up.
}

async function requestAndPreviewPrompt(
  query: string,
  outputChannel: vscode.OutputChannel,
  options: SidebarRequestOptions = { includeSelection: true, includeFile: true }
) {
  try {
    const state = await requestAndStorePrompt(query, options);

    showPromptOutput(outputChannel, state.prompt, state.response, state);
    sidebarProvider?.update(getSidebarState('Preview ready.', ''));
    await vscode.commands.executeCommand('aiGen.sidebar.focus');
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    sidebarProvider?.update(getSidebarState('Preview failed.', message));
    vscode.window.showErrorMessage(`ai-gen request failed: ${message}`);
  }
}

async function requestAndStorePrompt(
  query: string,
  options: SidebarRequestOptions = { includeSelection: true, includeFile: true }
): Promise<LastPromptState> {
  await ensureBackendAvailable();

  const editorContext = await getEditorContext(options);
  const response = await requestContext(query, editorContext);
  const prompt = response.optimized_prompt;

  if (!prompt) {
    throw new Error('ai-gen backend returned no optimized prompt.');
  }

  const metadata = extractPromptMetadata(prompt, response);
  codexAvailable = metadata.availableTargets.codex ?? codexAvailable;
  lastPromptState = {
    query,
    prompt,
    timestamp: new Date(),
    response,
    editorContext,
    ...metadata
  };
  lastSidebarView = 'prompt';
  return lastPromptState;
}

async function getEditorContext(
  options: SidebarRequestOptions = { includeSelection: true, includeFile: true }
): Promise<EditorContext> {
  const editor = vscode.window.activeTextEditor;
  const document = editor?.document;
  const selection = editor?.selection;
  const selectedText = options.includeSelection && editor && selection && !selection.isEmpty
    ? document?.getText(selection) ?? ''
    : '';
  const workspaceFolder = document
    ? vscode.workspace.getWorkspaceFolder(document.uri)
    : vscode.workspace.workspaceFolders?.[0];

  return {
    file_path: options.includeFile ? document?.uri.fsPath ?? '' : '',
    selected_text: selectedText,
    workspace_root: workspaceFolder?.uri.fsPath ?? '',
    open_files: options.includeFile ? collectOpenFiles() : [],
    current_file: options.includeFile ? document?.uri.fsPath ?? '' : '',
    branch_name: workspaceFolder ? await detectGitBranch(workspaceFolder.uri.fsPath) : '',
    session_id: ideSessionId
  };
}

function collectOpenFiles(): string[] {
  const files = vscode.workspace.textDocuments
    .filter((document) => document.uri.scheme === 'file')
    .map((document) => document.uri.fsPath);
  return Array.from(new Set(files));
}

async function requestContext(query: string, editorContext: EditorContext): Promise<BackendResponse> {
  const backendUrl = await getActiveBackendBaseUrl();

  let response: Response;
  try {
    response = await fetch(contextUrl(backendUrl), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        query,
        file_path: editorContext.file_path,
        selected_text: editorContext.selected_text,
        workspace_root: editorContext.workspace_root,
        open_files: editorContext.open_files,
        current_file: editorContext.current_file,
        branch_name: editorContext.branch_name,
        session_id: editorContext.session_id,
        ide: 'vscode'
      })
    });
  } catch {
    throw new Error(`Could not reach ai-gen backend at ${backendUrl}. ${backendResolution.reason}`);
  }

  if (!response.ok) {
    const details = await response.text();
    throw new Error(`Backend returned HTTP ${response.status}: ${details}`);
  }

  return response.json() as Promise<BackendResponse>;
}

async function detectGitBranch(workspaceRoot: string): Promise<string> {
  try {
    const { stdout } = await execFile('git', ['rev-parse', '--abbrev-ref', 'HEAD'], {
      cwd: workspaceRoot,
      timeout: 1000
    });
    const branch = stdout.trim();
    return branch && branch !== 'HEAD' ? branch : '';
  } catch {
    return '';
  }
}

async function ensureBackendAvailable() {
  const resolution = await refreshBackendResolution();
  if (!resolution.healthy || !resolution.url) {
    markBackendDisconnected();
    throw new Error(resolution.reason);
  }
}

async function checkBackend(): Promise<string> {
  try {
    const resolution = await refreshBackendResolution();
    if (!resolution.healthy || !resolution.url) {
      throw new Error(resolution.reason);
    }
    applyCapabilities(await requestCapabilities());
    const message = `ai-gen connected to ${resolution.source} backend: ${resolution.url}`;
    vscode.window.showInformationMessage(message);
    return message;
  } catch (error) {
    markBackendDisconnected();
    const message = error instanceof Error ? error.message : String(error);
    vscode.window.showErrorMessage(message);
    return message;
  }
}

async function refreshAvailability() {
  codexAvailable = await isCodexCliAvailable();
  try {
    const resolution = await refreshBackendResolution();
    if (!resolution.healthy || !resolution.url) {
      return;
    }
    const capabilities = await requestCapabilities();
    applyCapabilities(capabilities);
  } catch {
    markBackendDisconnected();
  }
}

async function requestCapabilities(): Promise<BackendCapabilities> {
  const baseUrl = await getActiveBackendBaseUrl();
  let response: Response;
  try {
    response = await fetch(capabilitiesUrl(baseUrl), { method: 'GET' });
  } catch {
    throw new Error(`Backend is unavailable at ${baseUrl}. ${backendResolution.reason}`);
  }
  if (!response.ok) {
    throw new Error(`Capabilities returned HTTP ${response.status}`);
  }
  return response.json() as Promise<BackendCapabilities>;
}

async function fetchJson<T>(url: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, { method: 'GET' });
  } catch {
    throw new Error(`Could not reach ai-gen backend at ${url}.`);
  }
  if (!response.ok) {
    const details = await response.text();
    throw new Error(`Backend returned HTTP ${response.status}: ${details}`);
  }
  return response.json() as Promise<T>;
}

async function postJson<T>(url: string, payload: Record<string, unknown>): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    });
  } catch {
    throw new Error(`Could not reach ai-gen backend at ${url}.`);
  }
  if (!response.ok) {
    const details = await response.text();
    throw new Error(`Backend returned HTTP ${response.status}: ${details}`);
  }
  return response.json() as Promise<T>;
}

function applyCapabilities(capabilities: BackendCapabilities) {
  backendStatus = capabilities.backend_up ? 'connected' : 'disconnected';
  codexAvailable = Boolean(capabilities.codex_available);
  localEnabled = Boolean(capabilities.local_enabled);
  localAvailable = Boolean(capabilities.local_available);
  localProvider = capabilities.local_provider || '';
  localModel = capabilities.local_model || '';
  localBaseUrl = capabilities.local_base_url || '';
  cloudEnabled = Boolean(capabilities.cloud_enabled);
  refinerEnabled = Boolean(capabilities.refiner?.enabled);
  refinerProvider = capabilities.refiner?.provider || '';
  refinerModel = capabilities.refiner?.model || '';
  refinerConfigured = Boolean(capabilities.refiner?.configured);
  statusWarnings = capabilities.warnings || [];
}

function markBackendDisconnected() {
  backendStatus = 'disconnected';
  localAvailable = false;
  statusWarnings = [backendResolution.reason || 'Backend is disconnected'];
}

async function refreshBackendResolution(): Promise<BackendResolution> {
  backendResolution = await resolveBackendUrl();
  backendStatus = backendResolution.healthy ? 'connected' : 'disconnected';
  if (backendResolution.healthy) {
    statusWarnings = [];
  } else {
    localAvailable = false;
    statusWarnings = [backendResolution.reason];
  }
  return backendResolution;
}

async function getActiveBackendBaseUrl(): Promise<string> {
  const resolution = await refreshBackendResolution();
  if (!resolution.healthy || !resolution.url) {
    throw new Error(resolution.reason);
  }
  return resolution.url;
}

function showPromptOutput(
  outputChannel: vscode.OutputChannel,
  prompt: string,
  response: BackendResponse,
  metadata: PromptMetadata
) {
  outputChannel.clear();
  outputChannel.appendLine('ai-gen optimized prompt');
  outputChannel.appendLine('');
  outputChannel.appendLine(`Detected intent: ${metadata.detectedIntent}`);
  outputChannel.appendLine(`Linked flows: ${metadata.hasLinkedFlows ? 'yes' : 'no'}`);
  outputChannel.appendLine(`Impacted components: ${metadata.hasImpactedComponents ? 'yes' : 'no'}`);
  outputChannel.appendLine(`Critical constraints: ${metadata.hasCriticalConstraints ? 'yes' : 'no'}`);
  outputChannel.appendLine(`Planning enabled: ${metadata.planningEnabled ? 'yes' : 'no'}`);
  outputChannel.appendLine(`Plan summary: ${metadata.planSummary}`);
  outputChannel.appendLine(`Execution target: ${metadata.executionTarget}`);
  outputChannel.appendLine(`Routing reason: ${metadata.executionReason}`);
  outputChannel.appendLine('');
  outputChannel.appendLine(prompt);

  const matchedLogic = response.matched_logic?.join(', ') || 'none';
  const tokenEstimate = response.token_estimate ?? 'unknown';
  outputChannel.appendLine('');
  outputChannel.appendLine(`[ai-gen] matched=${matchedLogic} tokens~=${tokenEstimate}`);
  outputChannel.show(true);
}

function parsePromptSections(prompt: string): Map<string, string> {
  const sections = new Map<string, string>();
  const lines = prompt.split(/\r?\n/);
  let currentSection: string | undefined;
  let currentLines: string[] = [];

  for (const line of lines) {
    const heading = line.match(/^##\s+(.+)$/);
    if (heading) {
      if (currentSection) {
        sections.set(currentSection, currentLines.join('\n').trim());
      }
      currentSection = heading[1].replace(/^Detected Intent:\s*/, 'Detected Intent');
      currentLines = heading[1].startsWith('Detected Intent:')
        ? [heading[1].replace('Detected Intent:', '').trim()]
        : [];
      continue;
    }

    if (currentSection) {
      currentLines.push(line);
    }
  }

  if (currentSection) {
    sections.set(currentSection, currentLines.join('\n').trim());
  }

  return sections;
}

function extractPromptMetadata(prompt: string, response: BackendResponse): PromptMetadata {
  return {
    detectedIntent: extractDetectedIntent(prompt),
    hasLinkedFlows: prompt.includes('## Linked Flows'),
    hasImpactedComponents: prompt.includes('## Impacted Components'),
    hasCriticalConstraints: prompt.includes('## Critical Constraints') || prompt.includes('## Constraints'),
    planningEnabled: response.planning_enabled ?? (prompt.includes('## Execution Plan') || prompt.includes('## Plan')),
    planSummary: response.plan_summary || 'Planning not required.',
    executionTarget: response.execution_target || 'preview_only',
    executionReason: response.execution_reason || 'routing metadata unavailable',
    availableTargets: response.available_targets || {}
  };
}

function formatAvailableTargets(targets: Record<string, boolean>): string {
  const entries = Object.entries(targets);
  if (entries.length === 0) {
    return 'unknown';
  }
  return entries.map(([target, available]) => `${target}=${available ? 'yes' : 'no'}`).join(', ');
}

function extractDetectedIntent(prompt: string): string {
  const match = prompt.match(/^## Detected Intent:\s*(.+)$/m);
  return match?.[1]?.trim() || 'unknown';
}

function selectedExecutionFilesForBackend(state: LastPromptState): string[] {
  const files = state.response.selected_execution_files?.length
    ? state.response.selected_execution_files
    : [state.editorContext.current_file || state.editorContext.file_path].filter(Boolean);
  return files.map((filePath) => toWorkspaceRelative(filePath, state.editorContext.workspace_root));
}

function constraintsForValidation(state: LastPromptState): string[] {
  return extractListSection(state.prompt, 'Constraints');
}

function likelyBreakpointsForValidation(state: LastPromptState): string[] {
  const hotspotFiles = (state.response.likely_bug_hotspots || [])
    .map((hotspot) => typeof hotspot.file === 'string' ? hotspot.file : '')
    .filter(Boolean)
    .map((filePath) => toWorkspaceRelative(filePath, state.editorContext.workspace_root));
  if (hotspotFiles.length > 0) {
    return Array.from(new Set(hotspotFiles));
  }
  return extractListSection(state.prompt, 'Likely Breakpoints')
    .map((line) => line.split('(')[0].trim())
    .filter(Boolean)
    .map((filePath) => toWorkspaceRelative(filePath, state.editorContext.workspace_root));
}

function extractListSection(prompt: string, sectionName: string): string[] {
  const lines = prompt.split(/\r?\n/);
  const values: string[] = [];
  let inSection = false;
  for (const line of lines) {
    const heading = line.match(/^#{1,2}\s+(.+)$/);
    if (heading) {
      if (inSection) {
        break;
      }
      inSection = heading[1].trim() === sectionName;
      continue;
    }
    if (inSection && line.trim().startsWith('- ')) {
      values.push(line.trim().slice(2).trim());
    }
  }
  return Array.from(new Set(values));
}

function toWorkspaceRelative(filePath: string, workspaceRoot: string): string {
  const normalizedFile = filePath.replace(/\\/g, '/');
  const normalizedRoot = workspaceRoot.replace(/\\/g, '/').replace(/\/$/, '');
  if (normalizedRoot && normalizedFile.startsWith(`${normalizedRoot}/`)) {
    return normalizedFile.slice(normalizedRoot.length + 1);
  }
  return normalizedFile;
}

function validationRiskLevel(driftDetected: boolean, violations: number, risks: number): string {
  if (violations > 0 || driftDetected) {
    return 'high';
  }
  if (risks > 0) {
    return 'medium';
  }
  return 'low';
}

function sessionFlowForRetry(): string {
  const flow = lastPromptState?.response.session_bias_summary?.flow;
  return typeof flow === 'string' ? flow : '';
}

async function copyLastPrompt(): Promise<string> {
  const packet = currentExecutionPacket();
  if (!packet) {
    const message = 'No ai-gen execution packet is available yet. Run Preview or load a handoff first.';
    vscode.window.showErrorMessage(message);
    return message;
  }

  await vscode.env.clipboard.writeText(packet);
  vscode.window.showInformationMessage('ai-gen execution packet copied to clipboard.');
  return 'ai-gen execution packet copied to clipboard.';
}

async function sendLastPromptToCodex(): Promise<string> {
  const packet = currentExecutionPacket();
  if (!packet) {
    const message = 'No ai-gen execution packet is available yet. Run Preview or load a handoff first.';
    vscode.window.showErrorMessage(message);
    return message;
  }

  const executionTarget = lastPromptState?.executionTarget || (lastLoadedHandoff?.stage === 'dev' ? 'codex' : 'handoff');
  const executionReason = lastPromptState?.executionReason || 'loaded from handoff';
  if (executionTarget !== 'codex') {
    const override = await vscode.window.showWarningMessage(
      `ai-gen routed this prompt to ${executionTarget} (${executionReason}). Send to Codex anyway?`,
      { modal: true },
      'Send Anyway'
    );
    if (override !== 'Send Anyway') {
      return 'Send to Codex cancelled.';
    }
  }

  const available = await isCodexCliAvailable();
  if (!available) {
    const message = 'Codex CLI was not found on PATH. Install Codex CLI or update your PATH, then try again.';
    vscode.window.showErrorMessage(message);
    return message;
  }

  const confirmation = await vscode.window.showWarningMessage(
    'Send the most recent ai-gen prompt to Codex in an integrated terminal?',
    { modal: true },
    'Send to Codex'
  );
  if (confirmation !== 'Send to Codex') {
    return 'Send to Codex cancelled.';
  }

  let snapshotMessage = '';
  try {
    await captureExecutionSnapshot();
    snapshotMessage = ' Snapshot captured for validation.';
    vscode.window.showInformationMessage('Snapshot captured for validation.');
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    snapshotMessage = ' Snapshot failed; execution continued.';
    vscode.window.showWarningMessage(`Snapshot failed; execution will continue. ${message}`);
  }

  try {
    const terminal = vscode.window.createTerminal({ name: 'ai-gen Codex' });
    terminal.show();
    terminal.sendText(`codex ${shellQuote(packet)}`);
    return `Sent to Codex terminal.${snapshotMessage}`;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    vscode.window.showErrorMessage(`Could not launch Codex terminal: ${message}`);
    return `Could not launch Codex terminal: ${message}`;
  }
}

async function captureExecutionSnapshot(): Promise<void> {
  const workspaceRoot = lastPromptState?.editorContext.workspace_root || currentWorkspaceRoot();
  if (!workspaceRoot) {
    throw new Error('No workspace root is available for execution validation.');
  }
  const selectedFiles = currentSelectedFiles(workspaceRoot);
  if (!selectedFiles.length) {
    throw new Error('No selected files are available for execution validation.');
  }
  const backendUrl = await getActiveBackendBaseUrl();
  const response = await postJson<{ baseline_hashes?: Record<string, string> }>(snapshotUrl(backendUrl), {
    repo_id: currentRepoId(),
    branch_name: currentBranchName(workspaceRoot),
    session_id: currentSessionId(),
    workspace_root: workspaceRoot,
    repo_root: workspaceRoot,
    selected_execution_files: selectedFiles,
    selected_files: selectedFiles
  });
  lastExecutionState = {
    repoId: currentRepoId(),
    branchName: currentBranchName(workspaceRoot),
    sessionId: currentSessionId(),
    workspaceRoot,
    selectedFiles,
    constraints: currentConstraints(),
    likelyBreakpoints: currentLikelyBreakpoints(workspaceRoot, selectedFiles),
    baselineHashes: response.baseline_hashes || {},
    promptMode: lastPromptState?.response.prompt_mode || 'execute',
    timestamp: new Date()
  };
}

async function snapshotLastExecution(): Promise<string> {
  try {
    await captureExecutionSnapshot();
    const message = 'Snapshot captured for validation.';
    vscode.window.showInformationMessage(message);
    return message;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    vscode.window.showWarningMessage(`Unable to capture snapshot. ${message}`);
    return `Unable to capture snapshot. ${message}`;
  }
}

async function validateLastExecution(): Promise<string> {
  if (!lastExecutionState) {
    const message = 'No execution snapshot found. Run a task first.';
    vscode.window.showInformationMessage(message);
    return message;
  }
  try {
    const backendUrl = await getActiveBackendBaseUrl();
    const response = await postJson<ExecutionValidationResponse>(validateUrl(backendUrl), {
      repo_id: lastExecutionState.repoId,
      branch_name: lastExecutionState.branchName,
      session_id: lastExecutionState.sessionId,
      workspace_root: lastExecutionState.workspaceRoot,
      repo_root: lastExecutionState.workspaceRoot,
      selected_files: lastExecutionState.selectedFiles,
      allowed_flows: lastPromptState?.response.related_flows || [],
      constraints: lastExecutionState.constraints,
      likely_breakpoints: lastExecutionState.likelyBreakpoints,
      baseline_hashes: lastExecutionState.baselineHashes,
      prompt_mode: lastExecutionState.promptMode,
      query: lastPromptState?.query || '',
      detected_flow: sessionFlowForRetry(),
      related_flows: lastPromptState?.response.related_flows || []
    });
    if (!response.execution_validation) {
      throw new Error('Backend returned an empty validation response.');
    }
    if (lastPromptState) {
      lastPromptState.response = {
        ...lastPromptState.response,
        execution_validation: response.execution_validation,
        drift_detected: Boolean(response.drift_detected),
        constraint_violations: response.constraint_violations || [],
        risky_changes: response.risky_changes || [],
        retry_required: Boolean(response.retry_required),
        retry_plan: response.retry_plan || {},
        corrected_execution_prompt: response.corrected_execution_prompt || ''
      };
    }
    const violations = response.constraint_violations?.length || 0;
    const risks = response.risky_changes?.length || 0;
    const drift = Boolean(response.drift_detected);
    const riskLevel = validationRiskLevel(drift, violations, risks);
    const summary = `Validation complete. Drift detected: ${drift ? 'yes' : 'no'}. Violations: ${violations}. Risk level: ${riskLevel}.`;
    if (drift || violations > 0 || risks > 0) {
      vscode.window.showWarningMessage(summary);
    } else {
      vscode.window.showInformationMessage(summary);
    }
    return summary;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    vscode.window.showErrorMessage(`Execution validation failed: ${message}`);
    return `Execution validation failed: ${message}`;
  }
}

async function retryLastExecution(): Promise<string> {
  const prompt = lastPromptState?.response.corrected_execution_prompt;
  if (!prompt) {
    const message = 'No corrected retry prompt is available. Validate the last execution first.';
    vscode.window.showInformationMessage(message);
    return message;
  }
  const confirmation = await vscode.window.showWarningMessage(
    'Send the corrected retry prompt to Codex?',
    { modal: true },
    'Send Retry'
  );
  if (confirmation !== 'Send Retry') {
    return 'Retry cancelled.';
  }
  const available = await isCodexCliAvailable();
  if (!available) {
    const message = 'Codex CLI was not found on PATH. Install Codex CLI or update your PATH, then try again.';
    vscode.window.showErrorMessage(message);
    return message;
  }
  try {
    const terminal = vscode.window.createTerminal({ name: 'ai-gen Codex Retry' });
    terminal.show();
    terminal.sendText(`codex ${shellQuote(prompt)}`);
    return 'Sent corrected retry prompt to Codex terminal.';
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    vscode.window.showErrorMessage(`Could not launch Codex retry terminal: ${message}`);
    return `Could not launch Codex retry terminal: ${message}`;
  }
}

async function isCodexCliAvailable(): Promise<boolean> {
  try {
    if (process.platform === 'win32') {
      await execFile('where', ['codex'], { timeout: 3000 });
    } else {
      await execFile('/bin/sh', ['-lc', 'command -v codex'], { timeout: 3000 });
    }
    return true;
  } catch {
    return false;
  }
}

function shellQuote(value: string): string {
  return `'${value.replace(/'/g, `'\\''`)}'`;
}

function parseHandoffIdFromUri(uri: vscode.Uri): string {
  const path = (uri.path || '').replace(/^\/+/, '');
  const params = new URLSearchParams(uri.query || '');
  const handoffId = (params.get('handoffId') || '').trim();
  if (path === 'loadHandoff' && handoffId) {
    return handoffId;
  }
  return '';
}

function parseStoryPromptParamsFromUri(uri: vscode.Uri): { backendUrl: string; sessionId: string } | undefined {
  const path = (uri.path || '').replace(/^\/+/, '');
  if (path !== 'loadStoryPrompt') {
    return undefined;
  }
  const params = new URLSearchParams(uri.query || '');
  const backendUrl = (params.get('backendUrl') || '').trim().replace(/\/+$/, '');
  const sessionId = (params.get('sessionId') || '').trim();
  if (!backendUrl || !sessionId) {
    return undefined;
  }
  return { backendUrl, sessionId };
}

async function loadAndShowStoryPrompt(
  backendUrl: string,
  sessionId: string,
  outputChannel: vscode.OutputChannel
): Promise<void> {
  const session = await fetchJson<StoryPlannerSession>(storyPlannerSessionUrl(backendUrl, sessionId));
  const prompt = String(session.code_generation_prompt || '').trim();
  if (!prompt) {
    throw new Error('The Story Planner session does not have a final code-generation prompt yet.');
  }

  backendResolution = {
    url: backendUrl,
    source: backendUrl.includes('localhost') || backendUrl.includes('127.0.0.1') ? 'local' : 'railway',
    healthy: true,
    mode: 'auto',
    reason: 'Loaded from Azure DevOps Story Planner link.'
  };
  backendStatus = 'connected';
  statusWarnings = [];

  const metadata: PromptMetadata = {
    detectedIntent: 'story_planner_prompt',
    hasLinkedFlows: false,
    hasImpactedComponents: false,
    hasCriticalConstraints: true,
    planningEnabled: false,
    planSummary: 'Loaded from approved AI Story Planner workflow.',
    executionTarget: 'codex',
    executionReason: 'Loaded from Azure DevOps Story Planner handoff.',
    availableTargets: { codex: true }
  };
  const response: BackendResponse = {
    optimized_prompt: prompt,
    matched_logic: ['story_planner'],
    token_estimate: Math.ceil(prompt.length / 4),
    execution_target: 'codex',
    execution_reason: 'Loaded from Azure DevOps Story Planner handoff.',
    available_targets: { codex: true },
    prompt_mode: 'execute',
    prompt_mode_reason: 'Approved story-specific code-generation prompt.',
    selected_execution_files: []
  };

  lastPromptState = {
    query: session.story?.title || session.requirement || `Story Planner session ${sessionId}`,
    prompt,
    timestamp: session.updated_at ? new Date(session.updated_at) : new Date(),
    response,
    editorContext: {
      file_path: '',
      selected_text: '',
      workspace_root: currentWorkspaceRoot(),
      open_files: [],
      current_file: '',
      branch_name: currentBranchName(currentWorkspaceRoot()),
      session_id: ideSessionId
    },
    ...metadata
  };
  lastSidebarView = 'prompt';
  await vscode.env.clipboard.writeText(prompt);
  showPromptOutput(outputChannel, prompt, response, metadata);
  sidebarProvider?.update(getSidebarState('Story Planner prompt loaded and copied.', ''));
}

function currentExecutionPacket(): string | undefined {
  if (lastSidebarView === 'handoff' && lastLoadedHandoff) {
    const packet = lastLoadedHandoff.execution_packet || lastLoadedHandoff.content?.execution_packet;
    if (typeof packet === 'string' && packet.trim()) {
      return packet;
    }
  }
  if (lastPromptState?.prompt) {
    return lastPromptState.prompt;
  }
  if (lastLoadedHandoff) {
    const packet = lastLoadedHandoff.execution_packet || lastLoadedHandoff.content?.execution_packet;
    if (typeof packet === 'string' && packet.trim()) {
      return packet;
    }
  }
  return undefined;
}

function currentWorkspaceRoot(): string {
  return lastPromptState?.editorContext.workspace_root
    || vscode.workspace.workspaceFolders?.[0]?.uri.fsPath
    || '';
}

function currentRepoId(): string {
  const repoContext = lastLoadedHandoff?.repo_context || {};
  return lastPromptState?.response.resolved_repo_id
    || firstString(repoContext, ['resolved_repo_id', 'repo_id'])
    || '';
}

function currentBranchName(workspaceRoot: string): string {
  const repoContext = lastLoadedHandoff?.repo_context || {};
  return lastPromptState?.response.resolved_branch_name
    || lastPromptState?.editorContext.branch_name
    || firstString(repoContext, ['resolved_branch_name', 'branch_name'])
    || '';
}

function currentSessionId(): string {
  return lastPromptState?.editorContext.session_id || ideSessionId;
}

function currentSelectedFiles(workspaceRoot: string): string[] {
  if (lastPromptState) {
    return selectedExecutionFilesForBackend(lastPromptState);
  }
  const selectedFiles = lastLoadedHandoff?.selected_files || lastLoadedHandoff?.content?.selected_files;
  if (Array.isArray(selectedFiles)) {
    return normalizeStringList(selectedFiles).map((filePath) => toWorkspaceRelative(filePath, workspaceRoot));
  }
  return [];
}

function currentConstraints(): string[] {
  if (lastPromptState) {
    return constraintsForValidation(lastPromptState);
  }
  return normalizeStringList(lastLoadedHandoff?.constraints);
}

function currentLikelyBreakpoints(workspaceRoot: string, selectedFiles: string[]): string[] {
  if (lastPromptState) {
    return likelyBreakpointsForValidation(lastPromptState);
  }
  return selectedFiles.map((filePath) => toWorkspaceRelative(filePath, workspaceRoot));
}

function getSidebarState(statusMessage: string, errorMessage: string): SidebarState {
  return {
    backendMode: backendResolution.mode,
    activeBackendSource: backendResolution.source,
    backendUrl: backendResolution.url || '',
    backendReason: backendResolution.reason,
    backendStatus,
    codexAvailable,
    localEnabled,
    localAvailable,
    localProvider,
    localModel,
    localBaseUrl,
    cloudEnabled,
    refinerEnabled,
    refinerProvider,
    refinerModel,
    refinerConfigured,
    warnings: statusWarnings,
    statusMessage,
    errorMessage,
    latest: latestSidebarResult()
  };
}

function latestSidebarResult(): SidebarResult | undefined {
  if (lastSidebarView === 'handoff' && lastLoadedHandoff) {
    return handoffToSidebarResult(lastLoadedHandoff);
  }
  if (lastPromptState) {
    return toSidebarResult(lastPromptState);
  }
  if (lastLoadedHandoff) {
    return handoffToSidebarResult(lastLoadedHandoff);
  }
  return undefined;
}

async function loadAndShowHandoffById(handoffId: string, outputChannel: vscode.OutputChannel): Promise<void> {
  lastHandoffRequest = { kind: 'id', handoffId };
  try {
    const baseUrl = await getActiveBackendBaseUrl();
    const handoff = await fetchJson<HandoffRecord>(handoffByIdUrl(baseUrl, handoffId));
    if (!handoff || !handoff.stage) {
      throw new Error(`No handoff found for id ${handoffId}.`);
    }
    lastLoadedHandoff = handoff;
    lastSidebarView = 'handoff';
    await showHandoffDocument(handoff, outputChannel);
    sidebarProvider?.update(getSidebarState(`Loaded handoff ${handoffId}.`, ''));
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    sidebarProvider?.update(getSidebarState(`Failed to load handoff ${handoffId}.`, message));
    vscode.window.showErrorMessage(`ai-gen handoff load failed for ${handoffId}: ${message}`);
  }
}

async function loadAndShowHandoffForWorkItem(
  workItemId: string,
  stage: string,
  outputChannel: vscode.OutputChannel
): Promise<void> {
  try {
    const baseUrl = await getActiveBackendBaseUrl();
    const response = await fetchJson<{ items?: HandoffRecord[] }>(handoffListUrl(baseUrl, workItemId, stage, 'approved'));
    const handoff = response.items?.[0];
    if (!handoff) {
      throw new Error(`No approved ${stage} handoff found for work item ${workItemId}.`);
    }
    lastHandoffRequest = { kind: 'work_item', workItemId, stage };
    lastLoadedHandoff = handoff;
    lastSidebarView = 'handoff';
    await showHandoffDocument(handoff, outputChannel);
    sidebarProvider?.update(getSidebarState(`Loaded ${stage} handoff for work item ${workItemId}.`, ''));
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    sidebarProvider?.update(getSidebarState('Failed to load work item handoff.', message));
    vscode.window.showErrorMessage(`ai-gen handoff load failed: ${message}`);
  }
}

async function showHandoffDocument(handoff: HandoffRecord, outputChannel: vscode.OutputChannel): Promise<void> {
  const content = await fetchOrRenderHandoffMarkdown(handoff);
  outputChannel.clear();
  outputChannel.appendLine(content);
  outputChannel.show(true);
  const document = await vscode.workspace.openTextDocument({
    content,
    language: 'markdown'
  });
  await vscode.window.showTextDocument(document, { preview: true });
}

async function fetchOrRenderHandoffMarkdown(handoff: HandoffRecord): Promise<string> {
  const handoffId = handoff.handoff_id;
  if (!handoffId) {
    return renderHandoffMarkdown(handoff);
  }
  try {
    const baseUrl = await getActiveBackendBaseUrl();
    const response = await fetch(handoffMarkdownUrl(baseUrl, handoffId), { method: 'GET' });
    if (response.ok) {
      const content = await response.text();
      if (content.trim()) {
        return content;
      }
    }
  } catch {
    // Fall back to local rendering.
  }
  return renderHandoffMarkdown(handoff);
}

function renderHandoffMarkdown(handoff: HandoffRecord): string {
  const content = typeof handoff.content === 'object' && handoff.content
    ? JSON.stringify(handoff.content, null, 2)
    : '{}';
  const refinement = typeof handoff.refinement === 'object' && handoff.refinement
    ? JSON.stringify(handoff.refinement, null, 2)
    : '{}';
  const repoContext = typeof handoff.repo_context === 'object' && handoff.repo_context
    ? JSON.stringify(handoff.repo_context, null, 2)
    : '{}';
  const lines = [
    `# ${String(handoff.stage || 'handoff').toUpperCase()} Handoff`,
    '',
    `- Status: ${handoff.status || 'unknown'}`,
    `- Work Item: ${handoff.work_item_id || 'unknown'}`,
    `- Pipeline: ${handoff.pipeline_id || 'unknown'}`,
    '',
    '## Summary',
    handoff.summary || 'No summary available.',
  ];
  if (handoff.constraints?.length) {
    lines.push('', '## Constraints', ...handoff.constraints.map((item) => `- ${item}`));
  }
  if (handoff.open_questions?.length) {
    lines.push('', '## Open Questions', ...handoff.open_questions.map((item) => `- ${item}`));
  }
  if (handoff.next_actions?.length) {
    lines.push('', '## Next Actions', ...handoff.next_actions.map((item) => `- ${item}`));
  }
  const executionPacket = handoff.execution_packet || (typeof handoff.content?.execution_packet === 'string' ? handoff.content.execution_packet : '');
  if (handoff.stage === 'dev' && executionPacket) {
    lines.push('', '## Execution Packet', '```text', executionPacket, '```');
  }
  const selectedFiles = Array.isArray(handoff.selected_files)
    ? handoff.selected_files
    : (Array.isArray(handoff.content?.selected_files) ? handoff.content.selected_files as string[] : []);
  if (selectedFiles.length) {
    lines.push('', '## Selected Files', ...selectedFiles.map((item) => `- ${item}`));
  }
  lines.push('', '## Stage Output', '```json', content, '```', '', '## Refinement', '```json', refinement, '```', '', '## Repo Context', '```json', repoContext, '```');
  return lines.join('\n');
}

function handoffToSidebarResult(handoff: HandoffRecord): SidebarResult {
  const content = handoff.content || {};
  const refinement = handoff.refinement || {};
  const repoContext = handoff.repo_context || {};
  const executionPacket = typeof handoff.execution_packet === 'string'
    ? handoff.execution_packet
    : typeof content.execution_packet === 'string'
      ? content.execution_packet
    : handoff.summary || 'No execution packet available.';
  return {
    query: handoff.summary || `${String(handoff.stage || 'handoff').toUpperCase()} handoff`,
    prompt: executionPacket,
    generatedAt: handoff.approved_at || handoff.created_at || 'unknown',
    loadedHandoff: handoff.handoff_id || currentLoadedHandoffLabel(),
    matchedLogic: 'handoff',
    tokenEstimate: 'n/a',
    executionTarget: handoff.stage === 'dev' ? 'execution_handoff' : `${handoff.stage || 'handoff'}_handoff`,
    executionReason: `Loaded ${handoff.status || 'draft'} handoff`,
    selectedExecutionFiles: Array.isArray(handoff.selected_files)
      ? handoff.selected_files.join('\n')
      : Array.isArray(content.selected_files)
        ? (content.selected_files as string[]).join('\n')
      : undefined,
    refinementUsed: Boolean(Object.keys(refinement).length),
    refinementProvider: undefined,
    refinementReason: undefined,
    refinedBaseFlow: toLines(refinement, ['base_flows', 'refined_base_flows', 'base_flow', 'refined_base_flow']),
    refinedVariant: toLines(refinement, ['variants', 'refined_variants', 'variant', 'refined_variant']),
    refinedSurface: toLines(refinement, ['surfaces', 'refined_surfaces', 'surface', 'refined_surface']),
    refinedFields: toLines(refinement, ['fields', 'refined_fields']),
    refinedValidations: toLines(refinement, ['validations', 'refined_validations']),
    refinedScope: toLines(refinement, ['scope_hints', 'refined_scope', 'first_pass_scope']),
    refinedActors: toLines(refinement, ['actors', 'refined_actors']),
    refinedStates: toLines(refinement, ['states', 'refined_states']),
    refinementUnknowns: normalizeStringList(handoff.open_questions).join('\n') || toLines(refinement, ['unknowns', 'refinement_unknowns']),
    refinementConfidence: firstString(refinement, ['confidence', 'refinement_confidence']),
    availableTargets: 'n/a',
    planningEnabled: false,
    planSummary: 'Loaded from approved handoff.',
    resolvedRepoId: firstString(repoContext, ['resolved_repo_id', 'repo_id']),
    resolvedBranchName: firstString(repoContext, ['resolved_branch_name', 'branch_name']),
    repoIdentityMode: firstString(repoContext, ['repo_identity_mode']),
    retrievalBiasApplied: undefined,
    sessionBiasSummary: undefined,
    constraints: normalizeStringList(handoff.constraints).join('\n'),
    plan: undefined,
    flow: toLines(refinement, ['base_flows', 'refined_base_flows', 'base_flow', 'refined_base_flow']),
    criticalSteps: normalizeStringList(handoff.next_actions).join('\n')
  };
}

function normalizeStringList(items: unknown): string[] {
  if (!Array.isArray(items)) {
    return [];
  }
  return items
    .map((item) => typeof item === 'string' ? item.trim() : '')
    .filter(Boolean);
}

function toLines(source: Record<string, unknown>, keys: string[]): string | undefined {
  for (const key of keys) {
    const value = source[key];
    if (typeof value === 'string' && value.trim()) {
      return value.trim();
    }
    if (Array.isArray(value)) {
      const lines = normalizeStringList(value);
      if (lines.length) {
        return lines.join('\n');
      }
    }
  }
  return undefined;
}

function firstString(source: Record<string, unknown>, keys: string[]): string | undefined {
  for (const key of keys) {
    const value = source[key];
    if (typeof value === 'string' && value.trim()) {
      return value.trim();
    }
  }
  return undefined;
}

function toSidebarResult(state: LastPromptState): SidebarResult {
  const sections = parsePromptSections(state.prompt);
  const response = state.response;
  const localOutput = response.local_output
    ? [
        response.local_provider ? `Provider: ${response.local_provider}` : '',
        response.local_model ? `Model: ${response.local_model}` : '',
        response.local_output
      ].filter(Boolean).join('\n')
    : undefined;

  return {
    query: state.query,
    prompt: state.prompt,
    generatedAt: state.timestamp.toLocaleString(),
    loadedHandoff: currentLoadedHandoffLabel(),
    matchedLogic: response.matched_logic?.join(', ') || 'none',
    tokenEstimate: String(response.token_estimate ?? 'unknown'),
    executionTarget: state.executionTarget,
    executionReason: state.executionReason,
    promptMode: response.prompt_mode,
    promptModeReason: response.prompt_mode_reason,
    executionConfidence: response.execution_confidence_level
      ? `${response.execution_confidence_level} (${response.execution_confidence ?? 0})`
      : undefined,
    executionConfidenceSignals: response.execution_confidence_signals?.join('\n'),
    selectedExecutionFiles: response.selected_execution_files?.join('\n'),
    driftDetected: response.drift_detected,
    validationDriftScore: typeof response.execution_validation?.drift_score === 'number'
      ? String(response.execution_validation.drift_score)
      : undefined,
    constraintViolations: response.constraint_violations?.join('\n'),
    riskyChanges: response.risky_changes?.join('\n'),
    validationSummary: typeof response.execution_validation?.summary === 'string'
      ? response.execution_validation.summary
      : undefined,
    retryRequired: response.retry_required,
    retryReason: typeof response.retry_plan?.reason === 'string' ? response.retry_plan.reason : undefined,
    retryStrategy: typeof response.retry_plan?.strategy === 'string' ? response.retry_plan.strategy : undefined,
    correctedExecutionPrompt: response.corrected_execution_prompt,
    semanticMappingApplied: response.semantic_mapping_applied,
    refinementUsed: response.refinement_used,
    refinementSource: response.refinement_source,
    refinementProvider: response.refinement_provider,
    refinementReason: response.refinement_reason,
    phiUsed: response.phi_used,
    phiStatus: response.phi_status,
    refinedBaseFlow: response.refined_base_flows?.join('\n') || response.refined_base_flow,
    refinedVariant: response.refined_variants?.join('\n') || response.refined_variant,
    refinedSurface: response.refined_surfaces?.join('\n') || response.refined_surface,
    refinedFields: response.refined_fields?.join('\n'),
    refinedValidations: response.refined_validations?.join('\n'),
    refinedScope: response.refined_scope?.join('\n'),
    refinedActors: response.refined_actors?.join('\n'),
    refinedStates: response.refined_states?.join('\n'),
    refinementUnknowns: response.refinement_unknowns?.join('\n'),
    refinementConfidence: response.refinement_confidence,
    availableTargets: formatAvailableTargets(state.availableTargets),
    planningEnabled: state.planningEnabled,
    planSummary: state.planSummary,
    resolvedRepoId: response.resolved_repo_id,
    resolvedBranchName: response.resolved_branch_name,
    repoIdentityMode: response.repo_identity_mode,
    retrievalBiasApplied: response.retrieval_bias_applied,
    sessionBiasSummary: response.session_bias_summary
      ? JSON.stringify(response.session_bias_summary, null, 2)
      : undefined,
    linkedFlows: sections.get('Linked Flows'),
    impactedComponents: sections.get('Impacted Components'),
    constraints: sections.get('Critical Constraints') || sections.get('Constraints'),
    plan: sections.get('Execution Plan') || sections.get('Plan'),
    flow: sections.get('Flow') || sections.get('Composed Flow'),
    criticalSteps: sections.get('Critical Steps') || sections.get('Importance-Aware Flow'),
    localOutput
  };
}

function currentLoadedHandoffLabel(): string | undefined {
  if (!lastHandoffRequest) {
    return undefined;
  }
  if (lastHandoffRequest.kind === 'id') {
    return lastHandoffRequest.handoffId;
  }
  return `${lastHandoffRequest.workItemId} / ${lastHandoffRequest.stage}`;
}

async function refreshLastHandoff(outputChannel: vscode.OutputChannel): Promise<string> {
  if (!lastHandoffRequest) {
    const handoffId = await vscode.window.showInputBox({
      title: 'ai-gen: Load Handoff by ID',
      prompt: 'Enter the handoff id',
      placeHolder: '123:dev:v1',
      ignoreFocusOut: true
    });
    if (!handoffId) {
      return 'Load handoff cancelled.';
    }
    await loadAndShowHandoffById(handoffId, outputChannel);
    return `Loaded handoff ${handoffId}.`;
  }
  try {
    if (lastHandoffRequest.kind === 'id') {
      await loadAndShowHandoffById(lastHandoffRequest.handoffId, outputChannel);
      return `Refreshed handoff ${lastHandoffRequest.handoffId}.`;
    }
    await loadAndShowHandoffForWorkItem(lastHandoffRequest.workItemId, lastHandoffRequest.stage, outputChannel);
    return `Refreshed ${lastHandoffRequest.stage} handoff for work item ${lastHandoffRequest.workItemId}.`;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    vscode.window.showWarningMessage(`Unable to refresh handoff state. ${message}`);
    return `Unable to refresh handoff state. ${message}`;
  }
}

async function reloadLastPromptFromBackend(outputChannel: vscode.OutputChannel): Promise<string> {
  if (!lastPromptState) {
    const message = 'No pipeline context is loaded yet. Run Preview first.';
    vscode.window.showInformationMessage(message);
    return message;
  }
  try {
    const includeSelection = Boolean(lastPromptState.editorContext.selected_text);
    const includeFile = Boolean(lastPromptState.editorContext.file_path || lastPromptState.editorContext.current_file);
    const refreshed = await requestAndStorePrompt(
      lastPromptState.query,
      { includeSelection, includeFile }
    );
    showPromptOutput(outputChannel, refreshed.prompt, refreshed.response, refreshed);
    return 'Pipeline context reloaded from backend.';
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    vscode.window.showWarningMessage(`Unable to refresh pipeline state. ${message}`);
    return `Unable to refresh pipeline state. ${message}`;
  }
}
