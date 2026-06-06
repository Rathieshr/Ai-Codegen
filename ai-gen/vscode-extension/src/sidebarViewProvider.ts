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
  backendStatus: string;
  backendUrl: string;
  loading: boolean;
  loadingMessage: string;
  errorMessage: string;
  session?: PlannerSession;
};

type SidebarHandlers = {
  startPlanning(requirement: string): Promise<PlannerViewState>;
  saveEdits(stage: string, payload: Record<string, unknown>): Promise<PlannerViewState>;
  regenerate(stage: string, userInput: string): Promise<PlannerViewState>;
  approve(stage: string): Promise<PlannerViewState>;
  copyPrompt(): Promise<PlannerViewState>;
  createWorkItems(): Promise<PlannerViewState>;
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
  <title>AI Story Planner</title>
  <style>
    body { margin: 0; padding: 16px; color: var(--vscode-foreground); background: var(--vscode-editor-background); font-family: var(--vscode-font-family); }
    h1,h2,h3 { margin: 0; }
    .page { display: grid; gap: 16px; }
    .hero { display: grid; gap: 6px; }
    .muted { color: var(--vscode-descriptionForeground); }
    .card { border: 1px solid var(--vscode-input-border); border-radius: 6px; padding: 14px; background: var(--vscode-sideBar-background); display: grid; gap: 12px; }
    .stage-row { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 8px; }
    .stage-chip { border: 1px solid var(--vscode-input-border); border-radius: 6px; padding: 8px; background: var(--vscode-editor-background); font-size: 12px; }
    .stage-chip.active { border-color: var(--vscode-focusBorder); }
    .stage-chip.done { background: color-mix(in srgb, var(--vscode-button-background) 18%, transparent); }
    .label { font-size: 12px; color: var(--vscode-descriptionForeground); }
    textarea, input[type="text"] { width: 100%; box-sizing: border-box; color: var(--vscode-input-foreground); background: var(--vscode-input-background); border: 1px solid var(--vscode-input-border); border-radius: 4px; padding: 8px; }
    textarea { min-height: 96px; resize: vertical; }
    .actions { display: flex; gap: 8px; flex-wrap: wrap; }
    button { border: 0; border-radius: 4px; padding: 7px 12px; cursor: pointer; color: var(--vscode-button-foreground); background: var(--vscode-button-background); }
    button.secondary { color: var(--vscode-button-secondaryForeground); background: var(--vscode-button-secondaryBackground); }
    button:disabled { opacity: 0.6; cursor: not-allowed; }
    ul { margin: 0; padding-left: 18px; }
    .status { font-size: 12px; color: var(--vscode-descriptionForeground); }
    .error { border: 1px solid var(--vscode-errorForeground); color: var(--vscode-errorForeground); border-radius: 6px; padding: 10px; }
    .success { border: 1px solid var(--vscode-testing-iconPassed); border-radius: 6px; padding: 10px; }
    .task { border: 1px solid var(--vscode-input-border); border-radius: 6px; padding: 10px; display: grid; gap: 8px; }
    .task-header { display: flex; justify-content: space-between; gap: 8px; align-items: center; }
    .two-col { display: grid; gap: 12px; }
    .readout { white-space: pre-wrap; border: 1px solid var(--vscode-input-border); border-radius: 6px; padding: 10px; background: var(--vscode-textCodeBlock-background); }
  </style>
</head>
<body>
  <div id="app" class="page"></div>
  <script nonce="${nonce}">
    const vscode = acquireVsCodeApi();
    const app = document.getElementById('app');
    let latestState = {
      backendStatus: 'unknown',
      backendUrl: '',
      loading: false,
      loadingMessage: '',
      errorMessage: '',
      session: undefined,
    };

    const stageLabels = {
      requirement: 'Requirement',
      refined_story: 'Refined Story',
      acceptance_criteria: 'Acceptance Criteria',
      tasks: 'Tasks',
      azure_devops_creation: 'Azure DevOps',
      success: 'Success Summary',
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

    function renderRequirementStart() {
      return \`
        <div class="card">
          <div class="hero">
            <h1>AI Story Planner</h1>
            <div class="muted">Turn a requirement into an approved user story, acceptance criteria, tasks, and Azure DevOps work items.</div>
          </div>
          <div class="label">Requirement</div>
          <textarea id="requirementInput" placeholder="As a customer, I want OTP login so I can securely access my account."></textarea>
          <div class="actions">
            <button id="startBtn">Start Planning</button>
            <button class="secondary" id="refreshBtn">Refresh</button>
          </div>
        </div>
      \`;
    }

    function stageRow(session) {
      const order = ['requirement', 'refined_story', 'acceptance_criteria', 'tasks', 'azure_devops_creation', 'success'];
      return '<div class="stage-row">' + order.map((stage) => {
        const done =
          stage === 'requirement' ? true :
          stage === 'refined_story' ? session.story_approved :
          stage === 'acceptance_criteria' ? session.acceptance_approved :
          stage === 'tasks' ? session.tasks_approved :
          stage === 'azure_devops_creation' ? session.current_stage === 'success' || session.current_stage === 'azure_devops_creation' :
          session.current_stage === 'success';
        const active = session.current_stage === stage;
        const status =
          stage === 'requirement' ? 'Entered' :
          stage === 'azure_devops_creation' && session.current_stage === 'azure_devops_creation' ? 'Ready' :
          done ? 'Approved' : active ? 'Current' : 'Pending';
        return \`<div class="stage-chip \${done ? 'done' : ''} \${active ? 'active' : ''}"><strong>\${stageLabels[stage]}</strong><div class="status">\${status}</div></div>\`;
      }).join('') + '</div>';
    }

    function storyFields(session) {
      return \`
        <div class="two-col">
          <div>
            <div class="label">Title</div>
            <input type="text" id="storyTitle" value="\${escapeHtml(session.story.title)}" />
          </div>
          <div>
            <div class="label">Business Value</div>
            <textarea id="storyBusinessValue">\${escapeHtml(session.story.business_value)}</textarea>
          </div>
          <div>
            <div class="label">Description</div>
            <textarea id="storyDescription">\${escapeHtml(session.story.description)}</textarea>
          </div>
        </div>
      \`;
    }

    function acceptanceFields(session) {
      return \`
        <div>
          <div class="label">Acceptance Criteria</div>
          <textarea id="acceptanceCriteriaInput">\${escapeHtml((session.acceptance_criteria || []).join('\\n'))}</textarea>
        </div>
      \`;
    }

    function taskFields(session) {
      return '<div class="two-col">' + (session.tasks || []).map((task, index) => \`
        <div class="task">
          <div class="task-header">
            <strong>Task \${index + 1}</strong>
            <span class="status">\${task.azure_work_item_id ? 'Created in Azure DevOps' : task.status === 'failed' ? 'Failed' : 'Not created yet'}</span>
          </div>
          <div>
            <div class="label">Task Title</div>
            <input type="text" data-task-field="title" data-task-index="\${index}" value="\${escapeHtml(task.title)}" />
          </div>
          <div>
            <div class="label">Task Description</div>
            <textarea data-task-field="description" data-task-index="\${index}">\${escapeHtml(task.description)}</textarea>
          </div>
          <div>
            <div class="label">Estimated Effort</div>
            <input type="text" data-task-field="estimated_effort" data-task-index="\${index}" value="\${escapeHtml(task.estimated_effort || '')}" />
          </div>
        </div>
      \`).join('') + '</div>';
    }

    function promptView(session) {
      return \`
        <div>
          <div class="label">Final Code Generation Prompt</div>
          <div class="readout">\${escapeHtml(session.code_generation_prompt || '')}</div>
        </div>
      \`;
    }

    function successView(session) {
      const storyLine = session.created_summary?.story?.azure_work_item_id
        ? 'User Story #' + session.created_summary.story.azure_work_item_id + ' created.'
        : 'User Story was not created.';
      const taskLines = (session.created_summary?.tasks || []).map((task) => '<li>' + escapeHtml(task.title + ': ' + (task.status === 'created' ? 'Created #' + task.azure_work_item_id : 'Failed')) + '</li>').join('');
      return \`
        <div class="success">
          <strong>Work item creation finished.</strong>
          <div class="muted">\${escapeHtml(storyLine)}</div>
          <ul>\${taskLines || '<li>No child tasks were created.</li>'}</ul>
        </div>
      \`;
    }

    function actionButtons(session) {
      if (session.current_stage === 'refined_story') {
        return \`
          <div class="actions">
            <button id="saveStoryBtn" class="secondary">Edit</button>
            <button id="regenStoryBtn" class="secondary">Regenerate</button>
            <button id="approveStoryBtn">Approve</button>
          </div>
        \`;
      }
      if (session.current_stage === 'acceptance_criteria') {
        return \`
          <div class="actions">
            <button id="saveAcceptanceBtn" class="secondary">Edit</button>
            <button id="regenAcceptanceBtn" class="secondary">Regenerate</button>
            <button id="approveAcceptanceBtn">Approve</button>
          </div>
        \`;
      }
      if (session.current_stage === 'tasks') {
        return \`
          <div class="actions">
            <button id="saveTasksBtn" class="secondary">Edit</button>
            <button id="regenTasksBtn" class="secondary">Regenerate</button>
            <button id="approveTasksBtn">Approve</button>
          </div>
        \`;
      }
      if (session.current_stage === 'azure_devops_creation') {
        return \`
          <div class="actions">
            <button id="copyPromptBtn" class="secondary">Copy Prompt</button>
            <button id="createWorkItemsBtn" class="secondary">Create Azure DevOps Work Items</button>
          </div>
        \`;
      }
      return '<div class="actions"><button id="refreshBtn">Refresh</button></div>';
    }

    function currentStageBody(session) {
      if (session.current_stage === 'refined_story') return storyFields(session);
      if (session.current_stage === 'acceptance_criteria') return acceptanceFields(session);
      if (session.current_stage === 'tasks') return taskFields(session);
      if (session.current_stage === 'azure_devops_creation') return promptView(session);
      return successView(session);
    }

    function sessionView(session) {
      return \`
        <div class="card">
          <div class="hero">
            <h1>AI Story Planner</h1>
            <div class="muted">Guide one requirement through story approval, task planning, and Azure DevOps creation.</div>
          </div>
          \${stageRow(session)}
          <div>
            <div class="label">Current Question</div>
            <div>\${escapeHtml(session.question || '')}</div>
          </div>
          \${(session.current_stage === 'refined_story' || session.current_stage === 'acceptance_criteria' || session.current_stage === 'tasks') ? \`
            <div>
              <div class="label">Your Input</div>
              <textarea id="activeUserInput" placeholder="\${escapeHtml(session.user_input_hint || '')}"></textarea>
            </div>
          \` : ''}
          \${currentStageBody(session)}
          \${actionButtons(session)}
          <div class="status">Last updated: \${escapeHtml(session.updated_at || '')}</div>
        </div>
      \`;
    }

    function render() {
      const error = latestState.errorMessage ? '<div class="error">' + escapeHtml(latestState.errorMessage) + '</div>' : '';
      const loading = latestState.loading ? '<div class="status">' + escapeHtml(latestState.loadingMessage || 'Working...') + '</div>' : '';
      app.innerHTML = error + loading + (latestState.session ? sessionView(latestState.session) : renderRequirementStart());
      wireEvents();
    }

    function wireEvents() {
      const byId = (id) => document.getElementById(id);
      const startBtn = byId('startBtn');
      if (startBtn) {
        startBtn.onclick = () => post('startPlanning', { requirement: byId('requirementInput').value });
      }
      const refreshBtn = byId('refreshBtn');
      if (refreshBtn) {
        refreshBtn.onclick = () => post('refreshState');
      }
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
