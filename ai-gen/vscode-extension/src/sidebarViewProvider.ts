import * as vscode from 'vscode';

export type SidebarRequestOptions = {
  includeSelection: boolean;
  includeFile: boolean;
};

export type SidebarState = {
  backendMode: string;
  activeBackendSource: string;
  backendUrl: string;
  backendReason: string;
  backendStatus: string;
  codexAvailable: boolean;
  localEnabled: boolean;
  localAvailable: boolean;
  localProvider: string;
  localModel: string;
  localBaseUrl: string;
  cloudEnabled: boolean;
  refinerEnabled: boolean;
  refinerProvider: string;
  refinerModel: string;
  refinerConfigured: boolean;
  warnings: string[];
  statusMessage: string;
  errorMessage: string;
  latest?: SidebarResult;
};

export type SidebarResult = {
  query: string;
  prompt: string;
  generatedAt: string;
  loadedHandoff?: string;
  matchedLogic: string;
  tokenEstimate: string;
  executionTarget: string;
  executionReason: string;
  promptMode?: string;
  promptModeReason?: string;
  executionConfidence?: string;
  executionConfidenceSignals?: string;
  selectedExecutionFiles?: string;
  driftDetected?: boolean;
  validationDriftScore?: string;
  constraintViolations?: string;
  riskyChanges?: string;
  validationSummary?: string;
  retryRequired?: boolean;
  retryReason?: string;
  retryStrategy?: string;
  correctedExecutionPrompt?: string;
  semanticMappingApplied?: boolean;
  refinementUsed?: boolean;
  refinementSource?: string;
  refinementProvider?: string;
  refinementReason?: string;
  phiUsed?: boolean;
  phiStatus?: string;
  refinedBaseFlow?: string;
  refinedVariant?: string;
  refinedSurface?: string;
  refinedFields?: string;
  refinedValidations?: string;
  refinedScope?: string;
  refinedActors?: string;
  refinedStates?: string;
  refinementUnknowns?: string;
  refinementConfidence?: string;
  availableTargets: string;
  planningEnabled: boolean;
  planSummary: string;
  resolvedRepoId?: string;
  resolvedBranchName?: string;
  repoIdentityMode?: string;
  retrievalBiasApplied?: boolean;
  sessionBiasSummary?: string;
  linkedFlows?: string;
  impactedComponents?: string;
  constraints?: string;
  plan?: string;
  flow?: string;
  criticalSteps?: string;
  localOutput?: string;
};

type SidebarHandlers = {
  previewTask(query: string, options: SidebarRequestOptions): Promise<SidebarState>;
  explainTask(options: SidebarRequestOptions): Promise<SidebarState>;
  copyPrompt(): Promise<SidebarState>;
  sendToCodex(): Promise<SidebarState>;
  refreshHandoff(): Promise<SidebarState>;
  reloadPipeline(): Promise<SidebarState>;
  snapshotExecution(): Promise<SidebarState>;
  validateExecution(): Promise<SidebarState>;
  retryExecution(): Promise<SidebarState>;
  checkBackend(): Promise<SidebarState>;
  refreshStatus(): Promise<SidebarState>;
  getState(): SidebarState;
};

export class AiGenSidebarViewProvider implements vscode.WebviewViewProvider {
  public static readonly viewType = 'aiGen.sidebar';

  private view?: vscode.WebviewView;

  public constructor(
    private readonly extensionUri: vscode.Uri,
    private readonly handlers: SidebarHandlers
  ) {}

  public resolveWebviewView(webviewView: vscode.WebviewView): void {
    this.view = webviewView;
    webviewView.webview.options = {
      enableScripts: true,
      localResourceRoots: [this.extensionUri]
    };
    webviewView.webview.html = this.renderHtml(webviewView.webview);
    this.postState(this.handlers.getState());

    webviewView.webview.onDidReceiveMessage(async (message) => {
      try {
        await this.handleMessage(message);
      } catch (error) {
        const messageText = error instanceof Error ? error.message : String(error);
        this.postState({
          ...this.handlers.getState(),
          errorMessage: messageText,
          statusMessage: 'Request failed.'
        });
        vscode.window.showErrorMessage(messageText);
      }
    });
  }

  public update(state: SidebarState): void {
    this.postState(state);
  }

  private async handleMessage(message: { type: string; query?: string; includeSelection?: boolean; includeFile?: boolean }) {
    const options = {
      includeSelection: message.includeSelection !== false,
      includeFile: message.includeFile !== false
    };

    this.postState({
      ...this.handlers.getState(),
      statusMessage: 'Working...',
      errorMessage: ''
    });

    let state: SidebarState;
    switch (message.type) {
      case 'previewTask':
        state = await this.handlers.previewTask((message.query || '').trim(), options);
        break;
      case 'explainTask':
        state = await this.handlers.explainTask(options);
        break;
      case 'copyPrompt':
        state = await this.handlers.copyPrompt();
        break;
      case 'sendToCodex':
        state = await this.handlers.sendToCodex();
        break;
      case 'refreshHandoff':
        state = await this.handlers.refreshHandoff();
        break;
      case 'reloadPipeline':
        state = await this.handlers.reloadPipeline();
        break;
      case 'snapshot':
        state = await this.handlers.snapshotExecution();
        break;
      case 'validateExecution':
        state = await this.handlers.validateExecution();
        break;
      case 'retryExecution':
        state = await this.handlers.retryExecution();
        break;
      case 'checkBackend':
        state = await this.handlers.checkBackend();
        break;
      case 'refreshStatus':
        state = await this.handlers.refreshStatus();
        break;
      default:
        state = {
          ...this.handlers.getState(),
          errorMessage: `Unknown sidebar action: ${message.type}`,
          statusMessage: 'Unknown action.'
        };
    }
    this.postState(state);
  }

  private postState(state: SidebarState): void {
    this.view?.webview.postMessage({ type: 'state', state });
  }

  private renderHtml(webview: vscode.Webview): string {
    const nonce = getNonce();
    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src ${webview.cspSource} 'unsafe-inline'; script-src 'nonce-${nonce}';">
  <title>ai-gen</title>
  <style>
    body { color: var(--vscode-foreground); background: var(--vscode-sideBar-background); font-family: var(--vscode-font-family); margin: 0; padding: 12px; }
    h1 { font-size: 18px; margin: 0 0 10px; }
    h2 { font-size: 13px; margin: 16px 0 8px; color: var(--vscode-descriptionForeground); text-transform: uppercase; letter-spacing: 0; }
    textarea { width: 100%; min-height: 86px; box-sizing: border-box; resize: vertical; color: var(--vscode-input-foreground); background: var(--vscode-input-background); border: 1px solid var(--vscode-input-border); border-radius: 4px; padding: 8px; }
    button { margin: 4px 4px 4px 0; padding: 6px 8px; color: var(--vscode-button-foreground); background: var(--vscode-button-background); border: 0; border-radius: 4px; cursor: pointer; }
    button.secondary { color: var(--vscode-button-secondaryForeground); background: var(--vscode-button-secondaryBackground); }
    button:hover { background: var(--vscode-button-hoverBackground); }
    label { display: block; margin: 6px 0; }
    .status { border: 1px solid var(--vscode-sideBarSectionHeader-border); border-radius: 6px; padding: 8px; background: var(--vscode-editor-background); }
    .meta { display: grid; grid-template-columns: auto 1fr; gap: 4px 8px; }
    .key { color: var(--vscode-descriptionForeground); }
    .message { margin-top: 8px; color: var(--vscode-descriptionForeground); }
    .error { color: var(--vscode-errorForeground); white-space: pre-wrap; }
    pre { white-space: pre-wrap; word-break: break-word; background: var(--vscode-textCodeBlock-background); padding: 8px; border-radius: 6px; max-height: 240px; overflow: auto; }
    details { margin: 8px 0; border-top: 1px solid var(--vscode-sideBarSectionHeader-border); padding-top: 8px; }
    summary { cursor: pointer; font-weight: 600; }
    .empty { color: var(--vscode-descriptionForeground); font-style: italic; }
    .card { border: 1px solid var(--vscode-sideBarSectionHeader-border); border-radius: 6px; padding: 8px; background: var(--vscode-editor-background); margin-top: 12px; }
    .pill { display: inline-block; padding: 2px 8px; border-radius: 999px; background: var(--vscode-badge-background); color: var(--vscode-badge-foreground); margin-left: 6px; }
  </style>
</head>
<body>
  <h1>ai-gen</h1>
  <section class="status">
    <div class="meta">
      <span class="key">Backend</span><span id="backendStatus">unknown</span>
      <span class="key">Backend Mode</span><span id="backendMode">auto</span>
      <span class="key">Active Backend</span><span id="activeBackend">none</span>
      <span class="key">Backend URL</span><span id="backendUrl">not available</span>
      <span class="key">Backend Reason</span><span id="backendReason">not resolved</span>
      <span class="key">Codex</span><span id="codexStatus">unknown</span>
      <span class="key">Local</span><span id="localStatus">unknown</span>
      <span class="key">Ollama</span><span id="ollamaStatus">unknown</span>
      <span class="key">Model</span><span id="modelStatus">unknown</span>
      <span class="key">Base URL</span><span id="baseUrlStatus">unknown</span>
      <span class="key">Cloud</span><span id="cloudStatus">unknown</span>
      <span class="key">Refiner</span><span id="refinerStatus">unknown</span>
      <span class="key">Provider</span><span id="refinerProviderStatus">unknown</span>
      <span class="key">Refiner Model</span><span id="refinerModelStatus">unknown</span>
      <span class="key">Configured</span><span id="refinerConfiguredStatus">unknown</span>
    </div>
    <div id="warnings"></div>
    <div id="statusMessage" class="message"></div>
    <div id="errorMessage" class="error"></div>
  </section>

  <h2>Task</h2>
  <textarea id="query" placeholder="Add OTP login"></textarea>
  <label><input id="includeSelection" type="checkbox" checked> Include current selection</label>
  <label><input id="includeFile" type="checkbox" checked> Include current file</label>
  <div>
    <button id="preview">Preview</button>
    <button id="explain" class="secondary">Explain</button>
    <button id="copy" class="secondary">Copy Packet</button>
    <button id="send">Send to Codex</button>
    <button id="refreshHandoff" class="secondary">Load / Refresh Handoff</button>
    <button id="reloadPipeline" class="secondary">Refresh</button>
    <button id="snapshot" class="secondary">Snapshot</button>
    <button id="validate" class="secondary">Validate Last Execution</button>
    <button id="retry" class="secondary">Retry Execution</button>
    <button id="check" class="secondary">Check Backend</button>
  </div>

  <h2>Execution</h2>
  <section id="result" class="empty">No prompt generated yet.</section>

  <script nonce="${nonce}">
    const vscode = acquireVsCodeApi();
    const $ = (id) => document.getElementById(id);

    function options() {
      return {
        includeSelection: $('includeSelection').checked,
        includeFile: $('includeFile').checked
      };
    }

    function post(type) {
      vscode.postMessage({ type, query: $('query').value, ...options() });
    }

    $('preview').addEventListener('click', () => post('previewTask'));
    $('explain').addEventListener('click', () => post('explainTask'));
    $('copy').addEventListener('click', () => post('copyPrompt'));
    $('send').addEventListener('click', () => post('sendToCodex'));
    $('refreshHandoff').addEventListener('click', () => post('refreshHandoff'));
    $('reloadPipeline').addEventListener('click', () => post('reloadPipeline'));
    $('snapshot').addEventListener('click', () => post('snapshot'));
    $('validate').addEventListener('click', () => post('validateExecution'));
    $('retry').addEventListener('click', () => post('retryExecution'));
    $('check').addEventListener('click', () => post('checkBackend'));

    window.addEventListener('message', (event) => {
      if (event.data?.type !== 'state') return;
      renderState(event.data.state);
    });

    function renderState(state) {
      $('backendStatus').textContent = state.backendStatus === 'connected' ? 'Connected' : 'Disconnected';
      $('backendMode').textContent = state.backendMode || 'auto';
      $('activeBackend').textContent = state.activeBackendSource || 'none';
      $('backendUrl').textContent = state.backendUrl || 'Not available';
      $('backendReason').textContent = state.backendReason || '';
      $('codexStatus').textContent = state.codexAvailable ? 'Available' : 'Unavailable';
      $('localStatus').textContent = state.localEnabled ? 'Enabled' : 'Disabled';
      $('ollamaStatus').textContent = state.localProvider === 'ollama'
        ? (state.localAvailable ? 'Reachable' : 'Unreachable')
        : 'Not configured';
      $('modelStatus').textContent = state.localModel || 'Not configured';
      $('baseUrlStatus').textContent = state.localBaseUrl || 'Not configured';
      $('cloudStatus').textContent = state.cloudEnabled ? 'Enabled' : 'Disabled';
      $('refinerStatus').textContent = state.refinerEnabled ? 'Enabled' : 'Disabled';
      $('refinerProviderStatus').textContent = state.refinerProvider || 'Not configured';
      $('refinerModelStatus').textContent = state.refinerModel || 'Not configured';
      $('refinerConfiguredStatus').textContent = state.refinerConfigured ? 'Yes' : 'No';
      $('warnings').innerHTML = renderWarnings(state.warnings || []);
      $('statusMessage').textContent = state.statusMessage || '';
      $('errorMessage').textContent = state.errorMessage || '';
      const backendConnected = state.backendStatus === 'connected';
      $('preview').disabled = !backendConnected;
      $('explain').disabled = !backendConnected;
      $('refreshHandoff').disabled = !backendConnected;
      $('reloadPipeline').disabled = !backendConnected;
      $('snapshot').disabled = !backendConnected;
      $('validate').disabled = !backendConnected;
      $('retry').disabled = !backendConnected;
      $('check').disabled = false;

      if (!state.latest) {
        $('result').className = 'empty';
        $('result').textContent = 'No prompt generated yet.';
        return;
      }

      const result = state.latest;
      $('query').value = result.query || $('query').value;
      $('result').className = '';
      $('result').innerHTML = [
        summary(result),
        packet(result),
        validation(result),
        detail('Refinement', refinement(result), true),
        detail('Open Questions', result.refinementUnknowns),
        detail('Repo Status', repoStatus(result), false),
        detail('Final Execution Packet', result.prompt, true),
        detail('Extra Context', extraContext(result), false)
      ].join('');
    }

    function summary(result) {
      return '<div class="card"><div class="meta">' +
        row('Query', esc(result.query)) +
        row('Loaded Handoff', esc(result.loadedHandoff || 'none')) +
        row('Execution Target', esc(result.executionTarget)) +
        row('Prompt Mode', esc(result.promptMode || 'unknown')) +
        row('Execution Confidence', esc(result.executionConfidence || 'unknown')) +
        row('Selected Files', esc(result.selectedExecutionFiles || 'not selected')) +
        '</div></div>';
    }

    function packet(result) {
      return '<div class="card"><strong>Execution packet</strong><pre>' + esc(result.prompt || '') + '</pre></div>';
    }

    function validation(result) {
      const lines = [];
      lines.push('Drift: ' + (result.driftDetected ? 'yes' : 'no'));
      if (result.validationDriftScore) lines.push('Drift score: ' + result.validationDriftScore);
      if (result.validationSummary) lines.push(result.validationSummary);
      if (result.constraintViolations) lines.push('Constraint violations:\\n' + result.constraintViolations);
      if (result.riskyChanges) lines.push('Risky changes:\\n' + result.riskyChanges);
      if (result.retryRequired) lines.push('Retry recommended: yes');
      if (result.retryReason) lines.push('Retry reason: ' + result.retryReason);
      if (!lines.length) return '';
      return '<div class="card"><strong>Validation result</strong><pre>' + esc(lines.join('\\n\\n')) + '</pre></div>';
    }

    function row(key, value) {
      return '<span class="key">' + key + '</span><span>' + value + '</span>';
    }

    function detail(title, content, open) {
      if (!content) return '';
      return '<details ' + (open ? 'open' : '') + '><summary>' + title + '</summary><pre>' + esc(content) + '</pre></details>';
    }

    function refinement(result) {
      const lines = [];
      const hasRefinement = result.refinementUsed
        || result.semanticMappingApplied
        || result.refinedVariant
        || result.refinedSurface
        || result.refinedFields
        || result.refinedValidations
        || result.refinementUnknowns;
      if (!hasRefinement) return '';
      lines.push('Semantic Refinement Status: ' + (result.semanticMappingApplied ? 'Applied' : 'Not Applied'));
      if (result.refinementSource) lines.push('Source: ' + result.refinementSource);
      if (result.phiStatus) lines.push('Phi: ' + result.phiStatus);
      if (result.refinementProvider) lines.push('Provider: ' + result.refinementProvider);
      if (result.refinementConfidence) lines.push('Confidence: ' + result.refinementConfidence);
      if (result.refinementReason) lines.push('Reason: ' + result.refinementReason);
      if (result.refinedBaseFlow) lines.push('Flows:\n' + result.refinedBaseFlow);
      if (result.refinedVariant) lines.push('Variants:\n' + result.refinedVariant);
      if (result.refinedSurface) lines.push('Surfaces:\n' + result.refinedSurface);
      if (result.refinedFields) lines.push('Fields:\n' + result.refinedFields);
      if (result.refinedValidations) lines.push('Validations:\n' + result.refinedValidations);
      if (result.refinedActors) lines.push('Actors:\n' + result.refinedActors);
      if (result.refinedStates) lines.push('States:\n' + result.refinedStates);
      return lines.join('\n');
    }

    function repoStatus(result) {
      const lines = [];
      lines.push('Backend: ' + (result.executionTarget ? 'ready' : 'unknown'));
      if (result.resolvedRepoId) lines.push('Repo ID: ' + result.resolvedRepoId);
      if (result.resolvedBranchName) lines.push('Branch: ' + result.resolvedBranchName);
      if (result.repoIdentityMode) lines.push('Identity: ' + result.repoIdentityMode);
      lines.push('Retrieval bias: ' + (result.retrievalBiasApplied ? 'applied' : 'not applied'));
      if (result.sessionBiasSummary) lines.push(result.sessionBiasSummary);
      return lines.join('\n');
    }

    function extraContext(result) {
      const lines = [];
      if (result.flow) lines.push('Flow:\n' + result.flow);
      if (result.linkedFlows) lines.push('Linked flows:\n' + result.linkedFlows);
      if (result.impactedComponents) lines.push('Impacted components:\n' + result.impactedComponents);
      if (result.constraints) lines.push('Constraints:\n' + result.constraints);
      if (result.plan) lines.push('Plan:\n' + result.plan);
      if (result.criticalSteps) lines.push('Critical steps:\n' + result.criticalSteps);
      if (result.localOutput) lines.push('Local output:\n' + result.localOutput);
      if (result.executionConfidenceSignals) lines.push('Confidence signals:\n' + result.executionConfidenceSignals);
      if (result.correctedExecutionPrompt) lines.push('Corrected retry packet:\n' + result.correctedExecutionPrompt);
      return lines.join('\n\n');
    }

    function renderWarnings(warnings) {
      if (!warnings.length) return '';
      return '<details open><summary>Warnings</summary><pre>' + esc(warnings.join('\\n')) + '</pre></details>';
    }

    function esc(value) {
      return String(value || '').replace(/[&<>"']/g, (char) => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
      }[char]));
    }

    post('refreshStatus');
  </script>
</body>
</html>`;
  }
}

function getNonce(): string {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  let nonce = '';
  for (let i = 0; i < 32; i++) {
    nonce += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return nonce;
}
