import * as SDK from 'azure-devops-extension-sdk';
import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  AiGenState,
  generateFromCurrentWorkItem,
  loadGeneratedState,
  saveGeneratedState
} from './api';
import './styles.css';

type ViewState = {
  loading: boolean;
  error: string;
  data?: AiGenState;
};

function WorkItemTab() {
  const [state, setState] = useState<ViewState>({
    loading: false,
    error: '',
    data: loadGeneratedState()
  });

  useEffect(() => {
    SDK.init({ loaded: false, applyTheme: true });
    SDK.ready().then(() => {
      SDK.notifyLoadSucceeded();
      if (!state.data) {
        refresh();
      }
    }).catch(() => {
      setState({ loading: false, error: 'Unable to initialize Azure DevOps SDK.' });
    });
  }, []);

  async function refresh() {
    setState((current) => ({ ...current, loading: true, error: '' }));
    try {
      const data = await generateFromCurrentWorkItem();
      saveGeneratedState(data);
      setState({ loading: false, error: '', data });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to generate ai-gen prompt';
      setState((current) => ({ ...current, loading: false, error: message }));
    }
  }

  async function copyPrompt() {
    const prompt = state.data?.response.optimized_prompt || '';
    if (!prompt) {
      return;
    }
    await navigator.clipboard.writeText(prompt);
  }

  const workItem = state.data?.workItem;
  const response = state.data?.response;

  return (
    <main className="ai-gen-page">
      <div className="ai-gen-header">
        <div>
          <h1 className="ai-gen-title">ai-gen</h1>
          <div className="ai-gen-muted">Convert this work item into a Codex-ready execution packet.</div>
        </div>
        <button className="ai-gen-button secondary" onClick={refresh} disabled={state.loading}>
          {state.loading ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      {state.error && (
        <div className="ai-gen-error">Unable to generate ai-gen prompt: {state.error}</div>
      )}

      <section className="ai-gen-section">
        <h2>Work Item Summary</h2>
        <div className="ai-gen-grid">
          <span className="ai-gen-key">Title</span>
          <span>{workItem?.title || 'Not loaded'}</span>
          <span className="ai-gen-key">Type</span>
          <span>{workItem?.type || 'Unknown'}</span>
          <span className="ai-gen-key">Tags</span>
          <span>{workItem?.tags.join(', ') || 'None'}</span>
        </div>
      </section>

      <section className="ai-gen-section">
        <h2>ai-gen Output</h2>
        <div className="ai-gen-grid">
          <span className="ai-gen-key">Detected Flow</span>
          <span>{response?.detected_flow || 'Not detected'}</span>
          <span className="ai-gen-key">Prompt Mode</span>
          <span>{response?.prompt_mode || 'Unknown'}</span>
          <span className="ai-gen-key">Execution Confidence</span>
          <span>{formatConfidence(response)}</span>
          <span className="ai-gen-key">Selected Files</span>
          <span>{response?.selected_execution_files?.join(', ') || 'None selected'}</span>
        </div>
      </section>

      <section className="ai-gen-section">
        <h2>Execution Prompt</h2>
        <pre className="ai-gen-prompt">{response?.optimized_prompt || 'Generate a prompt to preview it here.'}</pre>
      </section>

      <section className="ai-gen-section">
        <h2>Actions</h2>
        <div className="ai-gen-actions">
          <button className="ai-gen-button" onClick={copyPrompt} disabled={!response?.optimized_prompt}>
            Copy Prompt
          </button>
          <button className="ai-gen-button secondary" onClick={refresh} disabled={state.loading}>
            Refresh
          </button>
        </div>
        <p className="ai-gen-muted">
          Send to Codex from your IDE or terminal after copying the prompt.
        </p>
      </section>
    </main>
  );
}

function formatConfidence(response?: { execution_confidence?: number; execution_confidence_level?: string }) {
  if (!response) {
    return 'Unknown';
  }
  const level = response.execution_confidence_level || 'unknown';
  const score = typeof response.execution_confidence === 'number' ? ` (${response.execution_confidence})` : '';
  return `${level}${score}`;
}

const rootElement = document.getElementById('root');
if (rootElement) {
  createRoot(rootElement).render(<WorkItemTab />);
}
