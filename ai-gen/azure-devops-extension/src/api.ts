import * as SDK from 'azure-devops-extension-sdk';
import { IWorkItemFormService, WorkItemTrackingServiceIds } from 'azure-devops-extension-api/WorkItemTracking';

const BACKEND_URL = 'https://ai-codegen-production.up.railway.app/context';
const STATE_KEY = 'ai-gen:last-result';
const CAPABILITIES_URL = 'https://ai-codegen-production.up.railway.app/capabilities';
const REFINEMENT_HEALTH_URL = 'https://ai-codegen-production.up.railway.app/refinement/health';
const PIPELINE_CREATE_URL = 'https://ai-codegen-production.up.railway.app/assist/pipeline/create';
const PIPELINE_BASE_URL = 'https://ai-codegen-production.up.railway.app/assist/pipeline';
const HANDOFFS_URL = 'https://ai-codegen-production.up.railway.app/handoffs';
const VSCODE_EXTENSION_ID = 'rathiesh.ai-gen-vscode';

export type NormalizedWorkItem = {
  id: number | string;
  title: string;
  description: string;
  acceptanceCriteria: string;
  tags: string[];
  type: string;
  areaPath: string;
  iterationPath: string;
  relations: unknown[];
};

export type AiGenResponse = {
  optimized_prompt?: string;
  detected_flow?: string;
  prompt_mode?: string;
  execution_confidence?: number;
  execution_confidence_level?: string;
  selected_execution_files?: string[];
  semantic_mapping_applied?: boolean;
  refinement_used?: boolean;
  refinement_source?: string;
  refinement_provider?: string;
  refinement_reason?: string;
  phi_used?: boolean;
  phi_status?: string;
  phi_raw_response_preview?: string;
  refined_base_flows?: string[];
  refined_variants?: string[];
  refined_surfaces?: string[];
  refined_base_flow?: string;
  refined_variant?: string;
  refined_surface?: string;
  refined_fields?: string[];
  refined_validations?: string[];
  refined_scope?: string[];
  refined_actors?: string[];
  refined_states?: string[];
  refinement_unknowns?: string[];
  refinement_confidence?: string;
  ba?: unknown;
  ui?: unknown;
  dev?: unknown;
  test?: unknown;
  critic?: unknown;
  handoffs?: unknown;
  pipeline_status?: unknown;
  [key: string]: unknown;
};

export type PipelineStageState = {
  stage: string;
  status: string;
  approved: boolean;
  approved_at?: string | null;
  approved_by?: string | null;
  version: number;
  output: Record<string, unknown>;
  critic?: Record<string, unknown> | null;
  handoff_id?: string | null;
  skip_reason?: string | null;
  review_feedback?: Array<{ id: string; author: string; timestamp: string; comment: string }>;
  unresolved_findings?: Array<Record<string, unknown>>;
  resolved_findings?: Array<Record<string, unknown>>;
};

export type PipelineState = {
  pipeline_id: string;
  source: string;
  work_item_id: string;
  current_stage: string;
  workflow_state?: string;
  workflow_summary?: string;
  stages: Record<string, PipelineStageState>;
  workflow_template?: string;
  stage_order?: string[];
  stage_metadata?: Record<string, { name?: string; label?: string; role?: string; optional?: boolean; approval_required?: boolean }>;
  work_item_classification?: {
    artifact_type?: string;
    intent?: string;
    complexity?: string;
    confidence?: string;
    workflow_template?: string;
    recommended_template?: string;
    reason?: string;
  };
  current_stage_findings?: Array<Record<string, unknown>>;
  current_stage_blocking_findings?: Array<Record<string, unknown>>;
  all_findings?: Array<Record<string, unknown>>;
  resolved_findings?: Array<Record<string, unknown>>;
  version: number;
  created_at: string;
  updated_at: string;
  allowed_actions?: {
    generate_stages?: string[];
    regenerate_stages?: string[];
    approve_stages?: string[];
    skip_stages?: string[];
    view_handoff_stages?: string[];
    feedback_stages?: string[];
    current_stage_actions?: string[];
    workflow_actions?: string[];
  };
  work_item?: Record<string, unknown>;
  repo_context?: Record<string, unknown>;
  refinement?: Record<string, unknown>;
  pipeline_context?: {
    effective_context_summary?: {
      clarification_count?: number;
      approval_count?: number;
      handoff_summary_count?: number;
      revision_note_count?: number;
      pipeline_feedback_count?: number;
      effective_text_preview?: string;
    };
    context_sources?: string[];
    last_comment_sync_at?: string | null;
    comment_count?: number;
    warnings?: string[];
  };
  context_warnings?: string[];
  draft_work_items?: DraftWorkItem[];
  activity?: Array<Record<string, unknown>>;
  created_work_items?: Array<{
    draft_id?: string;
    type?: string;
    title?: string;
    azure_work_item_id?: number | null;
    parent_azure_work_item_id?: number | null;
    parent_draft_id?: string | null;
  }>;
};

export type AzureComment = {
  id?: number | string;
  text: string;
  created_by?: string;
  created_at?: string;
};

export type DraftWorkItem = {
  id?: string;
  draft_id: string;
  type?: string;
  parent_work_item_id?: string | null;
  draft_type: string;
  title: string;
  description: string;
  acceptance_criteria: string[];
  tags: string[];
  area_path?: string;
  iteration_path?: string;
  parent_draft_id?: string | null;
  children?: DraftWorkItem[];
  child_drafts: DraftWorkItem[];
  selected?: boolean;
  source_stage: string;
  status: 'draft' | 'approved' | 'created' | 'skipped' | 'failed';
  azure_work_item_id?: number | null;
  creation_error?: string | null;
};

export type DraftWorkItemsResponse = {
  pipeline_id: string;
  workflow_template?: string;
  draft_work_items: DraftWorkItem[];
};

export type WorkItemCreateRequest = {
  draft_id: string;
  type: string;
  title?: string;
  fields: Record<string, string | null | undefined>;
  parent_link?: {
    parent_work_item_id?: string | null;
    parent_draft_id?: string | null;
  };
};

export type DraftWorkItemCreatePayload = {
  pipeline_id: string;
  work_item_create_requests: WorkItemCreateRequest[];
};

export type HandoffRecord = {
  handoff_id: string;
  pipeline_id: string;
  work_item_id: string;
  stage: string;
  version: number;
  status: string;
  created_at?: string;
  approved_at?: string | null;
  summary?: string;
  execution_packet?: string;
  selected_files?: string[];
  content?: Record<string, unknown>;
  refinement?: Record<string, unknown>;
  repo_context?: Record<string, unknown>;
  constraints?: string[];
  open_questions?: string[];
  next_actions?: string[];
};

export type BackendCapabilities = {
  backend_up?: boolean;
  refiner?: {
    enabled?: boolean;
    provider?: string | null;
    model?: string | null;
    configured?: boolean;
    deployment?: string | null;
  };
  refinerHealth?: {
    deployment?: string | null;
    health?: string;
    last_success?: string | null;
    last_failure?: string | null;
    average_latency_ms?: number;
    consecutive_failures?: number;
  };
};

export type AiGenState = {
  workItem: NormalizedWorkItem;
  response: AiGenResponse;
  generatedAt: string;
  capabilities?: BackendCapabilities;
  pipeline?: PipelineState;
  handoff?: HandoffRecord;
  draftWorkItems?: DraftWorkItem[];
  lastSyncAt?: string;
  commentWarning?: string;
  commentSyncWarning?: string;
};

export function clearGeneratedState(): void {
  window.sessionStorage.removeItem(STATE_KEY);
}

export async function getCurrentWorkItem(): Promise<NormalizedWorkItem> {
  const service = await SDK.getService<IWorkItemFormService>(WorkItemTrackingServiceIds.WorkItemFormService);
  const formService = service as IWorkItemFormService & { getWorkItemRelations?: () => Promise<unknown[]> };
  const fields = await service.getFieldValues([
    'System.Id',
    'System.Title',
    'System.Description',
    'Microsoft.VSTS.Common.AcceptanceCriteria',
    'System.Tags',
    'System.WorkItemType',
    'System.AreaPath',
    'System.IterationPath'
  ]) as Record<string, unknown>;
  const relations = typeof formService.getWorkItemRelations === 'function'
    ? await formService.getWorkItemRelations()
    : [];

  return {
    id: primitiveId(fields['System.Id']),
    title: text(fields['System.Title']),
    description: htmlToText(text(fields['System.Description'])),
    acceptanceCriteria: htmlToText(text(fields['Microsoft.VSTS.Common.AcceptanceCriteria'])),
    tags: text(fields['System.Tags']).split(';').map((tag) => tag.trim()).filter(Boolean),
    type: text(fields['System.WorkItemType']),
    areaPath: text(fields['System.AreaPath']),
    iterationPath: text(fields['System.IterationPath']),
    relations: Array.isArray(relations) ? relations : []
  };
}

export async function generateAiGenPrompt(workItem: NormalizedWorkItem): Promise<AiGenResponse> {
  const query = [
    workItem.title,
    workItem.description,
    workItem.acceptanceCriteria
  ].filter(Boolean).join('\n\n');

  if (!query.trim()) {
    throw new Error('Work item has no title, description, or acceptance criteria.');
  }

  let response: Response;
  try {
    response = await fetch(BACKEND_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        query,
        work_item: workItem,
        source: 'azure_devops'
      })
    });
  } catch {
    throw new Error(`Unable to reach ai-gen backend at ${BACKEND_URL}.`);
  }

  if (!response.ok) {
    const details = await response.text();
    throw new Error(`ai-gen backend returned HTTP ${response.status}: ${details}`);
  }

  const data = await response.json() as AiGenResponse;
  if (!data.optimized_prompt) {
    throw new Error('ai-gen backend returned an empty prompt.');
  }
  return data;
}

export function saveGeneratedState(state: AiGenState): void {
  window.sessionStorage.setItem(STATE_KEY, JSON.stringify(state));
}

export function loadGeneratedState(): AiGenState | undefined {
  const raw = window.sessionStorage.getItem(STATE_KEY);
  if (!raw) {
    return undefined;
  }
  try {
    return JSON.parse(raw) as AiGenState;
  } catch {
    return undefined;
  }
}

export async function generateFromCurrentWorkItem(): Promise<AiGenState> {
  const workItem = await getCurrentWorkItem();
  const response = await generateAiGenPrompt(workItem);
  const capabilities = await loadCapabilities();
  const pipeline = await loadPipelineForWorkItem(workItem.id).catch(() => undefined);
  const commentLoad = await loadAiGenComments(workItem.id);
  const state = {
    workItem,
    response,
    generatedAt: new Date().toISOString(),
    capabilities,
    pipeline,
    draftWorkItems: pipeline?.draft_work_items || [],
    lastSyncAt: new Date().toISOString(),
    commentWarning: commentLoad.warning,
  };
  saveGeneratedState(state);
  return state;
}

export async function createPipeline(
  workItem: NormalizedWorkItem,
  response: AiGenResponse,
  aiGenComments: AzureComment[] = [],
): Promise<PipelineState> {
  return postJson<PipelineState>(PIPELINE_CREATE_URL, {
    source: 'azure_devops',
    work_item: workItem,
    ai_gen_comments: aiGenComments,
    repo_context: {
      resolved_repo_id: stringValue(response.resolved_repo_id),
      resolved_branch_name: stringValue(response.resolved_branch_name),
      selected_execution_files: arrayValue(response.selected_execution_files),
      related_flows: arrayValue(response.related_flows),
      detected_flow: stringValue(response.detected_flow)
    },
    refinement: {
      base_flows: arrayValue(response.refined_base_flows),
      variants: arrayValue(response.refined_variants),
      surfaces: arrayValue(response.refined_surfaces),
      refined_base_flow: stringValue(response.refined_base_flow),
      refined_variant: stringValue(response.refined_variant),
      refined_surface: stringValue(response.refined_surface),
      refined_fields: arrayValue(response.refined_fields),
      refined_validations: arrayValue(response.refined_validations),
      refined_scope: arrayValue(response.refined_scope),
      actors: arrayValue(response.refined_actors),
      states: arrayValue(response.refined_states),
      refinement_unknowns: arrayValue(response.refinement_unknowns),
      refinement_confidence: stringValue(response.refinement_confidence)
    }
  });
}

export async function runPipelineStage(
  pipelineId: string,
  stage: string,
  regenerate = false,
  feedbackComment?: string,
  feedbackAuthor = 'azure_devops',
  aiGenComments: AzureComment[] = [],
): Promise<PipelineState> {
  return postJson<PipelineState>(`${PIPELINE_BASE_URL}/${encodeURIComponent(pipelineId)}/run-stage`, {
    stage,
    regenerate,
    feedback_comment: feedbackComment,
    feedback_author: feedbackComment ? feedbackAuthor : undefined,
    ai_gen_comments: aiGenComments,
  });
}

export async function runEpicPlan(
  pipelineId: string,
  aiGenComments: AzureComment[] = [],
): Promise<PipelineState> {
  return postJson<PipelineState>(`${PIPELINE_BASE_URL}/${encodeURIComponent(pipelineId)}/run-epic-plan`, {
    stage: 'epic_analysis',
    regenerate: false,
    ai_gen_comments: aiGenComments,
  });
}

export async function loadPipeline(pipelineId: string): Promise<PipelineState> {
  return getJson<PipelineState>(`${PIPELINE_BASE_URL}/${encodeURIComponent(pipelineId)}`);
}

export async function loadPipelineForWorkItem(workItemId: number | string): Promise<PipelineState | undefined> {
  try {
    const pipeline = await getJson<PipelineState | Record<string, never>>(
      `${PIPELINE_BASE_URL}?work_item_id=${encodeURIComponent(String(workItemId))}`
    );
    if (pipeline && typeof (pipeline as PipelineState).pipeline_id === 'string') {
      return pipeline as PipelineState;
    }
    return undefined;
  } catch {
    return undefined;
  }
}

export async function approvePipelineStage(pipelineId: string, stage: string, approvedBy = 'azure_devops'): Promise<PipelineState> {
  const url = `${PIPELINE_BASE_URL}/${encodeURIComponent(pipelineId)}/approve-stage`;
  const body = {
    stage,
    approved_by: approvedBy
  };
  try {
    return await postJson<PipelineState>(url, body);
  } catch (firstError) {
    try {
      return await postJson<PipelineState>(url, body);
    } catch (secondError) {
      const pipeline = await loadPipeline(pipelineId).catch(() => undefined);
      const stageState = pipeline?.stages?.[stage];
      if (pipeline && stageState && (stageState.approved || Boolean(stageState.handoff_id))) {
        return pipeline;
      }
      throw secondError instanceof Error ? secondError : firstError;
    }
  }
}

export async function approveStoryAndGenerateTasks(
  pipelineId: string,
  aiGenComments: AzureComment[] = [],
): Promise<PipelineState> {
  return postJson<PipelineState>(`${PIPELINE_BASE_URL}/${encodeURIComponent(pipelineId)}/approve-story-and-plan`, {
    stage: 'ba',
    regenerate: false,
    ai_gen_comments: aiGenComments,
  });
}

export async function skipPipelineStage(pipelineId: string, stage: string, reason: string): Promise<PipelineState> {
  return postJson<PipelineState>(`${PIPELINE_BASE_URL}/${encodeURIComponent(pipelineId)}/skip-stage`, {
    stage,
    reason
  });
}

export async function addStageFeedback(
  pipelineId: string,
  stage: string,
  comment: string,
  author = 'azure_devops'
): Promise<PipelineState> {
  return postJson<PipelineState>(`${PIPELINE_BASE_URL}/${encodeURIComponent(pipelineId)}/stage-feedback`, {
    stage,
    comment,
    author
  });
}

export async function loadHandoff(handoffId: string): Promise<HandoffRecord | undefined> {
  try {
    return await getJson<HandoffRecord>(`${HANDOFFS_URL}/${encodeURIComponent(handoffId)}`);
  } catch {
    return undefined;
  }
}

export function buildVsCodeHandoffLink(handoffId: string): string {
  return `vscode://${VSCODE_EXTENSION_ID}/loadHandoff?handoffId=${encodeURIComponent(handoffId)}`;
}

export async function loadHandoffMarkdown(handoffId: string): Promise<string | undefined> {
  try {
    const response = await fetch(`${HANDOFFS_URL}/${encodeURIComponent(handoffId)}/markdown`, { method: 'GET' });
    if (!response.ok) {
      return undefined;
    }
    return await response.text();
  } catch {
    return undefined;
  }
}

export async function loadLatestHandoff(workItemId: number | string, stage: string, status = 'approved'): Promise<HandoffRecord | undefined> {
  try {
    const response = await getJson<{ items?: HandoffRecord[] }>(
      `${HANDOFFS_URL}?work_item_id=${encodeURIComponent(String(workItemId))}&stage=${encodeURIComponent(stage)}&status=${encodeURIComponent(status)}`
    );
    return response.items?.[0];
  } catch {
    return undefined;
  }
}

export async function loadCapabilities(): Promise<BackendCapabilities | undefined> {
  try {
    const [capabilityResponse, healthResponse] = await Promise.all([
      fetch(CAPABILITIES_URL, { method: 'GET' }),
      fetch(REFINEMENT_HEALTH_URL, { method: 'GET' }).catch(() => undefined),
    ]);
    if (!capabilityResponse.ok) {
      return undefined;
    }
    const capabilities = await capabilityResponse.json() as BackendCapabilities;
    if (healthResponse && healthResponse.ok) {
      const health = await healthResponse.json() as BackendCapabilities["refinerHealth"];
      capabilities.refinerHealth = health;
      if (capabilities.refiner) {
        capabilities.refiner.deployment = health?.deployment || capabilities.refiner.deployment;
      }
    }
    return capabilities;
  } catch {
    return undefined;
  }
}

export async function loadDraftWorkItems(pipelineId: string): Promise<DraftWorkItemsResponse> {
  return getJson<DraftWorkItemsResponse>(`${PIPELINE_BASE_URL}/${encodeURIComponent(pipelineId)}/draft-work-items`);
}

export async function approveDraftWorkItems(pipelineId: string, draftIds: string[]): Promise<DraftWorkItemsResponse> {
  return postJson<DraftWorkItemsResponse>(`${PIPELINE_BASE_URL}/${encodeURIComponent(pipelineId)}/draft-work-items/approve`, {
    draft_ids: draftIds
  });
}

export async function loadDraftWorkItemCreatePayload(
  pipelineId: string,
  draftIds: string[],
  createChildTasks = true
): Promise<DraftWorkItemCreatePayload> {
  return postJson<DraftWorkItemCreatePayload>(`${PIPELINE_BASE_URL}/${encodeURIComponent(pipelineId)}/draft-work-items/create`, {
    draft_ids: draftIds,
    create_child_tasks: createChildTasks
  });
}

export async function markDraftWorkItemsCreated(
  pipelineId: string,
  createdItems: Array<Record<string, unknown>>
): Promise<DraftWorkItemsResponse> {
  return postJson<DraftWorkItemsResponse>(`${PIPELINE_BASE_URL}/${encodeURIComponent(pipelineId)}/draft-work-items/created`, {
    created_items: createdItems
  });
}

export async function storeWorkItemCreationResult(
  pipelineId: string,
  createdItems: Array<Record<string, unknown>>
): Promise<DraftWorkItemsResponse> {
  return postJson<DraftWorkItemsResponse>(`${PIPELINE_BASE_URL}/${encodeURIComponent(pipelineId)}/work-item-creation-result`, {
    created_items: createdItems
  });
}

export async function refreshPipelineState(
  workItem: NormalizedWorkItem,
  currentState?: AiGenState,
  pipelineOverride?: PipelineState
): Promise<AiGenState> {
  const [capabilities, pipeline, commentLoad] = await Promise.all([
    loadCapabilities(),
    pipelineOverride ? Promise.resolve(pipelineOverride) : loadPipelineForWorkItem(workItem.id),
    loadAiGenComments(workItem.id),
  ]);
  const targetPipeline = pipelineOverride || pipeline || currentState?.pipeline;
  const targetStage = activeStageName(targetPipeline);
  const draftWorkItems = targetPipeline?.pipeline_id
    ? (await loadDraftWorkItems(targetPipeline.pipeline_id).catch(() => undefined))?.draft_work_items || targetPipeline.draft_work_items || currentState?.draftWorkItems
    : currentState?.draftWorkItems;
  const handoff = targetPipeline && targetStage && targetPipeline.stages[targetStage]?.handoff_id
    ? await loadHandoff(targetPipeline.stages[targetStage]?.handoff_id || '')
    : undefined;
  const refreshed = {
    workItem,
    response: currentState?.response || await generateAiGenPrompt(workItem),
    generatedAt: new Date().toISOString(),
    capabilities,
    pipeline: targetPipeline,
    handoff,
    draftWorkItems,
    lastSyncAt: new Date().toISOString(),
    commentWarning: commentLoad.warning,
    commentSyncWarning: currentState?.commentSyncWarning,
  };
  saveGeneratedState(refreshed);
  return refreshed;
}

export async function loadAiGenComments(workItemId: number | string): Promise<{ comments: AzureComment[]; warning?: string }> {
  const pageContext = SDK.getPageContext() as unknown as {
    webContext: {
      collection?: { uri?: string };
      project?: { name?: string };
    };
  };
  const collectionUri = pageContext.webContext.collection?.uri || `${window.location.origin}/`;
  const projectName = pageContext.webContext.project?.name;
  if (!projectName || !workItemId) {
    return { comments: [] };
  }
  try {
    const accessToken = await SDK.getAccessToken();
    const response = await fetch(
      `${trimTrailingSlash(collectionUri)}/${encodeURIComponent(projectName)}/_apis/wit/workItems/${workItemId}/comments?api-version=7.1-preview.4`,
      {
        method: 'GET',
        headers: {
          Authorization: `Bearer ${accessToken}`,
          'Content-Type': 'application/json',
        },
      }
    );
    if (!response.ok) {
      return {
        comments: [],
        warning: 'Could not load Azure DevOps comments. Pipeline used work item fields only.',
      };
    }
    const payload = await response.json() as { comments?: Array<Record<string, unknown>> };
    const comments = Array.isArray(payload.comments) ? payload.comments : [];
    return {
      comments: comments
        .map((comment) => ({
          id: comment.id as number | string | undefined,
          text: String(comment.text || ''),
          created_by: typeof comment.createdBy === 'object' && comment.createdBy
            ? String((comment.createdBy as Record<string, unknown>).displayName || (comment.createdBy as Record<string, unknown>).uniqueName || '')
            : undefined,
          created_at: String(comment.createdDate || comment.publishedDate || ''),
        }))
        .filter((comment) => comment.text.trim().toLowerCase().startsWith('[ai-gen ')),
    };
  } catch {
    return {
      comments: [],
      warning: 'Could not load Azure DevOps comments. Pipeline used work item fields only.',
    };
  }
}

export async function createAzureDevOpsWorkItems(
  workItem: NormalizedWorkItem,
  requests: WorkItemCreateRequest[]
): Promise<Array<{ draft_id: string; azure_work_item_id: number | null; parent_azure_work_item_id?: number | null; title: string; type: string; status: 'created' | 'failed' | 'skipped'; creation_error?: string | null }>> {
  const pageContext = SDK.getPageContext() as unknown as {
    webContext: {
      collection?: { uri?: string };
      project?: { name?: string; id?: string };
    };
  };
  const collectionUri = pageContext.webContext.collection?.uri || `${window.location.origin}/`;
  const projectName = pageContext.webContext.project?.name;
  if (!projectName) {
    throw new Error('Azure DevOps project context is unavailable.');
  }
  const accessToken = await SDK.getAccessToken();
  const created: Array<{ draft_id: string; azure_work_item_id: number | null; parent_azure_work_item_id?: number | null; title: string; type: string; status: 'created' | 'failed' | 'skipped'; creation_error?: string | null }> = [];
  const parentMapping = new Map<string, number>();
  const ordered = [...requests].sort((left, right) => creationDepth(left) - creationDepth(right));
  for (const request of ordered) {
    const draftParentId = request.parent_link?.parent_draft_id
      ? parentMapping.get(request.parent_link.parent_draft_id)
      : undefined;
    const fallbackParentId = numberOrUndefined(request.parent_link?.parent_work_item_id);
    const parentId = draftParentId || fallbackParentId;
    if (request.parent_link?.parent_draft_id && !draftParentId && !fallbackParentId) {
      created.push({
        draft_id: request.draft_id,
        azure_work_item_id: null,
        title: String(request.title || request.fields['System.Title'] || ''),
        type: request.type,
        status: 'failed',
        creation_error: 'Parent work item was not created or selected.',
      });
      continue;
    }
    try {
      const workItemId = await createWorkItem(collectionUri, projectName, accessToken, request.type, request.fields, parentId);
      parentMapping.set(request.draft_id, workItemId);
      created.push({
        draft_id: request.draft_id,
        azure_work_item_id: workItemId,
        parent_azure_work_item_id: parentId ?? null,
        title: String(request.title || request.fields['System.Title'] || ''),
        type: request.type,
        status: 'created',
      });
    } catch (error) {
      created.push({
        draft_id: request.draft_id,
        azure_work_item_id: null,
        parent_azure_work_item_id: parentId ?? null,
        title: String(request.title || request.fields['System.Title'] || ''),
        type: request.type,
        status: 'failed',
        creation_error: error instanceof Error ? error.message : `Azure DevOps could not create ${request.type}.`,
      });
    }
  }
  await addCreationComment(collectionUri, projectName, accessToken, workItem.id, created.filter((item) => item.status === 'created' && item.azure_work_item_id));
  return created;
}

export async function addAiGenComment(
  workItemId: number | string,
  kind: 'Clarification' | 'Approval' | 'Handoff' | 'Revision',
  lines: string[]
): Promise<void> {
  const pageContext = SDK.getPageContext() as unknown as {
    webContext: {
      collection?: { uri?: string };
      project?: { name?: string };
    };
  };
  const collectionUri = pageContext.webContext.collection?.uri || `${window.location.origin}/`;
  const projectName = pageContext.webContext.project?.name;
  if (!projectName || !workItemId) {
    throw new Error('Azure DevOps work item context is unavailable.');
  }
  const accessToken = await SDK.getAccessToken();
  const text = [`[ai-gen ${kind}]`, ...lines].join('\n');
  const response = await fetch(
    `${trimTrailingSlash(collectionUri)}/${encodeURIComponent(projectName)}/_apis/wit/workItems/${workItemId}/comments?api-version=7.1-preview.4`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${accessToken}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ text })
    }
  );
  if (!response.ok) {
    throw new Error(`Azure DevOps returned HTTP ${response.status} while syncing ai-gen ${kind.toLowerCase()} comment.`);
  }
}

async function postJson<T>(url: string, body: Record<string, unknown>): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
  } catch {
    throw new Error(`Unable to reach ai-gen backend at ${url}.`);
  }
  if (!response.ok) {
    throw new Error(`ai-gen backend returned HTTP ${response.status}: ${await response.text()}`);
  }
  return await response.json() as T;
}

async function getJson<T>(url: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, { method: 'GET' });
  } catch {
    throw new Error(`Unable to reach ai-gen backend at ${url}.`);
  }
  if (!response.ok) {
    throw new Error(`ai-gen backend returned HTTP ${response.status}: ${await response.text()}`);
  }
  return await response.json() as T;
}

function text(value: unknown): string {
  return value == null ? '' : String(value);
}

function primitiveId(value: unknown): number | string {
  return typeof value === 'number' || typeof value === 'string' ? value : '';
}

function stringValue(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value : undefined;
}

function arrayValue(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item).trim()).filter(Boolean) : [];
}

function htmlToText(value: string): string {
  if (!value) {
    return '';
  }
  const container = document.createElement('div');
  container.innerHTML = value;
  return (container.textContent || container.innerText || '').trim();
}

function activeStageName(pipeline?: PipelineState): string {
  if (!pipeline) {
    return '';
  }
  const ordered = Array.isArray(pipeline.stage_order) && pipeline.stage_order.length
    ? pipeline.stage_order
    : Object.keys(pipeline.stages || {});
  for (const stage of ordered) {
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

export async function createWorkItem(
  collectionUri: string,
  projectName: string,
  accessToken: string,
  type: string,
  fields: Record<string, string | null | undefined>,
  parentWorkItemId?: number
): Promise<number> {
  const operations: Array<Record<string, unknown>> = [];
  for (const [field, value] of Object.entries(fields)) {
    if (value != null && String(value).trim()) {
      operations.push({ op: 'add', path: `/fields/${field}`, value });
    }
  }
  if (parentWorkItemId) {
    operations.push({
      op: 'add',
      path: '/relations/-',
      value: {
        rel: 'System.LinkTypes.Hierarchy-Reverse',
        url: `${trimTrailingSlash(collectionUri)}/${encodeURIComponent(projectName)}/_apis/wit/workItems/${parentWorkItemId}`,
      }
    });
  }
  const typeName = encodeURIComponent(`$${type}`);
  const response = await fetch(
    `${trimTrailingSlash(collectionUri)}/${encodeURIComponent(projectName)}/_apis/wit/workitems/${typeName}?api-version=7.1`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${accessToken}`,
        'Content-Type': 'application/json-patch+json'
      },
      body: JSON.stringify(operations)
    }
  );
  if (!response.ok) {
    throw new Error(`Azure DevOps returned HTTP ${response.status} while creating ${type}.`);
  }
  const body = await response.json() as { id: number };
  return body.id;
}

async function addCreationComment(
  collectionUri: string,
  projectName: string,
  accessToken: string,
  parentWorkItemId: number | string,
  createdItems: Array<{ draft_id: string; azure_work_item_id: number | null; title: string; type: string }>
): Promise<void> {
  if (!createdItems.length || !parentWorkItemId) {
    return;
  }
  const text = [
    '[ai-gen Work Items Created]',
    'Created:',
    ...createdItems.map((item) => `- ${item.type} #${item.azure_work_item_id}: ${item.title}`)
  ].join('\n');
  await fetch(
    `${trimTrailingSlash(collectionUri)}/${encodeURIComponent(projectName)}/_apis/wit/workItems/${parentWorkItemId}/comments?api-version=7.1-preview.4`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${accessToken}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ text })
    }
  ).catch(() => undefined);
}

function creationDepth(request: WorkItemCreateRequest): number {
  const parentDraftId = request.parent_link?.parent_draft_id;
  if (!parentDraftId) {
    return 0;
  }
  return parentDraftId.split("draft_").length;
}

function trimTrailingSlash(value: string): string {
  return value.endsWith('/') ? value.slice(0, -1) : value;
}

function numberOrUndefined(value: unknown): number | undefined {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}
