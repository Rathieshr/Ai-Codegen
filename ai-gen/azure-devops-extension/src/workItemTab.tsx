import * as SDK from 'azure-devops-extension-sdk';
import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  clearGeneratedState,
  AiGenState,
  approvePipelineStage,
  addStageFeedback,
  buildVsCodeHandoffLink,
  createPipeline,
  getCurrentWorkItem,
  generateFromCurrentWorkItem,
  HandoffRecord,
  loadGeneratedState,
  loadHandoff,
  loadHandoffMarkdown,
  loadPipelineForWorkItem,
  PipelineStageState,
  refreshPipelineState,
  saveGeneratedState,
  skipPipelineStage,
  runPipelineStage
} from './api';
import './styles.css';

type ViewState = {
  loading: boolean;
  loadingMessage: string;
  error: string;
  data?: AiGenState;
};

const STAGE_ORDER = ['ba', 'ui', 'dev', 'test', 'critic'];

function WorkItemTab() {
  const [state, setState] = useState<ViewState>({
    loading: false,
    loadingMessage: '',
    error: '',
    data: loadGeneratedState()
  });
  const [clarification, setClarification] = useState('');

  useEffect(() => {
    SDK.init({ loaded: false, applyTheme: true });
    SDK.ready().then(() => {
      SDK.notifyLoadSucceeded();
      void refresh();
    }).catch(() => {
      setState({ loading: false, loadingMessage: '', error: 'Unable to initialize Azure DevOps SDK.' });
    });
  }, []);

  useEffect(() => {
    let disposed = false;
    let timer: number | undefined;

    const tick = async () => {
      if (disposed || document.visibilityState !== 'visible') {
        return;
      }
      try {
        const workItem = await getSafeCurrentWorkItemId();
        const currentWorkItemId = state.data?.workItem?.id;
        if (workItem && currentWorkItemId && String(workItem) !== String(currentWorkItemId)) {
          clearGeneratedState();
          setState({ loading: false, loadingMessage: '', error: '', data: undefined });
          await refresh();
          return;
        }
        const pipelineId = state.data?.pipeline?.pipeline_id;
        if (!pipelineId || !currentWorkItemId) {
          return;
        }
        const latest = await loadPipelineForWorkItem(currentWorkItemId);
        if (latest && latest.version !== state.data?.pipeline?.version) {
          await refreshPipeline('Refreshing pipeline...');
        }
      } catch {
        // Keep last safe UI; manual refresh remains available.
      }
    };

    const startPolling = () => {
      if (timer) {
        window.clearInterval(timer);
      }
      if (document.visibilityState === 'visible') {
        timer = window.setInterval(() => void tick(), 20000);
      }
    };

    const handleVisibility = () => {
      startPolling();
      if (document.visibilityState === 'visible') {
        void tick();
      }
    };

    startPolling();
    document.addEventListener('visibilitychange', handleVisibility);
    return () => {
      disposed = true;
      if (timer) {
        window.clearInterval(timer);
      }
      document.removeEventListener('visibilitychange', handleVisibility);
    };
  }, [state.data?.pipeline?.version, state.data?.pipeline?.pipeline_id, state.data?.workItem?.id]);

  const workItem = state.data?.workItem;
  const response = state.data?.response;
  const capabilities = state.data?.capabilities;
  const pipeline = state.data?.pipeline;
  const currentStageName = useMemo(() => activeStageName(pipeline), [pipeline]);
  const currentStage = currentStageName && pipeline ? pipeline.stages[currentStageName] : undefined;
  const allowedActions = pipeline?.allowed_actions;
  const canGenerate = Boolean(currentStageName && allowedActions?.generate_stages?.includes(currentStageName));
  const canRegenerate = Boolean(currentStageName && allowedActions?.regenerate_stages?.includes(currentStageName));
  const canApprove = Boolean(currentStageName && allowedActions?.approve_stages?.includes(currentStageName));
  const canSkipUi = Boolean(allowedActions?.skip_stages?.includes('ui') && currentStageName === 'ui');
  const canViewHandoff = Boolean(currentStageName && allowedActions?.view_handoff_stages?.includes(currentStageName));
  const canAddFeedback = Boolean(currentStageName && allowedActions?.feedback_stages?.includes(currentStageName));
  const unresolvedFindings = Array.isArray(currentStage?.unresolved_findings) ? currentStage?.unresolved_findings as Array<Record<string, unknown>> : [];
  const blockingFindings = unresolvedFindings.filter((finding) => String(finding.severity || '') === 'blocking');
  const warningFindings = unresolvedFindings.filter((finding) => String(finding.severity || '') === 'warning');
  const suggestionFindings = unresolvedFindings.filter((finding) => String(finding.severity || '') === 'suggestion');

  async function refresh() {
    setState((current) => ({ ...current, loading: true, loadingMessage: 'Refreshing...', error: '' }));
    try {
      const data = await generateFromCurrentWorkItem();
      const refreshed = await refreshPipelineState(data.workItem, data);
      setState({ loading: false, loadingMessage: '', error: '', data: refreshed });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to generate ai-gen prompt';
      setState((current) => ({ ...current, loading: false, loadingMessage: '', error: message }));
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
    setState((current) => ({ ...current, loading: true, error: '', loadingMessage: current.loadingMessage || 'Updating pipeline...' }));
    try {
      const next = await action();
      saveGeneratedState(next);
      setState({ loading: false, loadingMessage: '', error: '', data: next });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Pipeline action failed';
      setState((current) => ({ ...current, loading: false, loadingMessage: '', error: message }));
    }
  }

  async function refreshPipeline(loadingMessage = 'Refreshing pipeline...') {
    const currentData = state.data;
    if (!currentData?.workItem) {
      await refresh();
      return;
    }
    setState((current) => ({ ...current, loading: true, loadingMessage, error: '' }));
    try {
      const refreshed = await refreshPipelineState(currentData.workItem, currentData);
      setState({ loading: false, loadingMessage: '', error: '', data: refreshed });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to refresh pipeline state.';
      setState((current) => ({ ...current, loading: false, loadingMessage: '', error: message, data: current.data }));
    }
  }

  async function createOrRefreshPipeline() {
    if (!state.data?.workItem || !state.data?.response) {
      return;
    }
    setState((current) => ({ ...current, loadingMessage: 'Creating pipeline...' }));
    await withPipelineUpdate(async () => {
      const pipeline = await createPipeline(state.data!.workItem, state.data!.response);
      return refreshPipelineState(
        state.data!.workItem,
        { ...state.data!, pipeline },
        pipeline
      );
    });
  }

  async function generateStage(regenerate = false) {
    if (!state.data?.pipeline || !currentStageName) {
      return;
    }
    setState((current) => ({ ...current, loadingMessage: regenerate ? 'Regenerating...' : 'Generating...' }));
    await withPipelineUpdate(async () => {
      const pipeline = await runPipelineStage(state.data!.pipeline!.pipeline_id, currentStageName, regenerate);
      return refreshPipelineState(
        state.data!.workItem,
        { ...state.data!, pipeline },
        pipeline
      );
    });
  }

  async function approveStage() {
    if (!state.data?.pipeline || !currentStageName) {
      return;
    }
    setState((current) => ({ ...current, loadingMessage: 'Approving...' }));
    await withPipelineUpdate(async () => {
      const pipeline = await approvePipelineStage(state.data!.pipeline!.pipeline_id, currentStageName);
      return refreshPipelineState(
        state.data!.workItem,
        { ...state.data!, pipeline },
        pipeline
      );
    });
  }

  async function skipUi() {
    if (!state.data?.pipeline) {
      return;
    }
    setState((current) => ({ ...current, loadingMessage: 'Skipping UI...' }));
    await withPipelineUpdate(async () => {
      const pipeline = await skipPipelineStage(state.data!.pipeline!.pipeline_id, 'ui', 'backend-only task');
      return refreshPipelineState(
        state.data!.workItem,
        { ...state.data!, pipeline },
        pipeline
      );
    });
  }

  async function addClarification(andRegenerate = false) {
    if (!state.data?.pipeline || !currentStageName || !clarification.trim()) {
      return;
    }
    setState((current) => ({ ...current, loadingMessage: andRegenerate ? 'Regenerating with clarifications...' : 'Saving clarification...' }));
    await withPipelineUpdate(async () => {
      const pipeline = await addStageFeedback(state.data!.pipeline!.pipeline_id, currentStageName, clarification.trim());
      setClarification('');
      if (andRegenerate) {
        const regenerated = await runPipelineStage(pipeline.pipeline_id, currentStageName, true);
        return refreshPipelineState(
          state.data!.workItem,
          { ...state.data!, pipeline: regenerated },
          regenerated
        );
      }
      return refreshPipelineState(
        state.data!.workItem,
        { ...state.data!, pipeline },
        pipeline
      );
    });
  }

  async function viewCurrentHandoff() {
    if (!state.data || !currentStage?.handoff_id) {
      return;
    }
    setState((current) => ({ ...current, loadingMessage: 'Refreshing handoff...' }));
    await withPipelineUpdate(async () => {
      const handoff = await loadHandoff(currentStage.handoff_id || '');
      return { ...state.data!, handoff: handoff || state.data!.handoff };
    });
  }

  const showRefinement = Boolean(
    response?.refinement_used
    || response?.refined_base_flows?.length
    || response?.refined_variants?.length
    || response?.refined_surfaces?.length
    || response?.refined_variant
    || response?.refined_surface
    || response?.refined_fields?.length
    || response?.refined_validations?.length
    || response?.refined_scope?.length
    || response?.refinement_unknowns?.length
  );
  const stageOwner = ownerRole(currentStageName);
  const blockingIssues = currentStage ? stageBlockingIssues(currentStage) : [];
  const nextAction = currentStageName ? stageNextAction(currentStageName, currentStage, {
    canGenerate,
    canRegenerate,
    canApprove,
    canSkipUi,
    canViewHandoff
  }) : 'Create a pipeline to start.';
  const currentSummary = currentStage ? stageSummary(currentStageName || '', currentStage) : 'No active stage yet.';

  return (
    <main className="ai-gen-page">
      <div className="ai-gen-header">
        <div>
          <h1 className="ai-gen-title">ai-gen</h1>
          <div className="ai-gen-muted">Convert this work item into an execution packet and a staged assistant pipeline.</div>
        </div>
        <button
          className="ai-gen-button secondary"
          onClick={() => void (state.data?.pipeline ? refreshPipeline() : refresh())}
          disabled={state.loading}
        >
          {state.loading && state.loadingMessage ? state.loadingMessage : 'Refresh'}
        </button>
      </div>

      {state.error && (
        <div className="ai-gen-error">Unable to generate ai-gen prompt: {state.error}</div>
      )}

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
                  <small>{chipLabel(stage, pipeline.stages[stage])}</small>
                </div>
              ))}
            </div>
            <div className="ai-gen-stage-summary">
              <div className="ai-gen-stage-summary-main">
                <div className="ai-gen-stage-title-row">
                  <h3>{formatStageName(currentStageName || 'ba')}</h3>
                  <span className={`ai-gen-badge ${currentStage?.status || 'unknown'}`}>{currentStage?.status || 'unknown'}</span>
                </div>
                <p className="ai-gen-summary-text">{currentSummary}</p>
                <div className="ai-gen-stage-meta">
                  <span><strong>Owner:</strong> {stageOwner}</span>
                  <span><strong>Approved:</strong> {currentStage?.approved ? 'Yes' : 'No'}</span>
                  <span><strong>Version:</strong> {pipeline.version}</span>
                </div>
              </div>
              <div className="ai-gen-stage-sidebar">
                <div className="ai-gen-card-label">Next action</div>
                <div>{nextAction}</div>
              </div>
            </div>
            {blockingIssues.length ? (
              <div className="ai-gen-warning">
                <div className="ai-gen-key">Blocking issues</div>
                <ul className="ai-gen-list">
                  {blockingIssues.map((issue) => <li key={issue}>{issue}</li>)}
                </ul>
              </div>
            ) : null}
            {currentStage?.status === 'needs_revision' ? (
              <div className="ai-gen-warning">
                <div className="ai-gen-key">Needs Revision</div>
                <div>AI identified ambiguities requiring clarification before approval.</div>
              </div>
            ) : null}
            <div className="ai-gen-actions ai-gen-actions-compact">
              {canGenerate ? (
                <button className="ai-gen-button" onClick={() => generateStage(false)} disabled={state.loading}>
                  Generate
                </button>
              ) : null}
              {canRegenerate ? (
                <button className="ai-gen-button secondary" onClick={() => generateStage(true)} disabled={state.loading}>
                  Regenerate
                </button>
              ) : null}
              {canApprove ? (
                <button className="ai-gen-button secondary" onClick={approveStage} disabled={state.loading}>
                  Approve &amp; Continue
                </button>
              ) : null}
              {canSkipUi ? (
                <button className="ai-gen-button secondary" onClick={skipUi} disabled={state.loading}>
                  Skip UI
                </button>
              ) : null}
              <button className="ai-gen-button secondary" onClick={() => refreshPipeline()} disabled={state.loading}>
                Reload Pipeline
              </button>
              {canViewHandoff ? (
                <button className="ai-gen-button secondary" onClick={viewCurrentHandoff} disabled={state.loading}>
                  View Handoff
                </button>
              ) : null}
              {currentStageName === 'dev' && currentStage?.output?.execution_packet ? (
                <button className="ai-gen-button secondary" onClick={copyPrompt} disabled={state.loading}>
                  Copy Packet
                </button>
              ) : null}
            </div>
            {currentStage ? (
              <FeedbackPanel
                blockingFindings={blockingFindings}
                warningFindings={warningFindings}
                suggestionFindings={suggestionFindings}
                reviewFeedback={currentStage.review_feedback || []}
                clarification={clarification}
                onClarificationChange={setClarification}
                onAddClarification={() => addClarification(false)}
                onRegenerateWithClarifications={() => addClarification(true)}
                canAddFeedback={canAddFeedback}
                canRegenerate={canRegenerate}
                loading={state.loading}
              />
            ) : null}
            {currentStage ? <StagePanel stage={currentStageName} stageState={currentStage} /> : null}
            <PipelineHandoff handoff={state.data?.handoff} />
          </>
        )}
      </section>

      <section className="ai-gen-section">
        <h2>Work Item</h2>
        <div className="ai-gen-grid">
          <span className="ai-gen-key">Title</span>
          <span>{workItem?.title || 'Not loaded'}</span>
          <span className="ai-gen-key">Type</span>
          <span>{workItem?.type || 'Unknown'}</span>
          <span className="ai-gen-key">Tags</span>
          <span>{workItem?.tags.join(', ') || 'None'}</span>
          <span className="ai-gen-key">Detected Flow</span>
          <span>{response?.detected_flow || 'Not detected'}</span>
        </div>
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
        <details className="ai-gen-section" open={false}>
          <summary>Refinement</summary>
          <div className="ai-gen-grid">
            <span className="ai-gen-key">Used</span>
            <span>{response?.refinement_used ? 'Yes' : 'No'}</span>
            <span className="ai-gen-key">Flows</span>
            <span>{response?.refined_base_flows?.join(', ') || response?.refined_base_flow || 'Not refined'}</span>
            <span className="ai-gen-key">Variants</span>
            <span>{response?.refined_variants?.join(', ') || response?.refined_variant || 'Not refined'}</span>
            <span className="ai-gen-key">Surfaces</span>
            <span>{response?.refined_surfaces?.join(', ') || response?.refined_surface || 'Not refined'}</span>
          </div>
          {response?.refined_fields?.length ? (
            <ListSection title="Fields" items={response.refined_fields} />
          ) : null}
          {response?.refined_validations?.length ? (
            <ListSection title="Validations" items={response.refined_validations} />
          ) : null}
          {response?.refinement_unknowns?.length ? (
            <WarningSection title="Open Questions" items={response.refinement_unknowns} />
          ) : null}
        </details>
      )}

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

function FeedbackPanel({
  blockingFindings,
  warningFindings,
  suggestionFindings,
  reviewFeedback,
  clarification,
  onClarificationChange,
  onAddClarification,
  onRegenerateWithClarifications,
  canAddFeedback,
  canRegenerate,
  loading,
}: {
  blockingFindings: Array<Record<string, unknown>>;
  warningFindings: Array<Record<string, unknown>>;
  suggestionFindings: Array<Record<string, unknown>>;
  reviewFeedback: Array<{ id: string; author: string; timestamp: string; comment: string }>;
  clarification: string;
  onClarificationChange: (value: string) => void;
  onAddClarification: () => void;
  onRegenerateWithClarifications: () => void;
  canAddFeedback: boolean;
  canRegenerate: boolean;
  loading: boolean;
}) {
  return (
    <div className="ai-gen-stage-panel">
      {blockingFindings.length ? <FindingSection title="Blocking Issues" items={blockingFindings} /> : null}
      {warningFindings.length ? <FindingSection title="Warnings" items={warningFindings} /> : null}
      {suggestionFindings.length ? <FindingSection title="Suggestions" items={suggestionFindings} /> : null}
      <details open className="ai-gen-detail-block">
        <summary>Reviewer Clarifications</summary>
        <textarea
          className="ai-gen-textarea"
          value={clarification}
          onChange={(event) => onClarificationChange(event.target.value)}
          placeholder="Answer critic questions or add reviewer guidance for this stage."
        />
        <div className="ai-gen-actions ai-gen-actions-compact">
          <button className="ai-gen-button secondary" onClick={onAddClarification} disabled={loading || !canAddFeedback || !clarification.trim()}>
            Add Clarification
          </button>
          <button className="ai-gen-button" onClick={onRegenerateWithClarifications} disabled={loading || !canRegenerate || !clarification.trim()}>
            Regenerate with Clarifications
          </button>
        </div>
        {reviewFeedback.length ? (
          <ul className="ai-gen-list">
            {reviewFeedback.slice(-4).reverse().map((item) => (
              <li key={item.id}>
                <strong>{item.author}</strong>: {item.comment}
              </li>
            ))}
          </ul>
        ) : (
          <div className="ai-gen-muted">No reviewer clarifications yet.</div>
        )}
      </details>
    </div>
  );
}

function FindingSection({ title, items }: { title: string; items: Array<Record<string, unknown>> }) {
  return (
    <div className="ai-gen-warning">
      <div className="ai-gen-key">{title}</div>
      <ul className="ai-gen-list">
        {items.map((item) => (
          <li key={String(item.id || item.message || Math.random())}>{String(item.message || 'Review needed')}</li>
        ))}
      </ul>
    </div>
  );
}

async function getSafeCurrentWorkItemId(): Promise<string | undefined> {
  try {
    const workItem = await getCurrentWorkItem();
    return String(workItem.id || '');
  } catch {
    return undefined;
  }
}

function StagePanel({ stage, stageState }: { stage: string; stageState: PipelineStageState }) {
  const criticFindings = Array.isArray(stageState.critic?.findings) ? stageState.critic?.findings as Array<Record<string, unknown>> : [];
  return (
    <div className="ai-gen-stage-panel">
      {criticFindings.length ? (
        <div className="ai-gen-critic-card">
          <div className="ai-gen-critic-header">
            <strong>Critic review</strong>
            <span className={`ai-gen-badge ${String(stageState.critic?.overall_risk || 'medium')}`}>{String(stageState.critic?.overall_risk || 'medium')}</span>
          </div>
          <ul className="ai-gen-list">
            {criticFindings.slice(0, 3).map((finding, index) => (
              <li key={`${stage}-${index}`}>{String(finding.message || finding.type || 'Review needed')}</li>
            ))}
          </ul>
        </div>
      ) : null}
      <details open className="ai-gen-detail-block">
        <summary>Stage summary</summary>
        <div className="ai-gen-summary-card">
          <div className="ai-gen-grid">
            <span className="ai-gen-key">Stage</span>
            <span>{formatStageName(stage)}</span>
            <span className="ai-gen-key">Status</span>
            <span>{stageState.status}</span>
            <span className="ai-gen-key">Owner role</span>
            <span>{ownerRole(stage)}</span>
            <span className="ai-gen-key">Summary</span>
            <span>{stageSummary(stage, stageState)}</span>
          </div>
        </div>
      </details>
      <details className="ai-gen-detail-block">
        <summary>View Details</summary>
        {Object.keys(stageState.output || {}).length ? (
          <pre className="ai-gen-prompt">{JSON.stringify(stageState.output, null, 2)}</pre>
        ) : (
          <div className="ai-gen-muted">No stage output yet.</div>
        )}
      </details>
    </div>
  );
}

function PipelineHandoff({ handoff }: { handoff?: HandoffRecord }) {
  const canOpenInVsCode = Boolean(handoff?.handoff_id && handoff?.stage === 'dev' && handoff?.status === 'approved');

  const downloadHandoff = () => {
    if (!handoff) {
      return;
    }
    const blob = new Blob([JSON.stringify(handoff, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `${handoff.stage || 'handoff'}-${handoff.handoff_id || 'artifact'}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const copyHandoff = async () => {
    if (!handoff) {
      return;
    }
    await navigator.clipboard.writeText(JSON.stringify(handoff, null, 2));
  };

  const copyHandoffMarkdown = async () => {
    if (!handoff) {
      return;
    }
    const markdown = await loadHandoffMarkdown(handoff.handoff_id);
    await navigator.clipboard.writeText(markdown || JSON.stringify(handoff, null, 2));
  };

  const copyHandoffId = async () => {
    if (!handoff?.handoff_id) {
      return;
    }
    await navigator.clipboard.writeText(handoff.handoff_id);
  };

  const copyExecutionPacket = async () => {
    if (!handoff) {
      return;
    }
    const packet = handoff.execution_packet || String(handoff.content?.execution_packet || '');
    if (packet) {
      await navigator.clipboard.writeText(packet);
    }
  };

  const openInVsCode = () => {
    if (!handoff?.handoff_id) {
      return;
    }
    window.location.href = buildVsCodeHandoffLink(handoff.handoff_id);
  };

  return (
    <div className="ai-gen-handoff-card">
      <div className="ai-gen-handoff-header">
        <div>
          <div className="ai-gen-key">Handoff</div>
          <div>{handoff?.summary || 'Dev handoff not approved yet'}</div>
          <div className="ai-gen-muted">
            {handoff
              ? `${formatStageName(handoff.stage)} v${handoff.version} ${handoff.approved_at ? `approved ${handoff.approved_at}` : ''}`
              : 'Approve the Dev stage to open it directly in VS Code.'}
          </div>
        </div>
        <span className={`ai-gen-badge ${handoff?.status || 'draft'}`}>{handoff?.status || 'draft'}</span>
      </div>
      <div className="ai-gen-actions ai-gen-actions-compact">
        <button className="ai-gen-button secondary" onClick={openInVsCode} disabled={!canOpenInVsCode}>Open in VS Code</button>
        <button className="ai-gen-button secondary" onClick={copyHandoffId} disabled={!handoff?.handoff_id}>Copy Handoff ID</button>
        <button className="ai-gen-button secondary" onClick={copyExecutionPacket} disabled={!handoff?.execution_packet && !handoff?.content?.execution_packet}>Copy Execution Packet</button>
        <button className="ai-gen-button secondary" onClick={copyHandoff} disabled={!handoff}>Copy JSON</button>
        <button className="ai-gen-button secondary" onClick={copyHandoffMarkdown} disabled={!handoff}>Copy Markdown</button>
        <button className="ai-gen-button secondary" onClick={downloadHandoff} disabled={!handoff}>Download</button>
      </div>
      {!canOpenInVsCode ? <div className="ai-gen-muted">Dev handoff not approved yet.</div> : null}
      {handoff?.constraints?.length ? <ListSection title="Constraints" items={handoff.constraints} /> : null}
      {handoff?.open_questions?.length ? <WarningSection title="Open Questions" items={handoff.open_questions} /> : null}
      {handoff?.next_actions?.length ? <ListSection title="Next Actions" items={handoff.next_actions} /> : null}
      {handoff ? (
        <details className="ai-gen-detail-block">
          <summary>View</summary>
          <pre className="ai-gen-prompt">{JSON.stringify(handoff.content || {}, null, 2)}</pre>
        </details>
      ) : null}
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

function formatStageName(stage: string): string {
  return stage === 'dev' ? 'DEV' : stage.toUpperCase();
}

function ownerRole(stage?: string): string {
  switch (stage) {
    case 'ba':
      return 'Business Analyst';
    case 'ui':
      return 'App UI';
    case 'dev':
      return 'Developer';
    case 'test':
      return 'QA';
    case 'critic':
      return 'Reviewer';
    default:
      return 'Team';
  }
}

function stageSummary(stage: string, stageState: PipelineStageState): string {
  const output = stageState.output || {};
  switch (stage) {
    case 'ba':
      return String(output.refined_requirement || 'Clarify the requirement and acceptance criteria.');
    case 'ui':
      return String(output.user_goal || output.screen_name || 'Define the user-facing screen and states.');
    case 'dev':
      return String(output.task_summary || 'Prepare the execution packet and scope.');
    case 'test':
      return `${Array.isArray(output.test_cases) ? output.test_cases.length : 0} test cases prepared.`;
    case 'critic':
      return `${Array.isArray(output.findings) ? output.findings.length : 0} review findings.`;
    default:
      return 'Stage output is ready for review.';
  }
}

function stageBlockingIssues(stageState: PipelineStageState): string[] {
  const criticFindings = Array.isArray(stageState.unresolved_findings) ? stageState.unresolved_findings : [];
  const criticIssues = criticFindings
    .filter((finding) => String((finding as Record<string, unknown>).severity || '') === 'blocking')
    .map((finding) => String((finding as Record<string, unknown>).message || 'Review needed'))
    .filter(Boolean);
  const outputUnknowns = Array.isArray(stageState.output?.unknowns) ? stageState.output.unknowns.map((item) => String(item)) : [];
  return [...criticIssues, ...outputUnknowns].slice(0, 4);
}

function stageNextAction(
  stage: string,
  stageState: PipelineStageState | undefined,
  flags: { canGenerate: boolean; canRegenerate: boolean; canApprove: boolean; canSkipUi: boolean; canViewHandoff: boolean }
): string {
  if (!stageState) {
    return 'Create the pipeline to start this stage.';
  }
  if (flags.canGenerate) {
    return `Generate ${formatStageName(stage)} output.`;
  }
  if (stageState.status === 'needs_revision') {
    return 'Add clarification or regenerate with reviewer context.';
  }
  if (flags.canApprove) {
    return `Approve ${formatStageName(stage)} and continue.`;
  }
  if (flags.canSkipUi) {
    return 'Skip UI because this task is backend-only.';
  }
  if (flags.canViewHandoff) {
    return 'Review the handoff and share it with the next role.';
  }
  if (flags.canRegenerate) {
    return `Regenerate ${formatStageName(stage)} if the summary needs revision.`;
  }
  return 'Refresh to load the latest pipeline state.';
}

function chipLabel(stage: string, stageState?: PipelineStageState): string {
  if (!stageState) {
    return 'locked';
  }
  if (stageState.approved) {
    return `${ownerRole(stage)} approved`;
  }
  return stageState.status;
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
