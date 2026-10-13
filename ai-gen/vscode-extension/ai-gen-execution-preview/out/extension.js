"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.activate = activate;
exports.deactivate = deactivate;
const vscode = __importStar(require("vscode"));
const DEFAULT_LOCAL_BACKEND_URL = 'http://127.0.0.1:8000';
const DEFAULT_RAILWAY_BACKEND_URL = 'https://ai-codegen-production.up.railway.app';
const HEALTH_TIMEOUT_MS = 1800;
let provider;
const state = {
    backend: {
        url: null,
        source: 'none',
        healthy: false,
        reason: 'Backend has not been resolved yet.',
    },
    story: {
        title: '',
        description: '',
        acceptance_criteria: [],
    },
    devPrompt: '',
    uiPrompt: '',
    qaPrompt: '',
    copilotContext: '',
    status: 'Enter a story, then build execution context.',
    error: '',
    loading: false,
};
function activate(context) {
    provider = new ExecutionSidebarProvider(context.extensionUri);
    context.subscriptions.push(vscode.window.registerWebviewViewProvider(ExecutionSidebarProvider.viewType, provider));
    context.subscriptions.push(vscode.commands.registerCommand('ai-gen-execution.openWorkspace', async () => {
        await vscode.commands.executeCommand('workbench.view.extension.aiGenExecution');
    }), vscode.commands.registerCommand('ai-gen-execution.refreshBackend', async () => {
        await refreshBackend();
        provider?.render();
    }));
    void refreshBackend().then(() => provider?.render());
}
function deactivate() {
    provider = undefined;
}
class ExecutionSidebarProvider {
    extensionUri;
    static viewType = 'aiGenExecution.sidebar';
    view;
    constructor(extensionUri) {
        this.extensionUri = extensionUri;
    }
    resolveWebviewView(webviewView) {
        this.view = webviewView;
        webviewView.webview.options = {
            enableScripts: true,
            localResourceRoots: [this.extensionUri],
        };
        webviewView.webview.onDidReceiveMessage((message) => void this.handleMessage(message));
        this.render();
    }
    render() {
        if (!this.view) {
            return;
        }
        this.view.webview.html = htmlForState(state);
    }
    async handleMessage(message) {
        try {
            state.error = '';
            switch (message.command) {
                case 'updateStory':
                    updateStory(message.payload);
                    break;
                case 'buildExecutionContext':
                    await runAction('Building execution context...', buildExecutionContext);
                    break;
                case 'buildDevPrompt':
                    await runAction('Generating Dev prompt...', buildDevPrompt);
                    break;
                case 'buildUiPrompt':
                    await runAction('Generating UI prompt...', buildUiPrompt);
                    break;
                case 'buildQaPrompt':
                    await runAction('Generating QA prompt...', buildQaPrompt);
                    break;
                case 'buildCopilotContext':
                    await runAction('Building Copilot context...', buildCopilotContext);
                    break;
                case 'copy':
                    await copyOutput(String(message.payload || ''));
                    break;
                case 'refreshBackend':
                    await runAction('Refreshing backend...', refreshBackend);
                    break;
            }
        }
        catch (error) {
            state.error = error instanceof Error ? error.message : String(error);
            state.loading = false;
        }
        this.render();
    }
}
async function runAction(status, action) {
    state.loading = true;
    state.status = status;
    provider?.render();
    await action();
    state.loading = false;
}
function updateStory(payload) {
    state.story = {
        title: String(payload.title ?? state.story.title),
        description: String(payload.description ?? state.story.description),
        acceptance_criteria: payload.acceptance_text !== undefined
            ? splitLines(String(payload.acceptance_text))
            : state.story.acceptance_criteria,
    };
}
async function buildExecutionContext() {
    const backendUrl = await ensureBackendUrl();
    const profile = await getProfile(backendUrl);
    state.profile = profile;
    state.executionContext = await postJson(`${backendUrl}/project-intelligence/build-execution-context`, {
        profile,
        knowledge_profile: knowledgeProfile(profile),
        story: state.story,
    });
    state.status = 'Execution context is ready.';
}
async function buildDevPrompt() {
    const backendUrl = await ensureBackendUrl();
    const profile = state.profile || await getProfile(backendUrl);
    const result = await postJson(`${backendUrl}/project-intelligence/build-dev-prompt`, {
        profile,
        knowledge_profile: knowledgeProfile(profile),
        story: state.story,
    });
    state.profile = profile;
    state.devPrompt = result.prompt;
    state.status = 'Dev prompt is ready.';
}
async function buildUiPrompt() {
    const backendUrl = await ensureBackendUrl();
    const profile = state.profile || await getProfile(backendUrl);
    const result = await postJson(`${backendUrl}/project-intelligence/build-ui-prompt`, {
        profile,
        knowledge_profile: knowledgeProfile(profile),
        story: state.story,
    });
    state.profile = profile;
    state.uiPrompt = result.prompt;
    state.status = 'UI prompt is ready.';
}
async function buildQaPrompt() {
    const backendUrl = await ensureBackendUrl();
    const profile = state.profile || await getProfile(backendUrl);
    const result = await postJson(`${backendUrl}/project-intelligence/build-qa-prompt`, {
        profile,
        knowledge_profile: knowledgeProfile(profile),
        story: state.story,
    });
    state.profile = profile;
    state.qaPrompt = result.prompt;
    state.status = 'QA prompt is ready.';
}
async function buildCopilotContext() {
    const backendUrl = await ensureBackendUrl();
    const profile = state.profile || await getProfile(backendUrl);
    const result = await postJson(`${backendUrl}/project-intelligence/build-copilot-context`, {
        profile,
        knowledge_profile: knowledgeProfile(profile),
        story: state.story,
    });
    state.profile = profile;
    state.copilotContext = result.context;
    state.status = 'Copilot context is ready to copy.';
}
async function copyOutput(kind) {
    const value = {
        dev: state.devPrompt,
        ui: state.uiPrompt,
        qa: state.qaPrompt,
        copilot: state.copilotContext,
    }[kind];
    if (!value) {
        throw new Error('Generate this output before copying it.');
    }
    await vscode.env.clipboard.writeText(value);
    state.status = `${labelForKind(kind)} copied. Paste it into Copilot manually.`;
}
function labelForKind(kind) {
    return kind === 'copilot' ? 'Copilot context' : `${kind.toUpperCase()} prompt`;
}
async function getProfile(backendUrl) {
    return getJson(`${backendUrl}/project-intelligence/profile`);
}
function knowledgeProfile(profile) {
    return profile.knowledge_registry || {};
}
async function refreshBackend() {
    state.backend = await resolveBackendUrl();
    state.status = state.backend.healthy ? `Connected to ${state.backend.source} backend.` : state.backend.reason;
}
async function ensureBackendUrl() {
    if (!state.backend.url) {
        await refreshBackend();
    }
    if (!state.backend.url) {
        throw new Error('Unable to reach ai-gen backend. Check the execution preview backend settings.');
    }
    return state.backend.url;
}
async function resolveBackendUrl() {
    const mode = getBackendMode();
    const localUrl = getConfiguredUrl('localBackendUrl', DEFAULT_LOCAL_BACKEND_URL);
    const railwayUrl = getConfiguredUrl('railwayBackendUrl', DEFAULT_RAILWAY_BACKEND_URL);
    const candidates = mode === 'local' ? [['local', localUrl]]
        : mode === 'railway' ? [['railway', railwayUrl]]
            : [['local', localUrl], ['railway', railwayUrl]];
    for (const [source, url] of candidates) {
        if (url && await checkBackendHealth(url)) {
            return { url, source, healthy: true, reason: `Using ${source} backend.` };
        }
    }
    return { url: null, source: 'none', healthy: false, reason: 'No ai-gen backend available.' };
}
function getBackendMode() {
    const mode = vscode.workspace.getConfiguration('ai-gen-execution').get('backendMode', 'auto');
    return mode === 'local' || mode === 'railway' ? mode : 'auto';
}
function getConfiguredUrl(key, fallback) {
    return normalizeBaseUrl(vscode.workspace.getConfiguration('ai-gen-execution').get(key, fallback));
}
async function checkBackendHealth(url) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), HEALTH_TIMEOUT_MS);
    try {
        const response = await fetch(`${normalizeBaseUrl(url)}/health`, { method: 'GET', signal: controller.signal });
        return response.ok;
    }
    catch {
        return false;
    }
    finally {
        clearTimeout(timeout);
    }
}
async function getJson(url) {
    const response = await fetch(url, { method: 'GET' });
    if (!response.ok) {
        throw new Error(`Backend returned HTTP ${response.status}: ${await response.text()}`);
    }
    return await response.json();
}
async function postJson(url, body) {
    const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    if (!response.ok) {
        throw new Error(`Backend returned HTTP ${response.status}: ${await response.text()}`);
    }
    return await response.json();
}
function htmlForState(next) {
    const acceptanceText = next.story.acceptance_criteria.join('\n');
    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <style>
    body { color: var(--vscode-foreground); background: var(--vscode-sideBar-background); font-family: var(--vscode-font-family); padding: 12px; }
    h1 { font-size: 18px; margin: 0 0 10px; }
    h2 { font-size: 13px; margin: 0 0 8px; text-transform: uppercase; letter-spacing: 0; color: var(--vscode-descriptionForeground); }
    section { border: 1px solid var(--vscode-panel-border); border-radius: 6px; padding: 10px; margin-bottom: 12px; background: var(--vscode-editor-background); }
    label { display: block; font-size: 12px; color: var(--vscode-descriptionForeground); margin: 8px 0 4px; }
    input, textarea { width: 100%; box-sizing: border-box; color: var(--vscode-input-foreground); background: var(--vscode-input-background); border: 1px solid var(--vscode-input-border); border-radius: 4px; padding: 7px; font-family: var(--vscode-font-family); }
    textarea { min-height: 72px; resize: vertical; }
    button { color: var(--vscode-button-foreground); background: var(--vscode-button-background); border: 0; border-radius: 4px; padding: 7px 9px; margin: 6px 6px 0 0; cursor: pointer; }
    button.secondary { color: var(--vscode-button-secondaryForeground); background: var(--vscode-button-secondaryBackground); }
    button:disabled { opacity: .55; cursor: not-allowed; }
    pre { white-space: pre-wrap; word-break: break-word; background: var(--vscode-textCodeBlock-background); padding: 8px; border-radius: 4px; max-height: 260px; overflow: auto; }
    .status { color: var(--vscode-descriptionForeground); font-size: 12px; margin-bottom: 10px; }
    .error { background: var(--vscode-inputValidation-errorBackground); border: 1px solid var(--vscode-inputValidation-errorBorder); padding: 8px; border-radius: 4px; margin-bottom: 10px; }
    .grid { display: grid; gap: 6px; }
    .row { display: flex; justify-content: space-between; gap: 10px; border-bottom: 1px solid var(--vscode-panel-border); padding: 4px 0; }
    .row span:first-child { color: var(--vscode-descriptionForeground); }
  </style>
</head>
<body>
  <h1>Project Intelligence</h1>
  <div class="status">${escapeHtml(next.status)} ${next.loading ? 'Working...' : ''}</div>
  ${next.error ? `<div class="error">${escapeHtml(next.error)}</div>` : ''}
  <section>
    <h2>Story Context</h2>
    <label>Story Title</label>
    <input id="title" value="${escapeAttr(next.story.title)}" placeholder="Display Fault Event Details" />
    <label>Story Description</label>
    <textarea id="description" placeholder="Describe the approved story.">${escapeHtml(next.story.description)}</textarea>
    <label>Acceptance Criteria</label>
    <textarea id="acceptance" placeholder="One acceptance criterion per line">${escapeHtml(acceptanceText)}</textarea>
    <button data-command="buildExecutionContext">Build Execution Context</button>
  </section>
  <section>
    <h2>Execution Readiness Panel</h2>
    ${readinessRows(next)}
  </section>
  <section>
    <h2>Impact Analysis</h2>
    ${contextRows(next.executionContext)}
  </section>
  <section>
    <h2>Execution Context</h2>
    ${executionContextHtml(next.executionContext)}
  </section>
  ${promptSection('Dev Prompt', 'buildDevPrompt', 'copy', 'dev', next.devPrompt)}
  ${promptSection('UI Prompt', 'buildUiPrompt', 'copy', 'ui', next.uiPrompt)}
  ${promptSection('QA Prompt', 'buildQaPrompt', 'copy', 'qa', next.qaPrompt)}
  ${promptSection('Copilot Context', 'buildCopilotContext', 'copy', 'copilot', next.copilotContext)}
  <script>
    const vscode = acquireVsCodeApi();
    const title = document.getElementById('title');
    const description = document.getElementById('description');
    const acceptance = document.getElementById('acceptance');
    function updateStory() {
      vscode.postMessage({ command: 'updateStory', payload: { title: title.value, description: description.value, acceptance_text: acceptance.value } });
    }
    title.addEventListener('change', updateStory);
    description.addEventListener('change', updateStory);
    acceptance.addEventListener('change', updateStory);
    document.querySelectorAll('button[data-command]').forEach((button) => {
      button.addEventListener('click', () => {
        updateStory();
        vscode.postMessage({ command: button.dataset.command, payload: button.dataset.payload || '' });
      });
    });
  </script>
</body>
</html>`;
}
function readinessRows(next) {
    const profile = next.profile;
    const registry = profile?.knowledge_registry;
    const repo = profile?.repository_connection;
    return [
        row('Project Profile', profile ? 'Ready' : 'Missing'),
        row('Repository Intelligence', repo?.status === 'README analyzed' ? 'Ready' : profile ? 'Partial' : 'Missing'),
        row('Knowledge Registry', registry?.modules?.length || registry?.flows?.length ? 'Ready' : profile ? 'Partial' : 'Missing'),
        row('Impact Analysis', next.executionContext ? 'Ready' : 'Missing'),
        row('Execution Context', next.executionContext?.execution_readiness || 'Missing'),
    ].join('');
}
function contextRows(context) {
    if (!context) {
        return '<div class="status">Impact analysis is built as part of execution context.</div>';
    }
    return [
        row('Applications', context.affected_applications.join(', ') || 'Not identified'),
        row('Modules', context.affected_modules.join(', ') || 'Not identified'),
        row('Flows', context.affected_flows.join(', ') || 'Not identified'),
        row('Dependencies', context.dependencies.join(', ') || 'Not identified'),
        row('Risks', context.risks.join(', ') || 'Not identified'),
    ].join('');
}
function executionContextHtml(context) {
    if (!context) {
        return '<div class="status">Build execution context to see project-aware implementation guidance.</div>';
    }
    return [
        row('Story Summary', context.story_summary),
        row('Acceptance Criteria', context.acceptance_criteria.join(', ') || 'Not identified'),
        row('Technology Stack', formatStack(context.technology_stack) || 'Not identified'),
        row('Development Standards', formatStandards(context.development_standards) || 'Not identified'),
        row('Recommended Files', context.recommended_files.join(', ') || 'Inspect affected modules first'),
        row('Implementation Notes', context.implementation_notes.join(', ') || 'Not identified'),
        row('Execution Readiness', context.execution_readiness),
    ].join('');
}
function formatStack(stack) {
    return Object.entries(stack || {})
        .filter(([, values]) => Array.isArray(values) && values.length > 0)
        .map(([key, values]) => `${key}: ${values.join(', ')}`)
        .join('; ');
}
function formatStandards(standards) {
    return Object.values(standards || {})
        .flatMap((values) => Array.isArray(values) ? values : [])
        .join(', ');
}
function promptSection(title, buildCommand, copyCommand, payload, value) {
    return `<section>
    <h2>${escapeHtml(title)}</h2>
    <button data-command="${buildCommand}">Generate ${escapeHtml(title)}</button>
    <button class="secondary" data-command="${copyCommand}" data-payload="${payload}" ${value ? '' : 'disabled'}>Copy ${escapeHtml(title)}</button>
    ${value ? `<pre>${escapeHtml(value)}</pre>` : '<div class="status">Not generated yet.</div>'}
  </section>`;
}
function row(label, value) {
    return `<div class="row"><span>${escapeHtml(label)}</span><span>${escapeHtml(value)}</span></div>`;
}
function splitLines(value) {
    return value.split(/\n|,/).map((item) => item.trim()).filter(Boolean);
}
function normalizeBaseUrl(value) {
    const trimmed = value.trim();
    if (!trimmed) {
        return '';
    }
    const withScheme = /^https?:\/\//i.test(trimmed) ? trimmed : `${defaultScheme(trimmed)}://${trimmed}`;
    return withScheme.replace(/\/+$/, '');
}
function defaultScheme(value) {
    return /^(localhost|127\.0\.0\.1|0\.0\.0\.0)(:\d+)?($|\/)/i.test(value) ? 'http' : 'https';
}
function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, (char) => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;',
    }[char] || char));
}
function escapeAttr(value) {
    return escapeHtml(value).replace(/`/g, '&#96;');
}
//# sourceMappingURL=extension.js.map