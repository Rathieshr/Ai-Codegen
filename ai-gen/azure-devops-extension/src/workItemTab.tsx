import * as SDK from 'azure-devops-extension-sdk';
import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  AiGenState,
  approvePipelineStage,
  createPipeline,
  generateFromCurrentWorkItem,
  HandoffRecord,
  loadGeneratedState,
  loadHandoff,
  loadLatestHandoff,
  PipelineStageState,
  saveGeneratedState,
  skipPipelineStage,
  runPipelineStage
} from './api';
import './styles.css';

type ViewState = {
  loading: boolean;
  error: string;
  data?: AiGenState;
};

const STAGE_ORDER = ['ba', 'ui', 'dev', 'test', 'critic'];

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

  const workItem = state.data?.workItem;
  const response = state.data?.response;
  const capabilities = state.data?.capabilities;
  const pipeline = state.data?.pipeline;
  const currentStageName = useMemo(() => activeStageName(pipeline), [pipeline]);
  const currentStage = currentStageName && pipeline ? pipeline.stages[currentStageName] : undefined;

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

  async function withPipelineUpdate(action: () => Promise<AiGenState>) {
    setState((current) => ({ ...current, loading: true, error: '' }));
    try {
      const next = await action();
      saveGeneratedState(next);
      setState({ loading: false, error: '', data: next });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Pipeline action failed';
      setState((current) => ({ ...current, loading: false, error: message }));
    }
  }

  async function createOrRefreshPipeline() {
    if (!state.data?.workItem || !state.data?.response) {
      return;
    }
    await withPipelineUpdate(async () => {
      const pipelineData = await createPipeline(state.data!.workItem, state.data!.response);
      return { ...state.data!, pipeline: pipelineData };
    });
  }

  async function generateStage(regenerate = false) {
    if (!state.data?.pipeline || !currentStageName) {
      return;
    }
    await withPipelineUpdate(async () => {
      const pipelineData = await runPipelineStage(state.data!.pipeline!.pipeline_id, currentStageName, regenerate);
      const handoff = pipelineData.stages[currentStageName]?.handoff_id
        ? await loadHandoff(pipelineData.stages[currentStageName].handoff_id || '')
        : state.data?.handoff;
      return { ...state.data!, pipeline: pipelineData, handoff };
    });
  }

  async function approveStage() {
    if (!state.data?.pipeline || !currentStageName) {
      return;
    }
    await withPipelineUpdate(async () => {
      const pipelineData = await approvePipelineStage(state.data!.pipeline!.pipeline_id, currentStageName);
      const handoff = await loadLatestHandoff(state.data!.workItem.id, currentStageName, 'approved');
      return { ...state.data!, pipeline: pipelineData, handoff: handoff || state.data!.handoff };
    });
  }

  async function skipUi() {
    if (!state.data?.pipeline) {
      return;
    }
    await withPipelineUpdate(async () => {
      const pipelineData = await skipPipelineStage(state.data!.pipeline!.pipeline_id, 'ui', 'backend-only task');
      return { ...state.data!, pipeline: pipelineData };
    });
  }

  async function viewCurrentHandoff() {
    if (!state.data || !currentStage?.handoff_id) {
      return;
    }
    await withPipelineUpdate(async () => {
      const handoff = await loadHandoff(currentStage.handoff_id || '');
      return { ...state.data!, handoff: handoff || state.data!.handoff };
    });
  }

  const showRefinement = Boolean(
    response?.refinement_used
    || response?.refined_variant
    || response?.refined_surface
    || response?.refined_fields?.length
    || response?.refined_validations?.length
    || response?.refined_scope?.length
    || response?.refinement_unknowns?.length
  );

  return (
    <main className="ai-gen-page">
      <div className="ai-gen-header">
        <div>
          <h1 className="ai-gen-title">ai-gen</h1>
          <div className="ai-gen-muted">Convert this work item into an execution packet and a staged assistant pipeline.</div>
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
        <h2>AI Pipeline</h2>
        {!pipeline ? (
          <div className="ai-gen-actions">
            <button className="ai-gen-button" onClick={createOrRefreshPipeline} disabled={state.loading || !response?.optimized_prompt}>
              Create Pipeline
            </button>
            <span className="ai-gen-muted">Create BA, UI, Dev, Test, and Critic stages for this work item.</span>
          </div>
        ) : (
          <>
            <div className="ai-gen-stage-bar">
              {STAGE_ORDER.map((stage) => (
                <div
                  key={stage}
                  className={`ai-gen-stage-chip ${pipeline.stages[stage]?.status || 'locked'} ${currentStageName === stage ? 'active' : ''}`}
                >
                  <span>{stage.toUpperCase()}</span>
                  <small>{pipeline.stages[stage]?.status || 'locked'}</small>
                </div>
              ))}
            </div>
            <div className="ai-gen-grid">
              <span className="ai-gen-key">Pipeline ID</span>
              <span>{pipeline.pipeline_id}</span>
              <span className="ai-gen-key">Current Stage</span>
              <span>{currentStageName || 'None'}</span>
              <span className="ai-gen-key">Stage Status</span>
              <span>{currentStage?.status || 'Unknown'}</span>
            </div>
            <div className="ai-gen-actions">
              <button className="ai-gen-button" onClick={() => generateStage(false)} disabled={state.loading || !currentStageName}>
                Generate
              </button>
              <button className="ai-gen-button secondary" onClick={() => generateStage(true)} disabled={state.loading || !currentStageName}>
                Regenerate
              </button>
              <button className="ai-gen-button secondary" onClick={approveStage} disabled={state.loading || !currentStageName || !currentStage?.output}>
                Approve &amp; Continue
              </button>
              <button className="ai-gen-button secondary" onClick={skipUi} disabled={state.loading || currentStageName !== 'ui'}>
                Skip UI
              </button>
              <button className="ai-gen-button secondary" onClick={viewCurrentHandoff} disabled={state.loading || !currentStage?.handoff_id}>
                View Handoff
              </button>
            </div>
            {currentStage ? <StagePanel stage={currentStageName} stageState={currentStage} /> : null}
            {state.data?.handoff ? <PipelineHandoff handoff={state.data.handoff} /> : null}
          </>
        )}
      </section>

      <section className="ai-gen-section">
        <h2>Status</h2>
        <div className="ai-gen-grid">
          <span className="ai-gen-key">Backend</span>
          <span>{capabilities?.backend_up ? 'Connected' : 'Unknown'}</span>
          <span className="ai-gen-key">Refiner</span>
          <span>{capabilities?.refiner?.enabled ? 'Enabled' : 'Disabled'}</span>
          <span className="ai-gen-key">Provider</span>
          <span>{capabilities?.refiner?.provider || 'Not configured'}</span>
          <span className="ai-gen-key">Model</span>
          <span>{capabilities?.refiner?.model || 'Not configured'}</span>
          <span className="ai-gen-key">Configured</span>
          <span>{capabilities?.refiner?.configured ? 'Yes' : 'No'}</span>
        </div>
      </section>

      {showRefinement && (
        <section className="ai-gen-section">
          <h2>Refinement</h2>
          <div className="ai-gen-grid">
            <span className="ai-gen-key">Used</span>
            <span>{response?.refinement_used ? 'Yes' : 'No'}</span>
            <span className="ai-gen-key">Provider</span>
            <span>{response?.refinement_provider || 'Backend'}</span>
            <span className="ai-gen-key">Confidence</span>
            <span>{response?.refinement_confidence || 'Unknown'}</span>
            <span className="ai-gen-key">Reason</span>
            <span>{response?.refinement_reason || 'Not provided'}</span>
            <span className="ai-gen-key">Base Flow</span>
            <span>{response?.refined_base_flow || 'Not refined'}</span>
            <span className="ai-gen-key">Variant</span>
            <span>{response?.refined_variant || 'Not refined'}</span>
            <span className="ai-gen-key">Surface</span>
            <span>{response?.refined_surface || 'Not refined'}</span>
          </div>
          {response?.refined_fields?.length ? (
            <ListSection title="Fields" items={response.refined_fields} />
          ) : null}
          {response?.refined_validations?.length ? (
            <ListSection title="Validations" items={response.refined_validations} />
          ) : null}
          {response?.refined_scope?.length ? (
            <ListSection title="Refined Scope" items={response.refined_scope} />
          ) : null}
          {response?.refinement_unknowns?.length ? (
            <WarningSection title="Open Questions" items={response.refinement_unknowns} />
          ) : null}
        </section>
      )}

      <section className="ai-gen-section">
        <h2>Execution Prompt</h2>
        {response?.refined_scope?.length ? (
          <ListSection title="Refined Scope" items={response.refined_scope} />
        ) : null}
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

function StagePanel({ stage, stageState }: { stage: string; stageState: PipelineStageState }) {
  return (
    <div className="ai-gen-subsection">
      <div className="ai-gen-key">Current Stage Panel</div>
      <div className="ai-gen-grid">
        <span className="ai-gen-key">Stage</span>
        <span>{stage.toUpperCase()}</span>
        <span className="ai-gen-key">Status</span>
        <span>{stageState.status}</span>
        <span className="ai-gen-key">Approved</span>
        <span>{stageState.approved ? 'Yes' : 'No'}</span>
        <span className="ai-gen-key">Version</span>
        <span>{stageState.version}</span>
      </div>
      {stageState.critic ? (
        <div className="ai-gen-subsection">
          <div className="ai-gen-key">Critic Review</div>
          <pre className="ai-gen-prompt">{JSON.stringify(stageState.critic, null, 2)}</pre>
        </div>
      ) : null}
      {Object.keys(stageState.output || {}).length ? (
        <pre className="ai-gen-prompt">{JSON.stringify(stageState.output, null, 2)}</pre>
      ) : (
        <div className="ai-gen-muted">No stage output yet.</div>
      )}
    </div>
  );
}

function PipelineHandoff({ handoff }: { handoff: HandoffRecord }) {
  return (
    <div className="ai-gen-subsection">
      <div className="ai-gen-key">Handoff</div>
      <div className="ai-gen-grid">
        <span className="ai-gen-key">ID</span>
        <span>{handoff.handoff_id}</span>
        <span className="ai-gen-key">Stage</span>
        <span>{handoff.stage}</span>
        <span className="ai-gen-key">Status</span>
        <span>{handoff.status}</span>
        <span className="ai-gen-key">Summary</span>
        <span>{handoff.summary || 'No summary yet'}</span>
      </div>
      {handoff.constraints?.length ? <ListSection title="Constraints" items={handoff.constraints} /> : null}
      {handoff.open_questions?.length ? <WarningSection title="Open Questions" items={handoff.open_questions} /> : null}
      {handoff.next_actions?.length ? <ListSection title="Next Actions" items={handoff.next_actions} /> : null}
      <pre className="ai-gen-prompt">{JSON.stringify(handoff.content || {}, null, 2)}</pre>
    </div>
  );
}

function ListSection({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="ai-gen-subsection">
      <div className="ai-gen-key">{title}</div>
      <ul className="ai-gen-list">
        {items.map((item) => <li key={item}>{item}</li>)}
      </ul>
    </div>
  );
}

function WarningSection({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="ai-gen-warning">
      <div className="ai-gen-key">{title}</div>
      <ul className="ai-gen-list">
        {items.map((item) => <li key={item}>{item}</li>)}
      </ul>
    </div>
  );
}

function activeStageName(pipeline?: AiGenState['pipeline']): string {
  if (!pipeline) {
    return '';
  }
  for (const stage of STAGE_ORDER) {
    const stageState = pipeline.stages[stage];
    if (!stageState) {
      continue;
    }
    if (stageState.status === 'generated' || stageState.status === 'needs_revision' || stageState.status === 'pending') {
      return stage;
    }
  }
  return pipeline.current_stage || 'critic';
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
