import * as childProcess from 'child_process';
import * as util from 'util';
import * as vscode from 'vscode';
import {
  BackendResolution,
  capabilitiesUrl,
  contextUrl,
  resolveBackendUrl,
  snapshotUrl,
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

let lastPromptState: LastPromptState | undefined;
let lastExecutionState: LastExecutionState | undefined;
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
  if (!lastPromptState?.prompt) {
    const message = 'No ai-gen prompt is available yet. Run Preview first.';
    vscode.window.showErrorMessage(message);
    return message;
  }

  await vscode.env.clipboard.writeText(lastPromptState.prompt);
  vscode.window.showInformationMessage('ai-gen prompt copied to clipboard.');
  return 'ai-gen prompt copied to clipboard.';
}

async function sendLastPromptToCodex(): Promise<string> {
  if (!lastPromptState?.prompt) {
    const message = 'No ai-gen prompt is available yet. Run Preview first.';
    vscode.window.showErrorMessage(message);
    return message;
  }

  if (lastPromptState.executionTarget !== 'codex') {
    const override = await vscode.window.showWarningMessage(
      `ai-gen routed this prompt to ${lastPromptState.executionTarget} (${lastPromptState.executionReason}). Send to Codex anyway?`,
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
    terminal.sendText(`codex ${shellQuote(lastPromptState.prompt)}`);
    return `Sent to Codex terminal.${snapshotMessage}`;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    vscode.window.showErrorMessage(`Could not launch Codex terminal: ${message}`);
    return `Could not launch Codex terminal: ${message}`;
  }
}

async function captureExecutionSnapshot(): Promise<void> {
  if (!lastPromptState) {
    throw new Error('No prompt is available to snapshot.');
  }
  const workspaceRoot = lastPromptState.editorContext.workspace_root;
  if (!workspaceRoot) {
    throw new Error('No workspace root is available for execution validation.');
  }
  const selectedFiles = selectedExecutionFilesForBackend(lastPromptState);
  const backendUrl = await getActiveBackendBaseUrl();
  const response = await postJson<{ baseline_hashes?: Record<string, string> }>(snapshotUrl(backendUrl), {
    repo_id: lastPromptState.response.resolved_repo_id,
    branch_name: lastPromptState.response.resolved_branch_name || lastPromptState.editorContext.branch_name,
    session_id: lastPromptState.editorContext.session_id,
    workspace_root: workspaceRoot,
    repo_root: workspaceRoot,
    selected_execution_files: selectedFiles,
    selected_files: selectedFiles
  });
  lastExecutionState = {
    repoId: lastPromptState.response.resolved_repo_id || '',
    branchName: lastPromptState.response.resolved_branch_name || lastPromptState.editorContext.branch_name,
    sessionId: lastPromptState.editorContext.session_id,
    workspaceRoot,
    selectedFiles,
    constraints: constraintsForValidation(lastPromptState),
    likelyBreakpoints: likelyBreakpointsForValidation(lastPromptState),
    baselineHashes: response.baseline_hashes || {},
    promptMode: lastPromptState.response.prompt_mode || 'execute',
    timestamp: new Date()
  };
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
    warnings: statusWarnings,
    statusMessage,
    errorMessage,
    latest: lastPromptState ? toSidebarResult(lastPromptState) : undefined
  };
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
