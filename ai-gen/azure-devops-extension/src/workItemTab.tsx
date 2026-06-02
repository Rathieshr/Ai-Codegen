import * as SDK from 'azure-devops-extension-sdk';
import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  addAiGenComment,
  clearGeneratedState,
  approveDraftWorkItems,
  AiGenState,
  approvePipelineStage,
  addStageFeedback,
  buildVsCodeHandoffLink,
  createPipeline,
  createAzureDevOpsWorkItems,
  DraftWorkItem,
  getCurrentWorkItem,
  generateFromCurrentWorkItem,
  HandoffRecord,
  loadDraftWorkItemCreatePayload,
  loadAiGenComments,
  loadGeneratedState,
  loadHandoff,
  loadHandoffMarkdown,
  loadPipelineForWorkItem,
  PipelineState,
  PipelineStageState,
  refreshPipelineState,
  runEpicPlan,
  saveGeneratedState,
  skipPipelineStage,
  storeWorkItemCreationResult,
  runPipelineStage
} from './api';
import { selectWorkspaceRenderer } from './renderers/workspaceRenderer';
import './styles.css';

type ViewState = {
  loading: boolean;
  loadingMessage: string;
  error: string;
  data?: AiGenState;
};

function WorkItemTab() {
  const [state, setState] = useState<ViewState>({
    loading: false,
    loadingMessage: '',
    error: '',
    data: loadGeneratedState()
  });
  const [clarification, setClarification] = useState('');
  const [selectedChildTaskTitles, setSelectedChildTaskTitles] = useState<string[]>([]);
  const [createdTaskPreview, setCreatedTaskPreview] = useState<Array<Record<string, unknown>>>([]);
  const [selectedDraftIds, setSelectedDraftIds] = useState<string[]>([]);
  const [createdDraftsPreview, setCreatedDraftsPreview] = useState<Array<{ draft_id: string; azure_work_item_id: number | null; title: string; type: string; status: 'created' | 'failed' | 'skipped'; creation_error?: string | null }>>([]);
  const [pendingCommentSync, setPendingCommentSync] = useState<{ kind: 'Clarification' | 'Approval' | 'Handoff' | 'Revision'; lines: string[] } | undefined>(undefined);

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
  const stageOrder = useMemo(() => pipelineStageOrder(pipeline), [pipeline]);
  const currentStageName = useMemo(() => activeStageName(pipeline), [pipeline]);
  const currentStage = currentStageName && pipeline ? pipeline.stages[currentStageName] : undefined;
  const workflowState = String(pipeline?.workflow_state || 'not_generated');
  const currentStageActions = pipeline?.allowed_actions?.current_stage_actions || [];
  const workflowActions = pipeline?.allowed_actions?.workflow_actions || [];
  const canAddFeedback = currentStageActions.includes('add_clarification');
  const canRegenerateWithClarifications = currentStageActions.includes('regenerate_with_clarifications');
  const currentStageFindings = Array.isArray(pipeline?.current_stage_findings) ? pipeline?.current_stage_findings as Array<Record<string, unknown>> : [];
  const blockingFindings = Array.isArray(pipeline?.current_stage_blocking_findings)
    ? pipeline?.current_stage_blocking_findings as Array<Record<string, unknown>>
    : currentStageFindings.filter((finding) => String(finding.severity || '') === 'blocking');
  const warningFindings = currentStageFindings.filter((finding) => String(finding.severity || '') === 'warning');
  const suggestionFindings = currentStageFindings.filter((finding) => String(finding.severity || '') === 'suggestion');
  const proposedChildTasks = Array.isArray(currentStage?.output?.proposed_child_tasks)
    ? currentStage.output.proposed_child_tasks as Array<Record<string, unknown>>
    : [];
  const draftWorkItems = state.data?.draftWorkItems || pipeline?.draft_work_items || [];
  const currentStageDrafts = draftWorkItems.filter((draft) => draft.source_stage === currentStageName);
  const isPlanningTemplate = ['epic_planning', 'feature_planning'].includes(String(pipeline?.workflow_template || ''));
  const isStoryTaskPlanning = String(pipeline?.workflow_template || '') === 'story_delivery' && currentStageName === 'task_planning';
  const workspaceRenderer = useMemo(
    () => selectWorkspaceRenderer(pipeline?.workflow_template || pipeline?.work_item_classification?.recommended_template),
    [pipeline?.workflow_template, pipeline?.work_item_classification?.recommended_template]
  );

  useEffect(() => {
    setSelectedChildTaskTitles([]);
    setCreatedTaskPreview([]);
    setSelectedDraftIds([]);
    setCreatedDraftsPreview([]);
  }, [state.data?.pipeline?.pipeline_id, currentStageName]);

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
    await copyText(prompt);
  }

  async function copyExecutionPacket() {
    const packet = String(currentStage?.output?.execution_packet || '');
    if (!packet) {
      return;
    }
    await copyText(packet);
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
      const commentLoad = await loadAiGenComments(state.data!.workItem.id);
      let pipeline = await createPipeline(state.data!.workItem, state.data!.response, commentLoad.comments);
      if (String(pipeline.workflow_template || '') === 'epic_planning') {
        setState((current) => ({ ...current, loadingMessage: 'Generating Epic Plan...' }));
        pipeline = await runEpicPlan(pipeline.pipeline_id, commentLoad.comments);
      }
      return refreshPipelineState(
        state.data!.workItem,
        { ...state.data!, pipeline, commentWarning: commentLoad.warning },
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
      const commentLoad = await loadAiGenComments(state.data!.workItem.id);
      const pipeline = String(state.data!.pipeline!.workflow_template || '') === 'epic_planning' && !regenerate
        ? await runEpicPlan(state.data!.pipeline!.pipeline_id, commentLoad.comments)
        : await runPipelineStage(
          state.data!.pipeline!.pipeline_id,
          currentStageName,
          regenerate,
          undefined,
          'azure_devops',
          commentLoad.comments,
        );
      return refreshPipelineState(
        state.data!.workItem,
        { ...state.data!, pipeline, commentWarning: commentLoad.warning },
        pipeline
      );
    });
  }

  async function syncComment(kind: 'Clarification' | 'Approval' | 'Handoff' | 'Revision', lines: string[]) {
    await addAiGenComment(state.data!.workItem.id, kind, lines);
    setPendingCommentSync(undefined);
    setState((current) => current.data
      ? { ...current, data: { ...current.data, commentSyncWarning: undefined } }
      : current);
  }

  async function retryCommentSync() {
    if (!pendingCommentSync || !state.data) {
      return;
    }
    setState((current) => ({ ...current, loading: true, loadingMessage: 'Retrying comment sync...' }));
    try {
      await syncComment(pendingCommentSync.kind, pendingCommentSync.lines);
      const refreshed = await refreshPipelineState(state.data.workItem, state.data);
      setState({ loading: false, loadingMessage: '', error: '', data: refreshed });
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to sync Azure DevOps comment.';
      setState((current) => current.data
        ? { ...current, loading: false, loadingMessage: '', data: { ...current.data, commentSyncWarning: message } }
        : current);
    }
  }

  async function approveStage() {
    if (!state.data?.pipeline || !currentStageName) {
      return;
    }
    setState((current) => ({ ...current, loadingMessage: 'Approving...' }));
    await withPipelineUpdate(async () => {
      const pipeline = await approvePipelineStage(state.data!.pipeline!.pipeline_id, currentStageName);
      const approvalLines = [
        `Stage: ${stageLabel(currentStageName, pipeline)}`,
        `Approved by ai-gen at pipeline version ${pipeline.version}.`,
      ];
      try {
        await syncComment('Approval', approvalLines);
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Unable to sync Azure DevOps comment.';
        setPendingCommentSync({ kind: 'Approval', lines: approvalLines });
        setState((current) => current.data
          ? { ...current, data: { ...current.data, commentSyncWarning: message } }
          : current);
      }
      if (pipeline.stages[currentStageName]?.handoff_id) {
        const handoffLines = [
          `Stage: ${stageLabel(currentStageName, pipeline)}`,
          `Handoff: ${pipeline.stages[currentStageName]?.handoff_id}`,
        ];
        try {
          await syncComment('Handoff', handoffLines);
        } catch (error) {
          const message = error instanceof Error ? error.message : 'Unable to sync Azure DevOps comment.';
          setPendingCommentSync({ kind: 'Handoff', lines: handoffLines });
          setState((current) => current.data
            ? { ...current, data: { ...current.data, commentSyncWarning: message } }
            : current);
        }
      }
      return refreshPipelineState(
        state.data!.workItem,
        { ...state.data!, pipeline },
        pipeline
      );
    });
  }

  async function skipCurrentStage() {
    if (!state.data?.pipeline || !currentStageName) {
      return;
    }
    setState((current) => ({ ...current, loadingMessage: 'Skipping stage...' }));
    await withPipelineUpdate(async () => {
      const pipeline = await skipPipelineStage(
        state.data!.pipeline!.pipeline_id,
        currentStageName,
        currentStageName.includes('ui') ? 'UI stage is not needed for this work item.' : 'Optional stage skipped.'
      );
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
    const comment = clarification.trim();
    setState((current) => ({ ...current, loadingMessage: andRegenerate ? 'Regenerating with clarifications...' : 'Saving clarification...' }));
    await withPipelineUpdate(async () => {
      if (andRegenerate) {
        const commentLoad = await loadAiGenComments(state.data!.workItem.id);
        const regenerated = await runPipelineStage(
          state.data!.pipeline!.pipeline_id,
          currentStageName,
          true,
          comment,
          'azure_devops',
          commentLoad.comments,
        );
        const revisionLines = [
          `Stage: ${stageLabel(currentStageName, regenerated)}`,
          comment,
        ];
        try {
          await syncComment('Revision', revisionLines);
        } catch (error) {
          const message = error instanceof Error ? error.message : 'Unable to sync Azure DevOps comment.';
          setPendingCommentSync({ kind: 'Revision', lines: revisionLines });
          setState((current) => current.data
            ? { ...current, data: { ...current.data, commentSyncWarning: message } }
            : current);
        }
        setClarification('');
        return refreshPipelineState(
          state.data!.workItem,
          { ...state.data!, pipeline: regenerated, commentWarning: commentLoad.warning },
          regenerated
        );
      }
      const pipeline = await addStageFeedback(state.data!.pipeline!.pipeline_id, currentStageName, comment);
      const clarificationLines = [
        `Stage: ${stageLabel(currentStageName, pipeline)}`,
        comment,
      ];
      try {
        await syncComment('Clarification', clarificationLines);
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Unable to sync Azure DevOps comment.';
        setPendingCommentSync({ kind: 'Clarification', lines: clarificationLines });
        setState((current) => current.data
          ? { ...current, data: { ...current.data, commentSyncWarning: message } }
          : current);
      }
      setClarification('');
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

  async function createSelectedTasksPreview() {
    if (!proposedChildTasks.length) {
      return;
    }
    const selected = proposedChildTasks.filter((task) => {
      const title = String(task.title || '').trim();
      return title && selectedChildTaskTitles.includes(title);
    });
    setCreatedTaskPreview(selected);
    if (selected.length) {
      await copyText(JSON.stringify(selected, null, 2));
    }
  }

  async function approveSelectedDraftsAction() {
    if (!state.data?.pipeline || !selectedDraftIds.length) {
      return;
    }
    setState((current) => ({ ...current, loadingMessage: 'Approving drafts...' }));
    await withPipelineUpdate(async () => {
      await approveDraftWorkItems(state.data!.pipeline!.pipeline_id, selectedDraftIds);
      return refreshPipelineState(state.data!.workItem, state.data!);
    });
  }

  async function createSelectedDraftWorkItemsAction() {
    if (!state.data?.pipeline || !selectedDraftIds.length) {
      return;
    }
    const count = selectedDraftIds.length;
    const confirmed = window.confirm(`This will create ${count} Azure DevOps work items under ${state.data.workItem.type} #${state.data.workItem.id}. Continue?`);
    if (!confirmed) {
      return;
    }
    setState((current) => ({ ...current, loadingMessage: 'Creating Azure DevOps work items...' }));
    await withPipelineUpdate(async () => {
      const payload = await loadDraftWorkItemCreatePayload(state.data!.pipeline!.pipeline_id, selectedDraftIds, true);
      const created = await createAzureDevOpsWorkItems(state.data!.workItem, payload.work_item_create_requests);
      await storeWorkItemCreationResult(
        state.data!.pipeline!.pipeline_id,
        created.map((item) => ({
          draft_id: item.draft_id,
          type: item.type,
          title: item.title,
          azure_work_item_id: item.azure_work_item_id,
          parent_azure_work_item_id: item.parent_azure_work_item_id,
          status: item.status,
          creation_error: item.creation_error || null,
        }))
      );
      setCreatedDraftsPreview(created);
      return refreshPipelineState(state.data!.workItem, state.data!);
    });
  }

  const showRefinement = Boolean(
    response?.semantic_mapping_applied
    || response?.refinement_used
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
  const stageOwner = ownerRole(currentStageName, pipeline);
  const blockingIssues = blockingFindings
    .map((finding) => String(finding.message || 'Review needed'))
    .filter(Boolean)
    .slice(0, 4);
  const nextAction = stageNextAction(workflowActions, pipeline);
  const currentSummary = pipeline ? workflowSummary(pipeline, currentStageName || '', currentStage) : 'No active stage yet.';
  const recommendation = workflowRecommendation(workItem?.type || '', response);
  const timelineItems = buildTimeline(pipeline);
  const contextWarnings = [...(pipeline?.context_warnings || []), ...(pipeline?.pipeline_context?.warnings || [])];
  const workflowConfidence = String(pipeline?.work_item_classification?.confidence || inferWorkflowConfidence(workItem?.type || ''));
  const showPromptActions = ['task_execution', 'bug_fix', 'story_delivery', 'ui_task', 'qa_task', 'spike'].includes(String(pipeline?.workflow_template || ''));

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
        <div className="ai-gen-grid">
          <span className="ai-gen-key">Connected</span>
          <span>{capabilities?.backend_up ? 'Yes' : 'Unknown'}</span>
          <span className="ai-gen-key">Last Sync</span>
          <span>{state.data?.lastSyncAt || state.data?.generatedAt || 'Not synced yet'}</span>
          <span className="ai-gen-key">Pipeline Version</span>
          <span>{pipeline?.version || 'Not created'}</span>
          <span className="ai-gen-key">Refresh</span>
          <span>{state.loading ? `${state.loadingMessage || 'Refreshing...'}` : 'Ready'}</span>
        </div>
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
          <span className="ai-gen-key">Workflow Template</span>
          <span>{formatTemplateName(String(pipeline?.workflow_template || recommendation.workflowLabel || ''))}</span>
          <span className="ai-gen-key">Confidence</span>
          <span>{workflowConfidence}</span>
        </div>
      </section>

      <section className="ai-gen-section">
        <h2>AI Pipeline</h2>
        {!pipeline ? (
            <div className="ai-gen-stage-panel">
              <h3>AI Recommendation</h3>
              <div className="ai-gen-grid">
                <span className="ai-gen-key">Work Item Title</span>
                <span>{workItem?.title || 'Not loaded'}</span>
                <span className="ai-gen-key">Detected Type</span>
                <span>{recommendation.detectedType}</span>
                <span className="ai-gen-key">Recommended Workflow</span>
                <span>{recommendation.workflowLabel}</span>
                <span className="ai-gen-key">Confidence</span>
                <span>{workflowConfidence}</span>
                <span className="ai-gen-key">Expected Outputs</span>
                <span>{recommendation.outputs.join(', ')}</span>
                <span className="ai-gen-key">Estimated Time</span>
                <span>30 seconds</span>
              </div>
              {state.data?.commentWarning ? <div className="ai-gen-warning">{state.data.commentWarning}</div> : null}
              <div className="ai-gen-actions">
                <button className="ai-gen-button" onClick={createOrRefreshPipeline} disabled={state.loading || !response?.optimized_prompt}>
                  {recommendation.actionLabel}
              </button>
            </div>
          </div>
        ) : (
          <>
            <div className="ai-gen-grid">
              <span className="ai-gen-key">Workflow Template</span>
              <span>{formatTemplateName(pipeline.workflow_template || pipeline.work_item_classification?.recommended_template || 'legacy_delivery')}</span>
              <span className="ai-gen-key">Artifact Type</span>
              <span>{pipeline.work_item_classification?.artifact_type || 'generic'}</span>
              <span className="ai-gen-key">Confidence</span>
              <span>{workflowConfidence}</span>
              <span className="ai-gen-key">Why this template</span>
              <span>{pipeline.work_item_classification?.reason || 'Selected from work item type and refinement context.'}</span>
            </div>
            <div className="ai-gen-stage-bar">
              {stageOrder.map((stage) => (
                <div
                  key={stage}
                  className={`ai-gen-stage-chip ${pipeline.stages[stage]?.status || 'locked'} ${currentStageName === stage ? 'active' : ''}`}
                >
                  <span>{stageLabel(stage, pipeline)}</span>
                  <small>{chipLabel(stage, pipeline.stages[stage], pipeline)}</small>
                </div>
              ))}
            </div>
            {workspaceRenderer({
              pipeline,
              currentStageName,
              currentStage,
              currentSummary,
              nextAction,
              stageOwner,
              workflowState,
              timelineItems,
              blockingIssues,
              commentWarning: state.data?.commentWarning,
              commentSyncWarning: state.data?.commentSyncWarning,
              contextWarnings,
              loading: state.loading,
              retryCommentSync: pendingCommentSync ? () => void retryCommentSync() : undefined,
              actionBar: (
                <WorkflowActionBar
                  workflowActions={workflowActions}
                  workflowTemplate={String(pipeline.workflow_template || '')}
                  loading={state.loading}
                  onGenerate={() => generateStage(false)}
                  onRegenerate={() => generateStage(true)}
                  onApprove={() => approveStage()}
                  onSkip={() => skipCurrentStage()}
                  onRefresh={() => refreshPipeline()}
                  onViewHandoff={() => viewCurrentHandoff()}
                  onCopyPacket={() => copyExecutionPacket()}
                  onSelectAll={() => setSelectedDraftIds(flattenDrafts(currentStageDrafts).map((item) => item.draft_id))}
                  onDeselectAll={() => setSelectedDraftIds([])}
                  onCreateSelected={() => createSelectedDraftWorkItemsAction()}
                />
              ),
              feedbackPanel: currentStage && (blockingFindings.length || warningFindings.length || suggestionFindings.length || canAddFeedback || canRegenerateWithClarifications || (currentStage.review_feedback || []).length) ? (
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
                  canRegenerate={canRegenerateWithClarifications}
                  loading={state.loading}
                  stageState={currentStage}
                />
              ) : null,
              stagePanel: currentStage ? (
                <StagePanel
                  stage={currentStageName}
                  stageState={currentStage}
                  currentStageFindings={currentStageFindings}
                  allFindings={pipeline?.all_findings || []}
                  pipeline={pipeline}
                />
              ) : null,
              draftPanel: ((isPlanningTemplate || isStoryTaskPlanning) && currentStageDrafts.length > 0) ? (
                <DraftWorkItemsPanel
                  workflowTemplate={String(pipeline.workflow_template || '')}
                  drafts={currentStageDrafts}
                  selectedDraftIds={selectedDraftIds}
                  onToggleDraft={(draftId) => setSelectedDraftIds((current) => current.includes(draftId) ? current.filter((item) => item !== draftId) : [...current, draftId])}
                  onSelectAll={() => setSelectedDraftIds(flattenDrafts(currentStageDrafts).map((item) => item.draft_id))}
                  onDeselectAll={() => setSelectedDraftIds([])}
                  onApproveDrafts={() => void approveSelectedDraftsAction()}
                  onCreateSelected={() => void createSelectedDraftWorkItemsAction()}
                  onRetryFailed={() => setSelectedDraftIds(flattenDrafts(currentStageDrafts).filter((item) => item.status === 'failed').map((item) => item.draft_id))}
                  createdPreview={createdDraftsPreview}
                  loading={state.loading}
                />
              ) : null,
              createdWorkItemsPanel: pipeline?.created_work_items?.length ? (
                <CreatedWorkItemsPanel items={pipeline.created_work_items} />
              ) : null,
              childTaskPanel: proposedChildTasks.length ? (
                <ChildTaskPlannerCard
                  tasks={proposedChildTasks}
                  selectedTitles={selectedChildTaskTitles}
                  onToggle={(title) => setSelectedChildTaskTitles((current) => current.includes(title) ? current.filter((item) => item !== title) : [...current, title])}
                  onCreateSelected={() => void createSelectedTasksPreview()}
                  createdPreview={createdTaskPreview}
                  loading={state.loading}
                />
              ) : null,
              handoffPanel: <PipelineHandoff handoff={state.data?.handoff} workflowTemplate={String(pipeline.workflow_template || '')} />,
            })}
          </>
        )}
      </section>

      <section className="ai-gen-section">
        <details>
          <summary>Developer Diagnostics</summary>
          {response?.phi_status === 'unusable_response' ? (
            <div className="ai-gen-warning">
              <div>Phi configured but returned unusable structured output. Fallback was used.</div>
              {response?.phi_raw_response_preview ? (
                <details className="ai-gen-detail-block">
                  <summary>Raw Phi Preview</summary>
                  <pre className="ai-gen-prompt">{String(response.phi_raw_response_preview)}</pre>
                </details>
              ) : (
                <div className="ai-gen-subtle">No raw Phi preview was captured for this response.</div>
              )}
            </div>
          ) : null}
          <div className="ai-gen-grid">
            <span className="ai-gen-key">Backend</span>
            <span>{capabilities?.backend_up ? 'Connected' : 'Unknown'}</span>
            <span className="ai-gen-key">Refiner</span>
            <span>{capabilities?.refiner?.enabled ? 'Enabled' : 'Disabled'}</span>
            <span className="ai-gen-key">Provider</span>
            <span>{capabilities?.refiner?.provider || 'Not configured'}</span>
            <span className="ai-gen-key">Model</span>
            <span>{capabilities?.refiner?.model || 'Not configured'}</span>
            <span className="ai-gen-key">Deployment</span>
            <span>{capabilities?.refinerHealth?.deployment || capabilities?.refiner?.deployment || 'Not configured'}</span>
            <span className="ai-gen-key">Configured</span>
            <span>{capabilities?.refiner?.configured ? 'Yes' : 'No'}</span>
            <span className="ai-gen-key">Health</span>
            <span>{capabilities?.refinerHealth?.health || 'unknown'}</span>
            <span className="ai-gen-key">Last Success</span>
            <span>{capabilities?.refinerHealth?.last_success || 'Never'}</span>
            <span className="ai-gen-key">Last Failure</span>
            <span>{capabilities?.refinerHealth?.last_failure || 'None'}</span>
            <span className="ai-gen-key">Latency</span>
            <span>{typeof capabilities?.refinerHealth?.average_latency_ms === 'number' ? `${capabilities.refinerHealth.average_latency_ms} ms` : 'unknown'}</span>
            <span className="ai-gen-key">Comment Sync</span>
            <span>{state.data?.commentSyncWarning ? 'Needs Retry' : 'Ready'}</span>
            <span className="ai-gen-key">Pipeline Metadata</span>
            <span>{pipeline ? `${pipeline.workflow_template || 'workflow'} v${pipeline.version}` : 'Not created'}</span>
          </div>
        </details>
      </section>

      {showRefinement && (
        <details className="ai-gen-section" open={false}>
          <summary>Refinement</summary>
          <div className="ai-gen-grid">
            <span className="ai-gen-key">Semantic Refinement</span>
            <span>{response?.semantic_mapping_applied ? 'Applied' : 'Not Applied'}</span>
            <span className="ai-gen-key">Source</span>
            <span>{response?.refinement_source || 'none'}</span>
            <span className="ai-gen-key">Phi</span>
            <span>{response?.phi_status || (response?.phi_used ? 'used' : 'skipped')}</span>
            <span className="ai-gen-key">Confidence</span>
            <span>{response?.refinement_confidence || 'unknown'}</span>
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

      {showPromptActions ? (
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
            Use this packet with your preferred executor: Codex, Gemini, Copilot, Claude, Cursor, or manual implementation.
          </p>
        </section>
      ) : null}
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
  stageState,
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
  stageState: PipelineStageState;
}) {
  const guidedPrompts = clarificationPrompts(stageState);
  return (
    <div className="ai-gen-stage-panel">
      {blockingFindings.length ? <FindingSection title="Blocking Issues" items={blockingFindings} /> : null}
      {warningFindings.length ? <FindingSection title="Warnings" items={warningFindings} /> : null}
      {suggestionFindings.length ? <FindingSection title="Suggestions" items={suggestionFindings} /> : null}
      <details open className="ai-gen-detail-block">
        <summary>Clarification required before approval</summary>
        {guidedPrompts.length ? (
          <>
            <div className="ai-gen-key">Guided prompts</div>
            <ul className="ai-gen-list">
              {guidedPrompts.map((prompt) => <li key={prompt}>{prompt}</li>)}
            </ul>
          </>
        ) : null}
        <textarea
          className="ai-gen-textarea"
          value={clarification}
          onChange={(event) => onClarificationChange(event.target.value)}
          placeholder="Example: OTP expires in 2 minutes. Max retry attempts: 3. Resend cooldown: 30 seconds."
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

function StagePanel({
  stage,
  stageState,
  currentStageFindings,
  allFindings,
  pipeline,
}: {
  stage: string;
  stageState: PipelineStageState;
  currentStageFindings: Array<Record<string, unknown>>;
  allFindings: Array<Record<string, unknown>>;
  pipeline?: PipelineState;
}) {
  const stageDebugFindings = allFindings.filter((finding) => String(finding.target_stage || '') === stage);
  const risk = String(stageState.critic?.overall_risk || 'low');
  const stageFindings = currentStageFindings;
  const blockingCount = stageFindings.filter((finding) => String(finding.severity || '') === 'blocking').length;
  const warningCount = stageFindings.filter((finding) => String(finding.severity || '') === 'warning').length;
  const epicHistoryOutputs = pipeline && String(pipeline.workflow_template || '') === 'epic_planning'
    ? ['epic_analysis', 'feature_generation', 'story_generation']
      .map((name) => ({ name, output: pipeline.stages[name]?.output || {} }))
      .filter((item) => Object.keys(item.output).length > 0)
    : [];
  return (
    <div className="ai-gen-stage-panel">
      {stageFindings.length ? (
        <div className="ai-gen-critic-card">
          <div className="ai-gen-critic-header">
            <strong>Critic review</strong>
            <span className={`ai-gen-badge ${risk}`}>Risk: {risk}</span>
          </div>
          <div className="ai-gen-muted">
            {blockingCount ? `Blocking: ${blockingCount}` : 'Blocking: 0'} {warningCount ? `| Warnings: ${warningCount}` : ''}
          </div>
        </div>
      ) : null}
      <details className="ai-gen-detail-block">
        <summary>View Details</summary>
        {stageDebugFindings.length ? (
          <>
            <div className="ai-gen-key">Stage Findings</div>
            <ul className="ai-gen-list">
              {stageDebugFindings.map((finding) => (
                <li key={String(finding.id || finding.message || Math.random())}>
                  [{String(finding.target_stage || stage).toUpperCase()}] {String(finding.status || 'open')}: {String(finding.message || 'Review needed')}
                </li>
              ))}
            </ul>
          </>
        ) : null}
        {Object.keys(stageState.output || {}).length ? (
          <pre className="ai-gen-prompt">{JSON.stringify(stageState.output, null, 2)}</pre>
        ) : epicHistoryOutputs.length ? (
          <>
            {epicHistoryOutputs.map((item) => (
              <details key={item.name} className="ai-gen-detail-block" open={item.name === 'story_generation'}>
                <summary>{stageLabel(item.name, pipeline)} Details</summary>
                <pre className="ai-gen-prompt">{JSON.stringify(item.output, null, 2)}</pre>
              </details>
            ))}
          </>
        ) : (
          <div className="ai-gen-muted">{stageLabel(stage, pipeline)} not generated yet.</div>
        )}
      </details>
    </div>
  );
}

function WorkflowActionBar({
  workflowActions,
  workflowTemplate,
  loading,
  onGenerate,
  onRegenerate,
  onApprove,
  onSkip,
  onRefresh,
  onViewHandoff,
  onCopyPacket,
  onSelectAll,
  onDeselectAll,
  onCreateSelected,
}: {
  workflowActions: string[];
  workflowTemplate: string;
  loading: boolean;
  onGenerate: () => void;
  onRegenerate: () => void;
  onApprove: () => void;
  onSkip: () => void;
  onRefresh: () => void;
  onViewHandoff: () => void;
  onCopyPacket: () => void;
  onSelectAll: () => void;
  onDeselectAll: () => void;
  onCreateSelected: () => void;
}) {
  return (
    <div className="ai-gen-actions ai-gen-actions-compact">
      {workflowActions.map((action) => {
        if (action === 'generate_epic_plan' || action === 'resume_epic_plan' || action === 'generate_feature_breakdown' || action === 'generate_execution_packet' || action === 'analyze_bug' || action === 'design_tests' || action === 'generate_ui_plan' || action === 'generate_ui_handoff' || action === 'start_research_plan') {
          return <button key={action} className="ai-gen-button" onClick={onGenerate} disabled={loading}>{workflowActionLabel(action, workflowTemplate)}</button>;
        }
        if (action === 'approve_plan' || action === 'approve_story') {
          return <button key={action} className="ai-gen-button secondary" onClick={onApprove} disabled={loading}>{workflowActionLabel(action, workflowTemplate)}</button>;
        }
        if (action === 'add_clarification') {
          return null;
        }
        if (action === 'regenerate_with_clarifications' || action === 'regenerate_story' || action === 'generate_fix_packet' || action === 'generate_regression_checklist' || action === 'generate_tasks' || action === 'complete_recommendation') {
          return <button key={action} className="ai-gen-button secondary" onClick={onRegenerate} disabled={loading}>{workflowActionLabel(action, workflowTemplate)}</button>;
        }
        if (action === 'select_all') {
          return <button key={action} className="ai-gen-button secondary" onClick={onSelectAll} disabled={loading}>{workflowActionLabel(action, workflowTemplate)}</button>;
        }
        if (action === 'deselect_all') {
          return <button key={action} className="ai-gen-button secondary" onClick={onDeselectAll} disabled={loading}>{workflowActionLabel(action, workflowTemplate)}</button>;
        }
        if (action === 'create_selected_work_items') {
          return <button key={action} className="ai-gen-button" onClick={onCreateSelected} disabled={loading}>{workflowActionLabel(action, workflowTemplate)}</button>;
        }
        if (action === 'open_in_vscode' || action === 'view_handoff') {
          return <button key={action} className="ai-gen-button secondary" onClick={onViewHandoff} disabled={loading}>{workflowActionLabel(action, workflowTemplate)}</button>;
        }
        if (action === 'copy_execution_packet' || action === 'copy_json' || action === 'download') {
          return <button key={action} className="ai-gen-button secondary" onClick={onCopyPacket} disabled={loading}>{workflowActionLabel(action, workflowTemplate)}</button>;
        }
        if (action === 'view_created_work_items') {
          return <button key={action} className="ai-gen-button secondary" onClick={onRefresh} disabled={loading}>{workflowActionLabel(action, workflowTemplate)}</button>;
        }
        return null;
      })}
      <button className="ai-gen-button secondary" onClick={onRefresh} disabled={loading}>Refresh</button>
    </div>
  );
}

function ChildTaskPlannerCard({
  tasks,
  selectedTitles,
  onToggle,
  onCreateSelected,
  createdPreview,
  loading,
}: {
  tasks: Array<Record<string, unknown>>;
  selectedTitles: string[];
  onToggle: (title: string) => void;
  onCreateSelected: () => void;
  createdPreview: Array<Record<string, unknown>>;
  loading: boolean;
}) {
  return (
    <div className="ai-gen-stage-panel">
      <details open className="ai-gen-detail-block">
        <summary>Child Task Preview</summary>
        <div className="ai-gen-muted">Preview only. Review the proposed tasks before creating them manually in Azure DevOps.</div>
        <ul className="ai-gen-list">
          {tasks.map((task) => {
            const title = String(task.title || '');
            const checked = selectedTitles.includes(title);
            return (
              <li key={title}>
                <label>
                  <input type="checkbox" checked={checked} onChange={() => onToggle(title)} />
                  {' '}
                  <strong>{String(task.type || 'task')}</strong>: {title}
                </label>
                <div className="ai-gen-muted">{String(task.description || '')}</div>
              </li>
            );
          })}
        </ul>
        <div className="ai-gen-actions ai-gen-actions-compact">
          <button className="ai-gen-button" onClick={onCreateSelected} disabled={loading || !selectedTitles.length}>
            Create Selected Tasks
          </button>
        </div>
        {createdPreview.length ? (
          <details className="ai-gen-detail-block">
            <summary>Selected Task Preview</summary>
            <pre className="ai-gen-prompt">{JSON.stringify(createdPreview, null, 2)}</pre>
          </details>
        ) : null}
      </details>
    </div>
  );
}

function DraftWorkItemsPanel({
  workflowTemplate,
  drafts,
  selectedDraftIds,
  onToggleDraft,
  onSelectAll,
  onDeselectAll,
  onApproveDrafts,
  onCreateSelected,
  onRetryFailed,
  createdPreview,
  loading,
}: {
  workflowTemplate: string;
  drafts: DraftWorkItem[];
  selectedDraftIds: string[];
  onToggleDraft: (draftId: string) => void;
  onSelectAll: () => void;
  onDeselectAll: () => void;
  onApproveDrafts: () => void;
  onCreateSelected: () => void;
  onRetryFailed: () => void;
  createdPreview: Array<{ draft_id: string; azure_work_item_id: number | null; title: string; type: string; status: 'created' | 'failed' | 'skipped'; creation_error?: string | null }>;
  loading: boolean;
}) {
  const flattened = flattenDrafts(drafts);
  const risks = draftRiskSummary(drafts);
  const header = workflowTemplate === 'story_delivery' ? 'Proposed Child Tasks' : 'Proposed Work Items';
  const failedCount = flattened.filter((draft) => draft.status === 'failed').length;
  return (
    <div className="ai-gen-stage-panel">
      <details open className="ai-gen-detail-block">
        <summary>{header}</summary>
        <div className="ai-gen-grid">
          <span className="ai-gen-key">Summary</span>
          <span>{workflowTemplate === 'story_delivery' ? 'Preview the proposed delivery tasks for the approved story.' : 'Review the generated backlog items before creating them in Azure DevOps.'}</span>
          <span className="ai-gen-key">Draft Count</span>
          <span>{flattened.length}</span>
          <span className="ai-gen-key">Approved</span>
          <span>{flattened.filter((draft) => draft.status === 'approved' || draft.status === 'created').length}</span>
        </div>
        <ul className="ai-gen-list">
          {drafts.map((draft) => (
            <DraftWorkItemRow key={draft.draft_id} draft={draft} selectedDraftIds={selectedDraftIds} onToggleDraft={onToggleDraft} />
          ))}
        </ul>
        {(risks.dependencies.length || risks.missingAcceptance.length) ? (
          <div className="ai-gen-warning">
            <div className="ai-gen-key">Risks / Dependencies</div>
            <ul className="ai-gen-list">
              {risks.dependencies.map((item) => <li key={`dep-${item}`}>{item}</li>)}
              {risks.missingAcceptance.map((item) => <li key={`acc-${item}`}>{item}</li>)}
            </ul>
          </div>
        ) : null}
        <div className="ai-gen-actions ai-gen-actions-compact">
          <button className="ai-gen-button secondary" onClick={onSelectAll} disabled={loading || !flattened.length}>
            Select All
          </button>
          <button className="ai-gen-button secondary" onClick={onDeselectAll} disabled={loading || !selectedDraftIds.length}>
            Deselect All
          </button>
          <button className="ai-gen-button secondary" onClick={onApproveDrafts} disabled={loading || !selectedDraftIds.length}>
            Approve Drafts
          </button>
          <button className="ai-gen-button" onClick={onCreateSelected} disabled={loading || !selectedDraftIds.length}>
            {workflowTemplate === 'story_delivery' ? 'Create Selected Child Tasks' : 'Create Selected Work Items'}
          </button>
          {failedCount ? (
            <button className="ai-gen-button secondary" onClick={onRetryFailed} disabled={loading}>
              Retry Failed
            </button>
          ) : null}
        </div>
        {createdPreview.length ? (
          <details className="ai-gen-detail-block">
            <summary>Created Work Items</summary>
            <ul className="ai-gen-list">
              {createdPreview.map((item) => (
                <li key={item.draft_id}>
                  {item.status === 'created'
                    ? `${item.type} #${item.azure_work_item_id}: ${item.title}`
                    : `${item.type}: ${item.title} failed${item.creation_error ? ` - ${item.creation_error}` : ''}`}
                </li>
              ))}
            </ul>
          </details>
        ) : null}
      </details>
    </div>
  );
}

function DraftWorkItemRow({
  draft,
  selectedDraftIds,
  onToggleDraft,
  level = 0,
}: {
  draft: DraftWorkItem;
  selectedDraftIds: string[];
  onToggleDraft: (draftId: string) => void;
  level?: number;
}) {
  const checked = selectedDraftIds.includes(draft.draft_id);
  const children = draft.children || draft.child_drafts || [];
  return (
    <li style={{ marginLeft: `${level * 16}px` }}>
      <label>
        <input type="checkbox" checked={checked} onChange={() => onToggleDraft(draft.draft_id)} />
        {' '}
        <strong>{draft.draft_type}</strong>: {draft.title}
      </label>
      <div className="ai-gen-muted">
        {draft.acceptance_criteria.length} acceptance criteria | {children.length} child tasks | {draft.status}{draft.azure_work_item_id ? ` #${draft.azure_work_item_id}` : ''}{draft.creation_error ? ` | ${draft.creation_error}` : ''}
      </div>
      <details className="ai-gen-detail-block">
        <summary>View Details</summary>
        <div className="ai-gen-muted">{draft.description}</div>
        {draft.acceptance_criteria.length ? <ListSection title="Acceptance Criteria" items={draft.acceptance_criteria} /> : null}
        {children.length ? (
          <ul className="ai-gen-list">
            {children.map((child) => (
              <DraftWorkItemRow
                key={child.draft_id}
                draft={child}
                selectedDraftIds={selectedDraftIds}
                onToggleDraft={onToggleDraft}
                level={level + 1}
              />
            ))}
          </ul>
        ) : null}
      </details>
    </li>
  );
}

function PipelineHandoff({ handoff, workflowTemplate }: { handoff?: HandoffRecord; workflowTemplate: string }) {
  if (['epic_planning', 'feature_planning'].includes(workflowTemplate)) {
    return null;
  }
  const executionWorkflow = ['task_execution', 'bug_fix'].includes(workflowTemplate);
  const canOpenInVsCode = Boolean(
    executionWorkflow
    && handoff?.handoff_id
    && handoff?.status === 'approved'
    && (handoff?.execution_packet || handoff?.content?.execution_packet)
  );
  const canCopyExecutionPacket = Boolean(
    executionWorkflow
    && (handoff?.execution_packet || handoff?.content?.execution_packet)
  );
  const emptySummary = workflowTemplate === 'ui_task'
    ? 'UI handoff not generated yet'
    : 'Handoff not approved yet';
  const emptyDetail = workflowTemplate === 'ui_task'
    ? 'Generate and approve the UI Handoff stage to complete this workflow.'
    : executionWorkflow
      ? 'Approve the current execution stage to open it directly in VS Code.'
      : 'Generate and approve the current stage handoff to continue.';

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
    await copyText(JSON.stringify(handoff, null, 2));
  };

  const copyHandoffMarkdown = async () => {
    if (!handoff) {
      return;
    }
    const markdown = await loadHandoffMarkdown(handoff.handoff_id);
    await copyText(markdown || JSON.stringify(handoff, null, 2));
  };

  const copyHandoffId = async () => {
    if (!handoff?.handoff_id) {
      return;
    }
    await copyText(handoff.handoff_id);
  };

  const copyExecutionPacket = async () => {
    if (!handoff) {
      return;
    }
    const packet = handoff.execution_packet || String(handoff.content?.execution_packet || '');
    if (packet) {
      await copyText(packet);
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
          <div>{handoff?.summary || emptySummary}</div>
          <div className="ai-gen-muted">
            {handoff
              ? `${formatTemplateStageName(handoff.stage)} v${handoff.version} ${handoff.status === 'approved' ? `approved ${handoff.approved_at || ''}` : 'draft - not approved'}`
              : emptyDetail}
          </div>
        </div>
        <span className={`ai-gen-badge ${handoff?.status || 'draft'}`}>{handoff?.status || 'draft'}</span>
      </div>
      <div className="ai-gen-actions ai-gen-actions-compact">
        {executionWorkflow ? (
          <button className="ai-gen-button secondary" onClick={openInVsCode} disabled={!canOpenInVsCode}>Open in VS Code</button>
        ) : null}
        <button className="ai-gen-button secondary" onClick={copyHandoffId} disabled={!handoff?.handoff_id}>Copy Handoff ID</button>
        {executionWorkflow ? (
          <button className="ai-gen-button secondary" onClick={copyExecutionPacket} disabled={!canCopyExecutionPacket}>Copy Execution Packet</button>
        ) : null}
        <button className="ai-gen-button secondary" onClick={copyHandoff} disabled={!handoff}>Copy JSON</button>
        <button className="ai-gen-button secondary" onClick={copyHandoffMarkdown} disabled={!handoff}>Copy Markdown</button>
        <button className="ai-gen-button secondary" onClick={downloadHandoff} disabled={!handoff}>Download</button>
      </div>
      {executionWorkflow && !canOpenInVsCode ? <div className="ai-gen-muted">An approved execution-ready handoff is not available yet.</div> : null}
      {handoff?.constraints?.length ? <ListSection title="Constraints" items={handoff.constraints} /> : null}
      {handoff?.open_questions?.length ? <WarningSection title="Open Questions" items={handoff.open_questions} /> : null}
      {handoff?.next_actions?.length ? <ListSection title="Next Actions" items={handoff.next_actions} /> : null}
      {handoff ? (
        <details className="ai-gen-detail-block">
          <summary>{handoff?.status === 'approved' ? 'View' : 'View Draft'}</summary>
          <pre className="ai-gen-prompt">{JSON.stringify(handoff.content || {}, null, 2)}</pre>
        </details>
      ) : null}
    </div>
  );
}

function CreatedWorkItemsPanel({
  items,
}: {
  items: Array<{ type?: string; azure_work_item_id?: number | null; title?: string; parent_azure_work_item_id?: number | null }>;
}) {
  return (
    <div className="ai-gen-stage-panel">
      <div className="ai-gen-key">Created Work Items</div>
      <ul className="ai-gen-list">
        {items.map((item) => (
          <li key={`${item.type}-${item.azure_work_item_id}-${item.title}`}>
            <strong>{item.type}</strong> #{item.azure_work_item_id} - {item.title}
            {item.parent_azure_work_item_id ? ` (Parent #${item.parent_azure_work_item_id})` : ''}
            {item.azure_work_item_id ? (
              <>
                {' '}
                <a href={`${window.location.origin}/_workitems/edit/${item.azure_work_item_id}`} target="_blank" rel="noreferrer">
                  Open in Azure DevOps
                </a>
              </>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

function clarificationPrompts(stageState: PipelineStageState): string[] {
  const unknowns = Array.isArray(stageState.output?.unknowns) ? stageState.output.unknowns.map((item) => String(item)) : [];
  const combined = unknowns.join(' ').toLowerCase();
  if (combined.includes('otp') && (combined.includes('retry') || combined.includes('expiry'))) {
    return [
      'How long should OTP be valid?',
      'How many retry attempts are allowed?',
      'Should resend OTP have cooldown?',
    ];
  }
  return unknowns.slice(0, 3);
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
  for (const stage of pipelineStageOrder(pipeline)) {
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

function pipelineStageOrder(pipeline?: PipelineState): string[] {
  if (!pipeline) {
    return [];
  }
  return Array.isArray(pipeline.stage_order) && pipeline.stage_order.length
    ? pipeline.stage_order
    : Object.keys(pipeline.stages || {});
}

function workflowRecommendation(workItemType: string, response?: AiGenState['response']) {
  const normalized = String(workItemType || '').trim() || 'Work Item';
  const lower = normalized.toLowerCase();
  if (lower.includes('epic')) {
    return {
      detectedType: 'Epic',
      workflowLabel: 'Epic Planning',
      outputs: ['Features', 'Stories', 'Dependencies', 'Risks'],
      actionLabel: 'Generate Epic Plan',
    };
  }
  if (lower.includes('feature')) {
    return {
      detectedType: 'Feature',
      workflowLabel: 'Feature Planning',
      outputs: ['Stories', 'Tasks', 'Acceptance Criteria'],
      actionLabel: 'Generate Feature Breakdown',
    };
  }
  if (lower.includes('bug')) {
    return {
      detectedType: 'Bug',
      workflowLabel: 'Bug Fix',
      outputs: ['Fix Packet', 'Regression Checklist'],
      actionLabel: 'Analyze Bug',
    };
  }
  if (lower.includes('task')) {
    return {
      detectedType: normalized,
      workflowLabel: 'Task Execution',
      outputs: ['Execution Packet', 'Validation Checklist'],
      actionLabel: 'Generate Execution Packet',
    };
  }
  return {
    detectedType: normalized,
    workflowLabel: response?.prompt_mode === 'respond' ? 'Research Workflow' : 'Story Delivery',
    outputs: response?.prompt_mode === 'respond'
      ? ['Investigation Summary', 'Recommendation']
      : ['Refined Requirement', 'Generated Tasks', 'Test Plan'],
    actionLabel: response?.prompt_mode === 'respond' ? 'Start Research Workflow' : 'Start Story Workflow',
  };
}

function buildTimeline(pipeline?: PipelineState): Array<{ label: string; timestamp?: string }> {
  if (!pipeline) {
    return [];
  }
  const items: Array<{ label: string; timestamp?: string }> = [
    { label: `Pipeline Created (v${pipeline.version})`, timestamp: pipeline.created_at },
  ];
  if (pipeline.pipeline_context?.comment_count) {
    items.push({ label: `Comments Loaded (${pipeline.pipeline_context.comment_count})`, timestamp: pipeline.pipeline_context.last_comment_sync_at || pipeline.updated_at });
  }
  if (pipeline.pipeline_context?.last_comment_sync_at) {
    items.push({ label: 'Comment Synced', timestamp: pipeline.pipeline_context.last_comment_sync_at });
  }
  for (const activity of pipeline.activity || []) {
    const label = activityLabel(activity, pipeline);
    if (label) {
      items.push({ label, timestamp: String(activity.timestamp || '') || undefined });
    }
  }
  const seen = new Set<string>();
  return items.filter((item) => {
    const key = `${item.label}::${item.timestamp || ''}`;
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

function activityLabel(activity: Record<string, unknown>, pipeline: PipelineState): string {
  const stage = typeof activity.stage === 'string' ? stageLabel(activity.stage, pipeline) : '';
  switch (String(activity.type || '')) {
    case 'pipeline_created':
      return 'Pipeline Created';
    case 'comments_loaded':
      return `Comments Loaded (${String(activity.count || '0')})`;
    case 'clarification_added':
      return stage ? `${stage}: Clarification Added` : 'Clarification Added';
    case 'stage_generated':
      return stage ? `${stage}: Stage Generated` : 'Stage Generated';
    case 'stage_regenerated':
      return stage ? `${stage}: Regenerated` : 'Regenerated';
    case 'stage_approved':
      return stage ? `${stage}: Plan Approved` : 'Plan Approved';
    case 'handoff_created':
      return stage ? `${stage}: Handoff Created` : 'Handoff Created';
    case 'work_item_creation_result':
      return 'Work Items Created';
    default:
      return '';
  }
}

function flattenDrafts(drafts: DraftWorkItem[]): DraftWorkItem[] {
  const items: DraftWorkItem[] = [];
  for (const draft of drafts) {
    items.push(draft);
    items.push(...flattenDrafts(draft.children || draft.child_drafts || []));
  }
  return items;
}

function draftRiskSummary(drafts: DraftWorkItem[]) {
  const flattened = flattenDrafts(drafts);
  return {
    dependencies: flattened
      .filter((draft) => draft.parent_draft_id && !flattened.some((candidate) => candidate.draft_id === draft.parent_draft_id))
      .map((draft) => `Missing parent draft for ${draft.title}`),
    missingAcceptance: flattened
      .filter((draft) => !draft.acceptance_criteria.length)
      .map((draft) => `${draft.title} has no acceptance criteria.`),
  };
}

function stageLabel(stage: string, pipeline?: PipelineState): string {
  return String(pipeline?.stage_metadata?.[stage]?.label || formatTemplateStageName(stage));
}

function formatTemplateStageName(value: string): string {
  return value
    .split('_')
    .filter(Boolean)
    .map((part) => part.toUpperCase() === 'UI' || part.toUpperCase() === 'DEV' || part.toUpperCase() === 'QA'
      ? part.toUpperCase()
      : part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

function formatTemplateName(value: string): string {
  return formatTemplateStageName(value);
}

function ownerRole(stage?: string, pipeline?: PipelineState): string {
  if (stage && pipeline?.stage_metadata?.[stage]?.role) {
    return String(pipeline.stage_metadata[stage]?.role);
  }
  return 'Team';
}

function workflowSummary(pipeline: PipelineState, stage: string, stageState?: PipelineStageState): string {
  if (pipeline.workflow_summary) {
    return String(pipeline.workflow_summary);
  }
  const output = stageState?.output || {};
  return String(output.summary || output.task_summary || output.refined_requirement || `${stageLabel(stage, pipeline)} is ready.`);
}

function stageNextAction(workflowActions: string[], pipeline?: PipelineState): string {
  if (!pipeline) {
    return 'Create the pipeline to start.';
  }
  if (!workflowActions.length) {
    return 'Refresh to load the latest workflow state.';
  }
  return workflowActionLabel(workflowActions[0], String(pipeline.workflow_template || ''));
}

function chipLabel(stage: string, stageState?: PipelineStageState, pipeline?: PipelineState): string {
  if (!stageState) {
    return 'locked';
  }
  if (stageState.approved) {
    return `${ownerRole(stage, pipeline)} approved`;
  }
  return stageState.status;
}

function inferWorkflowConfidence(workItemType: string): string {
  const normalized = String(workItemType || '').trim().toLowerCase();
  if (!normalized) {
    return 'low';
  }
  return ['epic', 'feature', 'bug', 'task', 'story', 'user story', 'qa task', 'ui task', 'spike'].some((item) => normalized.includes(item))
    ? 'high'
    : 'medium';
}

function generateActionLabel(stage: string, pipeline?: PipelineState, regenerate = false): string {
  const workflow = String(pipeline?.workflow_template || '');
  if (workflow === 'epic_planning' && stage === 'epic_analysis') {
    return regenerate ? 'Regenerate Epic Plan' : 'Generate Epic Plan';
  }
  if (workflow === 'feature_planning' && stage === 'feature_analysis') {
    return regenerate ? 'Regenerate Feature Breakdown' : 'Generate Feature Breakdown';
  }
  if (workflow === 'bug_fix' && stage === 'bug_analysis') {
    return regenerate ? 'Reanalyze Bug' : 'Analyze Bug';
  }
  if (workflow === 'task_execution' && stage === 'task_analysis') {
    return regenerate ? 'Regenerate Execution Analysis' : 'Generate Execution Packet';
  }
  if (workflow === 'qa_task' && stage === 'test_design') {
    return regenerate ? 'Regenerate Test Design' : 'Design Tests';
  }
  if (workflow === 'ui_task' && stage === 'ui_plan') {
    return regenerate ? 'Regenerate UI Plan' : 'Generate UI Plan';
  }
  if (workflow === 'spike' && stage === 'research_plan') {
    return regenerate ? 'Regenerate Research Plan' : 'Start Research Plan';
  }
  return regenerate ? 'Regenerate' : 'Generate';
}

function workflowActionLabel(action: string, workflowTemplate: string): string {
  switch (action) {
    case 'generate_epic_plan':
      return 'Generate Epic Plan';
    case 'resume_epic_plan':
      return 'Continue Epic Plan';
    case 'generate_feature_breakdown':
      return 'Generate Feature Breakdown';
    case 'approve_plan':
      return workflowTemplate === 'story_delivery' ? 'Approve Story' : 'Approve Plan';
    case 'select_all':
      return 'Select All';
    case 'deselect_all':
      return 'Deselect All';
    case 'create_selected_work_items':
      return workflowTemplate === 'story_delivery' ? 'Create Selected Child Tasks' : 'Create Selected Work Items';
    case 'view_created_work_items':
      return 'View Created Work Items';
    case 'regenerate_story':
      return 'Regenerate Story';
    case 'generate_tasks':
      return 'Generate Tasks';
    case 'add_clarification':
      return 'Add Clarification';
    case 'regenerate_with_clarifications':
      return 'Regenerate with Clarifications';
    case 'generate_execution_packet':
      return 'Generate Execution Packet';
    case 'copy_execution_packet':
      return 'Copy Execution Packet';
    case 'copy_json':
      return 'Copy JSON';
    case 'download':
      return 'Download';
    case 'open_in_vscode':
      return 'Open in VS Code';
    case 'analyze_bug':
      return 'Analyze Bug';
    case 'generate_fix_packet':
      return 'Generate Fix Packet';
    case 'generate_regression_checklist':
      return 'Generate Regression Checklist';
    case 'design_tests':
      return 'Design Tests';
    case 'generate_ui_plan':
      return 'Generate UI Plan';
    case 'generate_ui_handoff':
      return 'Generate UI Handoff';
    case 'start_research_plan':
      return 'Start Research Plan';
    case 'complete_recommendation':
      return 'Complete Recommendation';
    case 'view_handoff':
      return 'View Handoff';
    default:
      return formatTemplateStageName(action);
  }
}

async function copyText(value: string): Promise<void> {
  if (!value) {
    return;
  }
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(value);
      return;
    } catch {
      // Fall back to manual copy for restricted browser contexts.
    }
  }
  const textArea = document.createElement('textarea');
  textArea.value = value;
  textArea.setAttribute('readonly', 'true');
  textArea.style.position = 'fixed';
  textArea.style.opacity = '0';
  textArea.style.pointerEvents = 'none';
  document.body.appendChild(textArea);
  textArea.focus();
  textArea.select();
  try {
    const copied = document.execCommand('copy');
    if (copied) {
      return;
    }
  } finally {
    document.body.removeChild(textArea);
  }
  window.prompt('Clipboard access is unavailable here. Copy the text manually:', value);
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
