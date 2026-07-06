import * as vscode from 'vscode';

export type PlannerTask = {
  id: string;
  title: string;
  description: string;
  estimated_effort?: string;
  status: 'pending' | 'creating' | 'created' | 'failed';
  azure_work_item_id?: number | null;
  error?: string | null;
};

export type PlannerSession = {
  session_id: string;
  requirement: string;
  current_stage: 'refined_story' | 'acceptance_criteria' | 'tasks' | 'azure_devops_creation' | 'success';
  story: {
    title: string;
    description: string;
    business_value: string;
  };
  acceptance_criteria: string[];
  tasks: PlannerTask[];
  code_generation_prompt: string;
  question: string;
  user_input_hint: string;
  story_approved: boolean;
  acceptance_approved: boolean;
  tasks_approved: boolean;
  created_story_id?: number | null;
  created_story_status?: 'pending' | 'creating' | 'created' | 'failed';
  created_story_error?: string | null;
  created_tasks: Array<{ title: string; status: string; azure_work_item_id?: number | null; error?: string }>;
  created_summary?: {
    story?: { azure_work_item_id?: number | null; status?: string };
    tasks?: Array<{ title: string; status: string; azure_work_item_id?: number | null; error?: string }>;
  };
  error_message?: string;
  updated_at?: string;
};

export type PlannerViewState = {
  workspaceName: string;
  backendStatus: string;
  backendUrl: string;
  backendSource?: string;
  backendReason?: string;
  currentFileName?: string;
  currentBranch?: string;
  lastSyncLabel?: string;
  loading: boolean;
  loadingMessage: string;
  errorMessage: string;
  recentEngineeringPackages: string[];
  session?: PlannerSession;
  executionWorkspace?: ExecutionWorkspaceState;
};

export type ExecutionWorkspaceState = {
  artifactType: string;
  artifactId: string;
  title: string;
  status: 'ready' | 'missing' | 'error';
  statusMessage: string;
  executionPackage?: Record<string, unknown>;
  executionContext?: Record<string, unknown>;
  contextCapsule?: Record<string, unknown>;
  executionPlan?: string;
  developerPrompt?: string;
  repositoryContext?: Record<string, unknown>;
  relatedFiles: string[];
  currentBranch?: string;
};

type SidebarHandlers = {
  startPlanning(requirement: string): Promise<PlannerViewState>;
  saveEdits(stage: string, payload: Record<string, unknown>): Promise<PlannerViewState>;
  regenerate(stage: string, userInput: string): Promise<PlannerViewState>;
  approve(stage: string): Promise<PlannerViewState>;
  copyPrompt(): Promise<PlannerViewState>;
  createWorkItems(): Promise<PlannerViewState>;
  generateExecutionPlan(): Promise<PlannerViewState>;
  generateDeveloperPrompt(): Promise<PlannerViewState>;
  rebuildExecutionPackage(): Promise<PlannerViewState>;
  openCopilotChat(): Promise<PlannerViewState>;
  openPlanning(): Promise<PlannerViewState>;
  refreshState(): Promise<PlannerViewState>;
  getState(): PlannerViewState;
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

    webviewView.webview.onDidReceiveMessage(async (message: { type: string; payload?: Record<string, unknown> }) => {
      try {
        await this.handleMessage(message);
      } catch (error) {
        const messageText = error instanceof Error ? error.message : String(error);
        this.postState({
          ...this.handlers.getState(),
          loading: false,
          loadingMessage: '',
          errorMessage: messageText,
        });
        vscode.window.showErrorMessage(messageText);
      }
    });
  }

  public update(state: PlannerViewState): void {
    this.postState(state);
  }

  private async handleMessage(message: { type: string; payload?: Record<string, unknown> }) {
    this.postState({
      ...this.handlers.getState(),
      loading: true,
      loadingMessage: 'Working...',
      errorMessage: '',
    });

    const payload = message.payload || {};
    let state: PlannerViewState;
    switch (message.type) {
      case 'startPlanning':
        state = await this.handlers.startPlanning(String(payload.requirement || ''));
        break;
      case 'saveEdits':
        state = await this.handlers.saveEdits(String(payload.stage || ''), payload.values as Record<string, unknown>);
        break;
      case 'regenerate':
        state = await this.handlers.regenerate(String(payload.stage || ''), String(payload.userInput || ''));
        break;
      case 'approve':
        state = await this.handlers.approve(String(payload.stage || ''));
        break;
      case 'copyPrompt':
        state = await this.handlers.copyPrompt();
        break;
      case 'createWorkItems':
        state = await this.handlers.createWorkItems();
        break;
      case 'generateExecutionPlan':
        state = await this.handlers.generateExecutionPlan();
        break;
      case 'generateDeveloperPrompt':
        state = await this.handlers.generateDeveloperPrompt();
        break;
      case 'rebuildExecutionPackage':
        state = await this.handlers.rebuildExecutionPackage();
        break;
      case 'openCopilotChat':
        state = await this.handlers.openCopilotChat();
        break;
      case 'openPlanning':
        state = await this.handlers.openPlanning();
        break;
      case 'refreshState':
        state = await this.handlers.refreshState();
        break;
      default:
        state = {
          ...this.handlers.getState(),
          loading: false,
          loadingMessage: '',
          errorMessage: `Unknown action: ${message.type}`,
        };
    }
    this.postState(state);
  }

  private postState(state: PlannerViewState): void {
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
  <title>HEI Engineering Assistant</title>
  <style>
    :root {
      --hei-bg: var(--vscode-editor-background);
      --hei-card: var(--vscode-sideBar-background);
      --hei-muted: var(--vscode-descriptionForeground);
      --hei-border: var(--vscode-input-border);
      --hei-primary: var(--vscode-button-background);
      --hei-primary-fg: var(--vscode-button-foreground);
      --hei-secondary: var(--vscode-button-secondaryBackground);
      --hei-secondary-fg: var(--vscode-button-secondaryForeground);
      --hei-input-bg: var(--vscode-input-background);
      --hei-input-fg: var(--vscode-input-foreground);
      --hei-panel: var(--vscode-editorWidget-background, var(--vscode-sideBar-background));
      --hei-focus: var(--vscode-focusBorder);
      --hei-link: var(--vscode-textLink-foreground);
      --hei-pass: var(--vscode-testing-iconPassed, #2ea043);
      --hei-warn: var(--vscode-testing-iconQueued, #d29922);
      --hei-error: var(--vscode-errorForeground);
    }
    body { margin: 0; padding: 14px; color: var(--vscode-editor-foreground); background: var(--hei-bg); font-family: var(--vscode-font-family); }
    h1,h2,h3,p { margin: 0; }
    button, input, textarea { font: inherit; }
    .page { display: grid; gap: 10px; max-width: 1320px; margin: 0 auto; }
    .header { display: grid; gap: 10px; grid-template-columns: 1fr; align-items: start; }
    .eyebrow { font-size: 11px; letter-spacing: .08em; text-transform: uppercase; color: var(--hei-muted); }
    .title-block { display: grid; gap: 4px; }
    .title-block h1 { font-size: 16px; line-height: 1.2; font-weight: 700; }
    .subtitle { color: var(--hei-muted); font-size: 12px; line-height: 1.4; }
    .card { border: 1px solid var(--hei-border); border-radius: 8px; background: var(--hei-card); padding: 10px; display: grid; gap: 8px; }
    .status-grid { display: grid; grid-template-columns: 1fr; gap: 8px; }
    .status-item, .summary-item, .footer-item, .option-item, .nav-item, .stage-item, .recent-item, .task-card, .action-card { border: 1px solid var(--hei-border); border-radius: 8px; background: var(--hei-panel); }
    .status-item, .summary-item, .footer-item { padding: 8px; display: grid; gap: 4px; }
    .status-label, .section-label, .mini-label { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--hei-muted); }
    .status-value { font-size: 13px; font-weight: 600; line-height: 1.25; }
    .nav { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
    .nav-item { padding: 8px 9px; cursor: pointer; text-align: left; min-height: 62px; }
    .nav-item.active { border-color: var(--hei-focus); box-shadow: inset 0 0 0 1px var(--hei-focus); }
    .nav-item strong { display: block; font-size: 13px; margin-bottom: 2px; }
    .nav-item span { color: var(--hei-muted); font-size: 11px; }
    .advanced { padding: 8px 10px; }
    .advanced summary { cursor: pointer; font-weight: 600; }
    .advanced-list { margin-top: 8px; color: var(--hei-muted); font-size: 12px; display: flex; flex-wrap: wrap; gap: 8px; }
    .input-shell { display: grid; gap: 9px; }
    textarea, input[type="text"] {
      width: 100%;
      box-sizing: border-box;
      color: var(--hei-input-fg);
      background: var(--hei-input-bg);
      border: 1px solid var(--hei-border);
      border-radius: 8px;
      padding: 9px 10px;
    }
    textarea { min-height: 96px; resize: vertical; line-height: 1.45; }
    .helper { color: var(--hei-muted); font-size: 12px; line-height: 1.4; }
    .example-list { display: grid; gap: 4px; color: var(--hei-muted); font-size: 12px; }
    .options { display: grid; gap: 8px; }
    .option-item { padding: 9px 10px; display: flex; gap: 8px; align-items: center; }
    .actions { display: flex; gap: 8px; flex-wrap: wrap; }
    button { border: 0; border-radius: 8px; padding: 9px 12px; cursor: pointer; color: var(--hei-primary-fg); background: var(--hei-primary); }
    button.full { width: 100%; justify-content: center; }
    button.secondary { color: var(--hei-secondary-fg); background: var(--hei-secondary); }
    button.ghost { background: transparent; color: var(--hei-link); border: 1px solid var(--hei-border); }
    button:disabled { opacity: .6; cursor: not-allowed; }
    .summary-grid { display: grid; grid-template-columns: 1fr; gap: 8px; }
    .summary-item strong { font-size: 14px; font-weight: 600; }
    .banner { border-radius: 8px; padding: 9px 10px; border: 1px solid var(--hei-border); background: var(--hei-panel); color: var(--hei-muted); }
    .error { border: 1px solid var(--hei-error); color: var(--hei-error); border-radius: 8px; padding: 12px; display: grid; gap: 8px; }
    .error ul { margin: 0; padding-left: 18px; color: var(--vscode-editor-foreground); }
    .loading-card { display: grid; gap: 10px; }
    .loading-stage { display: flex; align-items: center; gap: 10px; }
    .loading-dot { width: 8px; height: 8px; border-radius: 999px; background: var(--hei-primary); animation: pulse 1.4s ease-in-out infinite; }
    .loading-stage:nth-child(2) .loading-dot { animation-delay: .1s; }
    .loading-stage:nth-child(3) .loading-dot { animation-delay: .2s; }
    .loading-stage:nth-child(4) .loading-dot { animation-delay: .3s; }
    .loading-stage:nth-child(5) .loading-dot { animation-delay: .4s; }
    .loading-stage:nth-child(6) .loading-dot { animation-delay: .5s; }
    @keyframes pulse { 0%, 100% { opacity: .35; transform: scale(.9); } 50% { opacity: 1; transform: scale(1.1); } }
    .stage-row { display: grid; grid-template-columns: 1fr; gap: 8px; }
    .stage-item { padding: 9px; display: grid; gap: 3px; }
    .stage-item.active { border-color: var(--hei-focus); }
    .stage-item.done { background: color-mix(in srgb, var(--hei-primary) 12%, transparent); }
    .stage-item small { color: var(--hei-muted); }
    .task-grid, .recent-grid { display: grid; gap: 8px; }
    .task-grid { grid-template-columns: 1fr; }
    .task-card { padding: 9px; display: grid; gap: 8px; }
    .task-header { display: flex; justify-content: space-between; gap: 8px; align-items: flex-start; }
    .badge { border-radius: 999px; padding: 2px 8px; font-size: 11px; border: 1px solid var(--hei-border); color: var(--hei-muted); }
    .badge.good { color: var(--hei-pass); border-color: color-mix(in srgb, var(--hei-pass) 55%, var(--hei-border)); }
    .badge.warn { color: var(--hei-warn); border-color: color-mix(in srgb, var(--hei-warn) 55%, var(--hei-border)); }
    .readout { white-space: pre-wrap; border: 1px solid var(--hei-border); border-radius: 8px; padding: 9px; background: var(--vscode-textCodeBlock-background); line-height: 1.45; }
    .footer { display: flex; flex-wrap: wrap; gap: 8px; padding: 4px 2px 0; color: var(--hei-muted); font-size: 11px; align-items: center; }
    .hidden { display: none !important; }
    .link-button { background: transparent; color: var(--hei-link); border: none; padding: 0; text-align: left; cursor: pointer; }
    .detail-stack { display: grid; gap: 12px; }
    .cta-strip { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
    .pill { display: inline-flex; align-items: center; gap: 6px; border: 1px solid var(--hei-border); border-radius: 999px; padding: 4px 10px; color: var(--hei-muted); font-size: 11px; }
    .coming-soon { color: var(--hei-muted); font-size: 12px; line-height: 1.5; }
    .env-card { display: grid; gap: 8px; }
    .env-grid { display: grid; grid-template-columns: 1fr; gap: 8px; }
    .chip { display: inline-flex; align-items: center; gap: 6px; border-radius: 999px; padding: 3px 8px; font-size: 11px; font-weight: 600; width: fit-content; border: 1px solid var(--hei-border); }
    .chip::before { content: ''; width: 7px; height: 7px; border-radius: 999px; background: currentColor; }
    .chip.good { color: var(--hei-pass); border-color: color-mix(in srgb, var(--hei-pass) 45%, var(--hei-border)); }
    .chip.warn { color: var(--hei-warn); border-color: color-mix(in srgb, var(--hei-warn) 45%, var(--hei-border)); }
    .chip.neutral { color: var(--hei-muted); }
    .chip.error { color: var(--hei-error); border-color: color-mix(in srgb, var(--hei-error) 45%, var(--hei-border)); }
    .footer-pill { display: inline-flex; gap: 6px; align-items: center; }
    .footer-pill strong { color: var(--vscode-editor-foreground); font-weight: 600; }
    .planning-layout { display: grid; grid-template-columns: 1fr; gap: 10px; align-items: start; }
    .planning-main, .planning-side, .execution-layout { display: grid; gap: 10px; }
    .planning-main > section, .planning-side > section { min-width: 0; }
    .section-stack { display: grid; gap: 10px; }
    .compact-list { display: grid; gap: 8px; }
    .compact-row { border: 1px solid var(--hei-border); border-radius: 8px; background: var(--hei-panel); padding: 8px 9px; display: grid; gap: 4px; }
    .compact-row strong { font-size: 13px; }
    .compact-row span { color: var(--hei-muted); font-size: 12px; line-height: 1.4; }
    .execution-layout { grid-template-columns: 1fr; }
    .execution-layout .card.primary-span { grid-column: 1 / -1; }
    .card-head { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
    .card-head .title-block { flex: 1; }
    .toolbar-inline { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
    .code-preview details { width: 100%; }
    @media (min-width: 540px) {
      .status-grid, .summary-grid, .task-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .stage-row { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    @media (min-width: 640px) {
      .env-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    @media (min-width: 820px) {
      .header { grid-template-columns: 1fr; }
      .nav { grid-template-columns: repeat(4, minmax(0, 1fr)); }
      .execution-layout { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .execution-layout .card.primary-span { grid-column: 1 / -1; }
    }
    @media (min-width: 1120px) {
      .planning-layout { grid-template-columns: minmax(0, 1.15fr) minmax(320px, .85fr); }
      .stage-row { grid-template-columns: repeat(5, minmax(0, 1fr)); }
      .task-grid { grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }
    }
  </style>
</head>
<body>
  <div id="app" class="page"></div>
  <script nonce="${nonce}">
    const vscode = acquireVsCodeApi();
    const app = document.getElementById('app');
    let currentNav = 'planning';
    let latestState = {
      workspaceName: 'Workspace',
      backendStatus: 'unknown',
      backendUrl: '',
      backendSource: '',
      backendReason: '',
      currentFileName: '',
      currentBranch: '',
      lastSyncLabel: '—',
      loading: false,
      loadingMessage: '',
      errorMessage: '',
      recentEngineeringPackages: [],
      session: undefined,
      executionWorkspace: undefined,
    };

    const plannerStageLabels = {
      refined_story: 'Business Intent',
      acceptance_criteria: 'Acceptance Criteria',
      tasks: 'Implementation Tasks',
      azure_devops_creation: 'Approval & Developer Prompt',
      success: 'Ready',
    };

    function post(type, payload = {}) {
      vscode.postMessage({ type, payload });
    }

    function escapeHtml(value) {
      return String(value || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
    }

    function titleCase(value) {
      return String(value || '').replace(/[_-]+/g, ' ').replace(/\\s+/g, ' ').trim().replace(/\\b\\w/g, (match) => match.toUpperCase());
    }

    function currentRequestText() {
      const session = latestState.session;
      if (session?.requirement) return session.requirement;
      const input = document.getElementById('engineeringRequest');
      return input ? input.value : '';
    }

    function optionRows() {
      return \`
        <div class="options">
          <label class="option-item"><input type="checkbox" id="optRepo" checked /> <span>Use Repository Intelligence</span></label>
          <label class="option-item"><input type="checkbox" id="optMemory" checked /> <span>Use Engineering Memory</span></label>
          <label class="option-item"><input type="checkbox" id="optRoute" checked /> <span>Auto Route</span></label>
          <label class="option-item"><input type="checkbox" id="optPackage" checked /> <span>Generate Implementation Package</span></label>
        </div>
      \`;
    }

    function inferKnowledgeRegistryStatus() {
      const exec = latestState.executionWorkspace;
      const context = exec?.executionContext || {};
      const modules = Array.isArray(context.affected_modules) ? context.affected_modules.length : 0;
      return modules ? 'Active' : latestState.backendStatus.startsWith('Connected') ? 'Connected' : 'Not Connected';
    }

    function inferEngineeringMemoryStatus() {
      const exec = latestState.executionWorkspace;
      const context = exec?.executionContext || {};
      if (context.memory_context || context.memory_diagnostics) return 'Active';
      return latestState.backendStatus.startsWith('Connected') ? 'Connected' : 'Not Connected';
    }

    function inferProvider() {
      const exec = latestState.executionWorkspace;
      const context = exec?.executionContext || {};
      return context.provider_used || context.provider || (latestState.backendStatus.startsWith('Connected') ? 'Auto' : 'Not Connected');
    }

    function inferRepositoryMode() {
      const exec = latestState.executionWorkspace;
      const pkg = exec?.executionPackage || {};
      const readiness = pkg.readiness || {};
      return readiness.repositoryMode || (latestState.backendSource === 'local' ? 'Local' : latestState.backendSource === 'railway' ? 'Knowledge Snapshot' : 'Not Connected');
    }

    function chipClass(value) {
      const normalized = String(value || '').toLowerCase();
      if (normalized.includes('error') || normalized.includes('failed')) return 'error';
      if (normalized.includes('active') || normalized.includes('connected') || normalized.includes('healthy')) return 'good';
      if (normalized.includes('snapshot') || normalized.includes('auto')) return 'warn';
      return 'neutral';
    }

    function statusChip(value) {
      return \`<span class="chip \${chipClass(value)}">\${escapeHtml(String(value || '—'))}</span>\`;
    }

    function backendLabel() {
      if (latestState.backendSource === 'railway') return 'Cloud (Railway)';
      if (latestState.backendSource === 'local') return 'Local';
      return 'Not Connected';
    }

    function backendHealthLabel() {
      return latestState.backendStatus.startsWith('Connected') ? 'Healthy' : 'Not Connected';
    }

    function currentStoryLabel() {
      return latestState.session?.story?.title || '—';
    }

    function environmentCard() {
      const rows = [
        ['Workspace', latestState.workspaceName || '—'],
        ['Repository', inferRepositoryMode()],
        ['Knowledge Registry', statusChip(inferKnowledgeRegistryStatus())],
        ['Engineering Memory', statusChip(inferEngineeringMemoryStatus())],
        ['Backend', backendLabel()],
        ['Provider', inferProvider()],
        ['Status', statusChip(backendHealthLabel())],
        ['Last Sync', latestState.lastSyncLabel || '—'],
      ];
      return \`
        <section class="card env-card">
          <div class="title-block">
            <h2>HEI Environment</h2>
            <div class="subtitle">Current workspace connection and engineering intelligence status.</div>
          </div>
          <div class="env-grid">
            \${rows.map(([label, value]) => \`<div class="status-item"><div class="status-label">\${escapeHtml(label)}</div><div class="status-value">\${typeof value === 'string' && value.startsWith('<span') ? value : escapeHtml(String(value))}</div></div>\`).join('')}
          </div>
          <div class="status-item">
            <div class="status-label">Reason</div>
            <div class="helper">\${escapeHtml(latestState.backendReason || '—')}</div>
          </div>
        </section>
      \`;
    }

    function currentContextCard() {
      return \`
        <section class="card">
          <div class="title-block">
            <h2>Current Engineering Context</h2>
            <div class="subtitle">Working context from VS Code and the active HEI session.</div>
          </div>
          <div class="summary-grid">
            <div class="summary-item"><div class="status-label">Repository</div><strong>\${escapeHtml(latestState.workspaceName || '—')}</strong></div>
            <div class="summary-item"><div class="status-label">Branch</div><strong>\${escapeHtml(latestState.currentBranch || '—')}</strong></div>
            <div class="summary-item"><div class="status-label">Current File</div><strong>\${escapeHtml(latestState.currentFileName || '—')}</strong></div>
            <div class="summary-item"><div class="status-label">Current Story</div><strong>\${escapeHtml(currentStoryLabel())}</strong></div>
            <div class="summary-item"><div class="status-label">Implementation Package</div><strong>\${latestState.executionWorkspace?.executionPackage ? 'Loaded' : 'None'}</strong></div>
          </div>
        </section>
      \`;
    }

    function renderHeader() {
      return \`
        <section class="header">
          <div class="title-block">
            <div class="eyebrow">HEI</div>
            <h1>HEI Engineering Assistant</h1>
            <div class="subtitle">Repository-aware Engineering Intelligence</div>
          </div>
          \${environmentCard()}
        </section>
      \`;
    }

    function renderNavigation() {
      const items = [
        ['planning', 'Planning', 'Requirements<br/>Capabilities<br/>Stories<br/>Tasks'],
        ['execution', 'Execution', 'Implementation Packages<br/>Implementation Plans<br/>Developer Prompts'],
        ['memory', 'Memory', 'Validated Patterns<br/>Architecture<br/>Standards'],
        ['settings', 'Settings', 'Providers<br/>Repository<br/>Backend<br/>Preferences'],
      ];
      return \`
        <section class="nav">
          \${items.map(([key, label, detail]) => \`<button class="nav-item \${currentNav === key ? 'active' : ''}" data-nav="\${key}" aria-label="\${label}"><strong>\${label}</strong><span>\${detail}</span></button>\`).join('')}
        </section>
        <details class="card advanced">
          <summary>Diagnostics &amp; Advanced</summary>
          <div class="advanced-list">
            <span>Backend Diagnostics</span>
            <span>Provider Status</span>
            <span>Logs</span>
            <span>Connection</span>
            <span>Debug</span>
          </div>
        </details>
      \`;
    }

    function emptyState() {
      return \`
        <section class="card">
          <div class="title-block">
            <h2>Start with an engineering request.</h2>
            <div class="subtitle">HEI will analyze business intent, use repository knowledge and engineering memory, then generate an implementation-ready engineering plan.</div>
          </div>
        </section>
      \`;
    }

    function requestEditor() {
      const session = latestState.session;
      const value = session?.requirement || '';
      return \`
        <section class="card input-shell">
          <div class="card-head">
            <div class="title-block">
              <div class="section-label">Engineering Request</div>
              <div class="subtitle">Describe the capability, outcome, or engineering change you want HEI to plan.</div>
            </div>
          </div>
          <textarea id="engineeringRequest" aria-label="Engineering Request" placeholder="Describe what you want to build...">\${escapeHtml(value)}</textarea>
          <div class="example-list">
            <div>• Launch Line Defender in GridHub</div>
            <div>• Add Device Health Monitoring</div>
            <div>• Implement OTA Rollback</div>
            <div>• Modernize Alarm Dashboard</div>
            <div>• Add Fault Timeline</div>
          </div>
          \${optionRows()}
          <div class="actions">
            <button id="analyzePlanBtn" class="full">Analyze &amp; Plan</button>
            <button id="clearRequestBtn" class="secondary">Clear</button>
          </div>
        </section>
      \`;
    }

    function complexityLabel(taskCount) {
      if (taskCount >= 6) return 'High';
      if (taskCount >= 3) return 'Medium';
      if (taskCount > 0) return 'Low';
      return 'Pending';
    }

    function confidenceLabel(session) {
      const approvals = [session.story_approved, session.acceptance_approved, session.tasks_approved].filter(Boolean).length;
      return approvals === 3 ? 'High' : approvals === 2 ? 'Moderate' : approvals === 1 ? 'Early' : 'Draft';
    }

    function engineeringSummary(session) {
      const acCount = Array.isArray(session.acceptance_criteria) ? session.acceptance_criteria.length : 0;
      const taskCount = Array.isArray(session.tasks) ? session.tasks.length : 0;
      const items = [
        ['Business Intent', session.story?.business_value || session.story?.description || session.requirement || 'Pending analysis'],
        ['Capabilities Identified', acCount ? \`\${acCount} acceptance areas\` : 'Pending'],
        ['Estimated Features', 'Continue to HEI Planning workspace'],
        ['Estimated Stories', taskCount ? \`1 active story, \${taskCount} tasks proposed\` : 'Pending task generation'],
        ['Complexity', complexityLabel(taskCount)],
        ['Confidence', confidenceLabel(session)],
      ];
      return \`
        <section class="card">
          <div class="title-block">
            <h2>Engineering Summary</h2>
            <div class="subtitle">Structured output from the current HEI planning session.</div>
          </div>
          <div class="summary-grid">
            \${items.map(([label, value]) => \`<div class="summary-item"><div class="status-label">\${escapeHtml(label)}</div><strong>\${escapeHtml(String(value))}</strong></div>\`).join('')}
          </div>
          <div class="actions">
            <button id="continuePlanningBtn">Continue to Planning</button>
            <button id="openImplementationPackageBtn" class="secondary" \${latestState.executionWorkspace ? '' : 'disabled'}>Open Implementation Workspace</button>
            <button id="generateAiPromptBtn" class="secondary" \${latestState.executionWorkspace ? '' : 'disabled'}>Generate Developer Prompt</button>
            <button id="openExecutionWorkspaceBtn" class="secondary" \${latestState.executionWorkspace ? '' : 'disabled'}>Open Execution Workspace</button>
          </div>
        </section>
      \`;
    }

    function recentWork() {
      const items = latestState.recentEngineeringPackages || [];
      return \`
        <section class="card">
          <div class="title-block">
            <h2>Recent Engineering Packages</h2>
            <div class="subtitle">Resume recent HEI work quickly.</div>
          </div>
          <div class="recent-grid">
            \${items.length ? items.map((item) => \`<button class="recent-item nav-item" data-recent="\${escapeHtml(item)}"><strong>\${escapeHtml(item)}</strong><span>Reuse as engineering request</span></button>\`).join('') : '<div class="compact-row"><strong>No recent engineering packages.</strong></div>'}
          </div>
        </section>
      \`;
    }

    function planningSidePanel(session) {
      const phase = plannerStageLabels[session.current_stage] || 'Planning';
      const approvals = [
        session.story_approved ? 'Business Intent approved' : 'Business Intent pending',
        session.acceptance_approved ? 'Acceptance Criteria approved' : 'Acceptance Criteria pending',
        session.tasks_approved ? 'Implementation Tasks approved' : 'Implementation Tasks pending',
      ];
      return \`
        <section class="card">
          <div class="title-block">
            <h2>Planning Snapshot</h2>
            <div class="subtitle">Keep the current session readable at a glance while you work through approvals.</div>
          </div>
          <div class="summary-grid">
            <div class="summary-item"><div class="status-label">Current Phase</div><strong>\${escapeHtml(phase)}</strong></div>
            <div class="summary-item"><div class="status-label">Confidence</div><strong>\${escapeHtml(confidenceLabel(session))}</strong></div>
            <div class="summary-item"><div class="status-label">Complexity</div><strong>\${escapeHtml(complexityLabel(Array.isArray(session.tasks) ? session.tasks.length : 0))}</strong></div>
            <div class="summary-item"><div class="status-label">Prompt</div><strong>\${session.code_generation_prompt ? 'Available' : 'Pending'}</strong></div>
          </div>
          <div class="section-stack">
            <div class="section-label">Approval Status</div>
            <div class="compact-list">
              \${approvals.map((item) => \`<div class="compact-row"><strong>\${escapeHtml(item)}</strong></div>\`).join('')}
            </div>
          </div>
        </section>
      \`;
    }

    function loadingState() {
      if (!latestState.loading) return '';
      const stages = ['Analyzing Requirement', 'Repository Intelligence', 'Knowledge Registry', 'Engineering Memory', 'Planning', 'Almost Done'];
      return \`
        <section class="card loading-card">
          \${stages.map((stage) => \`<div class="loading-stage"><span class="loading-dot"></span><span>\${escapeHtml(stage)}</span></div>\`).join('')}
          <div class="helper">\${escapeHtml(latestState.loadingMessage || 'Working...')}</div>
        </section>
      \`;
    }

    function errorState() {
      if (!latestState.errorMessage) return '';
      return \`
        <section class="error" role="alert">
          <strong>Unable to complete engineering analysis.</strong>
          <ul>
            <li>Provider unavailable</li>
            <li>Repository disconnected</li>
            <li>Invalid workspace</li>
          </ul>
          <div>\${escapeHtml(latestState.errorMessage)}</div>
          <div class="actions">
            <button id="retryBtn">Retry</button>
            <button id="diagnosticsBtn" class="secondary">Open Diagnostics</button>
          </div>
        </section>
      \`;
    }

    function planningWorkflow(session) {
      const stages = [
        ['refined_story', 'Business Intent', session.story_approved],
        ['acceptance_criteria', 'Acceptance Criteria', session.acceptance_approved],
        ['tasks', 'Implementation Tasks', session.tasks_approved],
        ['azure_devops_creation', 'Approval & Developer Prompt', session.current_stage === 'azure_devops_creation' || session.current_stage === 'success'],
        ['success', 'Ready', session.current_stage === 'success'],
      ];
      return \`
        <section class="card">
          <div class="title-block">
            <h2>Planning Workspace</h2>
            <div class="subtitle">Move through the current HEI planning stage without leaving VS Code.</div>
          </div>
          <div class="stage-row">
            \${stages.map(([stage, label, done]) => \`<div class="stage-item \${done ? 'done' : ''} \${session.current_stage === stage ? 'active' : ''}"><strong>\${escapeHtml(label)}</strong><small>\${session.current_stage === stage ? 'Current' : done ? 'Ready' : 'Pending'}</small></div>\`).join('')}
          </div>
          <div class="banner">\${escapeHtml(session.question || 'HEI is ready for the next planning decision.')}</div>
          \${stageBody(session)}
        </section>
      \`;
    }

    function stageBody(session) {
      if (session.current_stage === 'refined_story') {
        return \`
          <div class="detail-stack">
            <input type="text" id="storyTitle" aria-label="Story Title" value="\${escapeHtml(session.story.title)}" />
            <textarea id="storyDescription" aria-label="Story Description">\${escapeHtml(session.story.description)}</textarea>
            <textarea id="storyBusinessValue" aria-label="Business Value">\${escapeHtml(session.story.business_value)}</textarea>
            <textarea id="activeUserInput" aria-label="User Input" placeholder="\${escapeHtml(session.user_input_hint || 'Add guidance for HEI')}"></textarea>
            <div class="actions">
              <button id="approveStoryBtn">Approve</button>
              <button id="saveStoryBtn" class="secondary">Edit</button>
              <button id="regenStoryBtn" class="secondary">Regenerate</button>
            </div>
          </div>
        \`;
      }
      if (session.current_stage === 'acceptance_criteria') {
        return \`
          <div class="detail-stack">
            <textarea id="acceptanceCriteriaInput" aria-label="Acceptance Criteria">\${escapeHtml((session.acceptance_criteria || []).join('\\n'))}</textarea>
            <textarea id="activeUserInput" aria-label="User Input" placeholder="\${escapeHtml(session.user_input_hint || 'Add guidance for HEI')}"></textarea>
            <div class="actions">
              <button id="approveAcceptanceBtn">Approve</button>
              <button id="saveAcceptanceBtn" class="secondary">Edit</button>
              <button id="regenAcceptanceBtn" class="secondary">Regenerate</button>
            </div>
          </div>
        \`;
      }
      if (session.current_stage === 'tasks') {
        return \`
          <div class="detail-stack">
            <div class="task-grid">
              \${(session.tasks || []).map((task, index) => \`
                <div class="task-card">
                  <div class="task-header">
                    <strong>\${escapeHtml(task.title || \`Task \${index + 1}\`)}</strong>
                    <span class="badge \${task.azure_work_item_id ? 'good' : task.status === 'failed' ? 'warn' : ''}">\${escapeHtml(task.azure_work_item_id ? 'Created' : task.status === 'failed' ? 'Failed' : 'Draft')}</span>
                  </div>
                  <textarea data-task-field="title" data-task-index="\${index}" aria-label="Task title">\${escapeHtml(task.title)}</textarea>
                  <textarea data-task-field="description" data-task-index="\${index}" aria-label="Task description">\${escapeHtml(task.description)}</textarea>
                  <input type="text" data-task-field="estimated_effort" data-task-index="\${index}" value="\${escapeHtml(task.estimated_effort || '')}" aria-label="Estimated effort" />
                </div>
              \`).join('')}
            </div>
            <textarea id="activeUserInput" aria-label="User Input" placeholder="\${escapeHtml(session.user_input_hint || 'Add guidance for HEI')}"></textarea>
            <div class="actions">
              <button id="approveTasksBtn">Approve</button>
              <button id="saveTasksBtn" class="secondary">Edit</button>
              <button id="regenTasksBtn" class="secondary">Regenerate</button>
            </div>
          </div>
        \`;
      }
      if (session.current_stage === 'azure_devops_creation') {
        return \`
          <div class="detail-stack">
            <div class="banner">Planning is approved. Generate the Developer Prompt or continue the workflow in HEI.</div>
            <div class="cta-strip">
              <span class="pill">\${escapeHtml(plannerStageLabels[session.current_stage] || 'Ready')}</span>
              <span class="pill">\${session.code_generation_prompt ? 'Developer Prompt Available' : 'Developer Prompt Pending'}</span>
            </div>
            <div class="actions">
              <button id="copyPromptBtn">Generate Developer Prompt</button>
              <button id="createWorkItemsBtn" class="secondary">Continue to Planning</button>
            </div>
            \${session.code_generation_prompt ? \`<details><summary>Show Developer Prompt</summary><div class="readout">\${escapeHtml(session.code_generation_prompt)}</div></details>\` : ''}
          </div>
        \`;
      }
      return \`
        <div class="detail-stack">
          <div class="banner">Planning is ready. Continue into implementation or Azure DevOps creation from the HEI workspace.</div>
          <div class="actions">
            <button id="copyPromptBtn">Generate Developer Prompt</button>
            <button id="refreshBtn" class="secondary">Refresh State</button>
          </div>
          \${session.code_generation_prompt ? \`<details><summary>Show Developer Prompt</summary><div class="readout">\${escapeHtml(session.code_generation_prompt)}</div></details>\` : ''}
        </div>
      \`;
    }

    function executionView() {
      const workspace = latestState.executionWorkspace;
      if (!workspace) {
        return \`
          <section class="execution-layout">
            <section class="card primary-span">
              <div class="title-block">
                <h2>Execution</h2>
                <div class="subtitle">No active Developer Prompt</div>
              </div>
              <div class="coming-soon">Generate an Implementation Package from the HEI Planning Workspace. HEI will turn it into a Developer Prompt for Copilot or Codex.</div>
              <div class="compact-list">
                <div class="compact-row"><strong>Developer Prompt</strong><span>Main VS Code artifact</span></div>
                <div class="compact-row"><strong>Implementation Plan</strong><span>Optional engineering strategy</span></div>
                <div class="compact-row"><strong>Implementation Package JSON</strong><span>Advanced hidden context</span></div>
                <div class="compact-row"><strong>Validation Results</strong><span>Included when available</span></div>
                <div class="compact-row"><strong>Engineering Memory</strong><span>Included when available</span></div>
              </div>
              <div class="actions">
                <button id="openPlanningBtn">Open HEI Planning</button>
              </div>
            </section>
            \${recentWork()}
          </section>
        \`;
      }
      const packageJson = workspace.executionPackage ? JSON.stringify(workspace.executionPackage, null, 2) : '';
      const plan = workspace.executionPlan || '';
      const developerPrompt = workspace.developerPrompt || '';
      return \`
        <section class="execution-layout">
          <section class="card primary-span">
            <div class="card-head">
              <div class="title-block">
                <h2>Execution</h2>
                <div class="subtitle">Developer Prompt is the main engineer-facing artifact. Structured package context stays available under Advanced.</div>
              </div>
              <span class="pill">\${escapeHtml(workspace.statusMessage || workspace.status)}</span>
            </div>
            <div class="summary-grid">
              <div class="summary-item"><div class="status-label">Artifact</div><strong>\${escapeHtml(workspace.artifactType || 'Artifact')} #\${escapeHtml(workspace.artifactId || '')}</strong></div>
              <div class="summary-item"><div class="status-label">Current Branch</div><strong>\${escapeHtml(workspace.currentBranch || 'Not provided')}</strong></div>
              <div class="summary-item"><div class="status-label">Related Files</div><strong>\${escapeHtml(String((workspace.relatedFiles || []).length || 0))}</strong></div>
              <div class="summary-item"><div class="status-label">Developer Prompt</div><strong>\${developerPrompt ? 'Ready' : 'Not generated'}</strong></div>
            </div>
            <div class="toolbar-inline">
              <button id="generateDeveloperPromptBtn" \${workspace.executionPackage ? '' : 'disabled'}>Generate Developer Prompt</button>
              <button id="copyExecutionPlanBtn" class="secondary" \${developerPrompt ? '' : 'disabled'}>Copy Prompt</button>
              <button id="openCopilotChatBtn" class="secondary" \${developerPrompt ? '' : 'disabled'}>Open Copilot Chat</button>
            </div>
          </section>
          <section class="card">
            <div class="title-block">
              <h2>Developer Prompt</h2>
              <div class="subtitle">Paste-ready prompt for Copilot, Codex, or another coding assistant.</div>
            </div>
            \${developerPrompt ? \`<div class="readout">\${escapeHtml(developerPrompt)}</div>\` : \`<div class="banner">Generate a Developer Prompt from the current Implementation Package.</div>\`}
          </section>
          <section class="card">
            <div class="title-block">
              <h2>Repository Context</h2>
              <div class="subtitle">Files and package context currently attached to this execution workspace.</div>
            </div>
            <div class="compact-list">
              \${(workspace.relatedFiles || []).length ? (workspace.relatedFiles || []).map((file) => \`<div class="compact-row"><strong>\${escapeHtml(file)}</strong></div>\`).join('') : '<div class="compact-row"><strong>No related files loaded yet</strong><span>Repository-ranked files will appear here when available.</span></div>'}
            </div>
          </section>
          <section class="card code-preview">
            <div class="title-block">
              <h2>Advanced</h2>
              <div class="subtitle">Implementation Package JSON, repository context, engineering rules, and diagnostics.</div>
            </div>
            \${plan ? \`<details><summary>Implementation Plan</summary><div class="readout">\${escapeHtml(plan)}</div></details>\` : ''}
            \${packageJson ? \`<details><summary>Implementation Package JSON</summary><div class="readout">\${escapeHtml(packageJson)}</div></details>\` : \`<div class="banner">Implementation Package is not available yet.</div>\`}
            <details>
              <summary>Repository Context</summary>
              <div class="readout">\${escapeHtml(JSON.stringify(workspace.repositoryContext || {}, null, 2))}</div>
            </details>
            <details>
              <summary>Diagnostics</summary>
              <div class="readout">\${escapeHtml(JSON.stringify(workspace.executionContext || {}, null, 2))}</div>
            </details>
          </section>
          \${recentWork()}
        </section>
      \`;
    }

    function memoryView() {
      return \`
        <section class="card">
          <div class="title-block">
            <h2>Memory</h2>
            <div class="subtitle">Engineering Memory will surface approved patterns, reusable packages, decisions, and lessons learned here.</div>
          </div>
          <div class="banner">Coming Soon</div>
        </section>
      \`;
    }

    function settingsView() {
      return \`
        <section class="card">
          <div class="title-block">
            <h2>Settings</h2>
            <div class="subtitle">Workspace routing and backend diagnostics will live here.</div>
          </div>
          <div class="banner">Coming Soon</div>
        </section>
      \`;
    }

    function footer() {
      return \`
        <section class="footer">
          <span class="footer-pill"><strong>HEI v1</strong></span>
          <span class="footer-pill">Repository Intelligence <strong>\${escapeHtml(inferRepositoryMode())}</strong></span>
          <span class="footer-pill">Knowledge Registry <strong>\${escapeHtml(inferKnowledgeRegistryStatus())}</strong></span>
          <span class="footer-pill">Engineering Memory <strong>\${escapeHtml(inferEngineeringMemoryStatus())}</strong></span>
          <span class="footer-pill">Backend <strong>\${escapeHtml(backendLabel())}</strong></span>
          <span class="footer-pill">Provider <strong>\${escapeHtml(inferProvider())}</strong></span>
        </section>
      \`;
    }

    function planningView() {
      const session = latestState.session;
      return \`
        <section class="planning-layout">
          <div class="planning-main">
            \${requestEditor()}
            \${!session ? emptyState() : ''}
            \${currentContextCard()}
            \${session ? planningWorkflow(session) : ''}
          </div>
          <div class="planning-side">
            \${session ? engineeringSummary(session) : ''}
            \${session ? planningSidePanel(session) : ''}
            \${session ? recentWork() : ''}
          </div>
        </section>
      \`;
    }

    function mainView() {
      if (currentNav === 'execution') return executionView();
      if (currentNav === 'memory') return memoryView();
      if (currentNav === 'settings') return settingsView();
      return planningView();
    }

    function render() {
      app.innerHTML = [
        renderHeader(),
        renderNavigation(),
        errorState(),
        loadingState(),
        mainView(),
        footer(),
      ].join('');
      wireEvents();
    }

    function wireEvents() {
      const byId = (id) => document.getElementById(id);
      document.querySelectorAll('[data-nav]').forEach((button) => {
        button.addEventListener('click', () => {
          currentNav = button.getAttribute('data-nav') || 'planning';
          render();
        });
      });
      const requestInput = byId('engineeringRequest');
      byId('analyzePlanBtn')?.addEventListener('click', () => post('startPlanning', { requirement: requestInput?.value || '' }));
      byId('clearRequestBtn')?.addEventListener('click', () => {
        if (requestInput) requestInput.value = '';
      });
      requestInput?.addEventListener('keydown', (event) => {
        if ((event.key === 'Enter' && (event.ctrlKey || event.metaKey)) || (event.key === 'Enter' && !event.shiftKey && event.altKey)) {
          event.preventDefault();
          post('startPlanning', { requirement: requestInput.value || '' });
        }
      });
      byId('retryBtn')?.addEventListener('click', () => post('refreshState'));
      byId('diagnosticsBtn')?.addEventListener('click', () => {
        const details = [latestState.backendStatus, latestState.backendUrl, latestState.backendReason].filter(Boolean).join('\\n');
        post('refreshState');
        if (details) {
          navigator.clipboard?.writeText(details).catch(() => {});
        }
      });
      byId('continuePlanningBtn')?.addEventListener('click', () => {
        currentNav = 'planning';
        render();
      });
      byId('openImplementationPackageBtn')?.addEventListener('click', () => {
        currentNav = 'execution';
        render();
      });
      byId('generateAiPromptBtn')?.addEventListener('click', () => {
        if (latestState.executionWorkspace) {
          post('generateDeveloperPrompt');
        } else {
          post('copyPrompt');
        }
      });
      byId('openExecutionWorkspaceBtn')?.addEventListener('click', () => {
        currentNav = 'execution';
        render();
      });
      document.querySelectorAll('[data-recent]').forEach((button) => {
        button.addEventListener('click', () => {
          const value = button.getAttribute('data-recent') || '';
          const input = byId('engineeringRequest');
          if (input) {
            input.value = value;
            input.focus();
          }
          currentNav = 'planning';
        });
      });
      byId('refreshBtn')?.addEventListener('click', () => post('refreshState'));
      byId('openPlanningBtn')?.addEventListener('click', () => post('openPlanning'));
      byId('generateExecutionPlanBtn')?.addEventListener('click', () => post('generateExecutionPlan'));
      byId('generateDeveloperPromptBtn')?.addEventListener('click', () => post('generateDeveloperPrompt'));
      byId('copyExecutionPlanBtn')?.addEventListener('click', () => post('copyPrompt'));
      byId('openCopilotChatBtn')?.addEventListener('click', () => post('openCopilotChat'));
      const session = latestState.session;
      if (!session) {
        return;
      }
      const userInput = () => (byId('activeUserInput') ? byId('activeUserInput').value : '');
      const storyPayload = () => ({
        title: byId('storyTitle')?.value || '',
        description: byId('storyDescription')?.value || '',
        business_value: byId('storyBusinessValue')?.value || '',
      });
      const acceptancePayload = () => ({
        acceptance_criteria: (byId('acceptanceCriteriaInput')?.value || '').split('\\n').map((line) => line.trim()).filter(Boolean),
      });
      const tasksPayload = () => ({
        tasks: Array.from(document.querySelectorAll('[data-task-index]')).reduce((acc, node) => {
          const index = Number(node.getAttribute('data-task-index') || 0);
          const field = node.getAttribute('data-task-field');
          acc[index] = acc[index] || { id: session.tasks[index]?.id || '' };
          acc[index][field] = node.value;
          return acc;
        }, []).filter(Boolean),
      });

      byId('saveStoryBtn')?.addEventListener('click', () => post('saveEdits', { stage: 'refined_story', values: storyPayload() }));
      byId('regenStoryBtn')?.addEventListener('click', () => post('regenerate', { stage: 'refined_story', userInput: userInput() }));
      byId('approveStoryBtn')?.addEventListener('click', () => post('approve', { stage: 'refined_story' }));
      byId('saveAcceptanceBtn')?.addEventListener('click', () => post('saveEdits', { stage: 'acceptance_criteria', values: acceptancePayload() }));
      byId('regenAcceptanceBtn')?.addEventListener('click', () => post('regenerate', { stage: 'acceptance_criteria', userInput: userInput() }));
      byId('approveAcceptanceBtn')?.addEventListener('click', () => post('approve', { stage: 'acceptance_criteria' }));
      byId('saveTasksBtn')?.addEventListener('click', () => post('saveEdits', { stage: 'tasks', values: tasksPayload() }));
      byId('regenTasksBtn')?.addEventListener('click', () => post('regenerate', { stage: 'tasks', userInput: userInput() }));
      byId('approveTasksBtn')?.addEventListener('click', () => post('approve', { stage: 'tasks' }));
      byId('copyPromptBtn')?.addEventListener('click', () => post('copyPrompt'));
      byId('createWorkItemsBtn')?.addEventListener('click', () => post('createWorkItems'));
    }

    window.addEventListener('message', (event) => {
      if (event.data?.type === 'state') {
        latestState = event.data.state;
        if (latestState.executionWorkspace && currentNav === 'planning' && !latestState.session) {
          currentNav = 'execution';
        }
        render();
      }
    });

    render();
  </script>
</body>
</html>`;
  }
}

function getNonce(): string {
  let text = '';
  const possible = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  for (let index = 0; index < 32; index += 1) {
    text += possible.charAt(Math.floor(Math.random() * possible.length));
  }
  return text;
}
