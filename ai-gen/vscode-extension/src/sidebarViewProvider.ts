import * as vscode from 'vscode';

export type SidebarRequestOptions = {
  includeSelection: boolean;
  includeFile: boolean;
};

export type SidebarState = {
  backendStatus: string;
  codexAvailable: boolean;
  localEnabled: boolean;
  localAvailable: boolean;
  localProvider: string;
  localModel: string;
  localBaseUrl: string;
  cloudEnabled: boolean;
  warnings: string[];
  statusMessage: string;
  errorMessage: string;
  latest?: SidebarResult;
};

export type SidebarResult = {
  query: string;
  prompt: string;
  generatedAt: string;
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
  </style>
</head>
<body>
  <h1>ai-gen</h1>
  <section class="status">
    <div class="meta">
      <span class="key">Backend</span><span id="backendStatus">unknown</span>
      <span class="key">Codex</span><span id="codexStatus">unknown</span>
      <span class="key">Local</span><span id="localStatus">unknown</span>
      <span class="key">Ollama</span><span id="ollamaStatus">unknown</span>
      <span class="key">Model</span><span id="modelStatus">unknown</span>
      <span class="key">Base URL</span><span id="baseUrlStatus">unknown</span>
      <span class="key">Cloud</span><span id="cloudStatus">unknown</span>
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
    <button id="copy" class="secondary">Copy Prompt</button>
    <button id="send">Send to Codex</button>
    <button id="validate" class="secondary">Validate Last Execution</button>
    <button id="retry" class="secondary">Retry Execution</button>
    <button id="check" class="secondary">Check Backend</button>
    <button id="refresh" class="secondary">Refresh Status</button>
  </div>

  <h2>Result</h2>
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
    $('validate').addEventListener('click', () => post('validateExecution'));
    $('retry').addEventListener('click', () => post('retryExecution'));
    $('check').addEventListener('click', () => post('checkBackend'));
    $('refresh').addEventListener('click', () => post('refreshStatus'));

    window.addEventListener('message', (event) => {
      if (event.data?.type !== 'state') return;
      renderState(event.data.state);
    });

    function renderState(state) {
      $('backendStatus').textContent = state.backendStatus === 'connected' ? 'Connected' : 'Disconnected';
      $('codexStatus').textContent = state.codexAvailable ? 'Available' : 'Unavailable';
      $('localStatus').textContent = state.localEnabled ? 'Enabled' : 'Disabled';
      $('ollamaStatus').textContent = state.localProvider === 'ollama'
        ? (state.localAvailable ? 'Reachable' : 'Unreachable')
        : 'Not configured';
      $('modelStatus').textContent = state.localModel || 'Not configured';
      $('baseUrlStatus').textContent = state.localBaseUrl || 'Not configured';
      $('cloudStatus').textContent = state.cloudEnabled ? 'Enabled' : 'Disabled';
      $('warnings').innerHTML = renderWarnings(state.warnings || []);
      $('statusMessage').textContent = state.statusMessage || '';
      $('errorMessage').textContent = state.errorMessage || '';
      const backendConnected = state.backendStatus === 'connected';
      $('preview').disabled = !backendConnected;
      $('explain').disabled = !backendConnected;
      $('validate').disabled = !backendConnected;
      $('retry').disabled = !backendConnected;
      $('check').disabled = false;
      $('refresh').disabled = false;

      if (!state.latest) {
        $('result').className = 'empty';
        $('result').textContent = 'No prompt generated yet.';
        return;
      }

      const result = state.latest;
      $('query').value = result.query || $('query').value;
      $('result').className = '';
      $('result').innerHTML = [
        meta(result),
        detail('Flow', result.flow),
        detail('Linked Flows', result.linkedFlows),
        detail('Impacted Components', result.impactedComponents),
        detail('Critical Constraints', result.constraints),
        detail('Plan', result.plan),
        detail('Critical Steps', result.criticalSteps),
        detail('Local Output', result.localOutput),
        detail('Final Codex Prompt', result.prompt, true)
      ].join('');
    }

    function meta(result) {
      return '<div class="meta">' +
        row('Query', esc(result.query)) +
        row('Execution Target', esc(result.executionTarget)) +
        row('Routing Reason', esc(result.executionReason)) +
        row('Prompt Mode', esc(result.promptMode || 'unknown')) +
        row('Prompt Mode Reason', esc(result.promptModeReason || 'unknown')) +
        row('Execution Confidence', esc(result.executionConfidence || 'unknown')) +
        row('Drift Detected', result.driftDetected ? 'yes' : 'no') +
        row('Drift Score', esc(result.validationDriftScore || '0')) +
        row('Retry Recommended', result.retryRequired ? 'yes' : 'no') +
        row('Retry Reason', esc(result.retryReason || 'none')) +
        row('Retry Strategy', esc(result.retryStrategy || 'none')) +
        row('Token Estimate', esc(result.tokenEstimate)) +
        row('Matched Logic', esc(result.matchedLogic)) +
        row('Repo ID', esc(result.resolvedRepoId || 'not resolved')) +
        row('Branch', esc(result.resolvedBranchName || 'not resolved')) +
        row('Repo Identity', esc(result.repoIdentityMode || 'unknown')) +
        row('Retrieval Bias', result.retrievalBiasApplied ? 'applied' : 'not applied') +
        row('Planning Enabled', result.planningEnabled ? 'yes' : 'no') +
        row('Plan Summary', esc(result.planSummary)) +
        '</div>' +
        detail('Selected Execution Files', result.selectedExecutionFiles) +
        detail('Execution Confidence Signals', result.executionConfidenceSignals) +
        detail('Execution Validation', result.validationSummary) +
        detail('Constraint Violations', result.constraintViolations) +
        detail('Risky Changes', result.riskyChanges) +
        detail('Corrected Execution Prompt', result.correctedExecutionPrompt) +
        detail('Session Bias Summary', result.sessionBiasSummary);
    }

    function row(key, value) {
      return '<span class="key">' + key + '</span><span>' + value + '</span>';
    }

    function detail(title, content, open) {
      if (!content) return '';
      return '<details ' + (open ? 'open' : '') + '><summary>' + title + '</summary><pre>' + esc(content) + '</pre></details>';
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
