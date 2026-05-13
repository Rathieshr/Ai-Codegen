import * as SDK from 'azure-devops-extension-sdk';
import { IWorkItemFormService, WorkItemTrackingServiceIds } from 'azure-devops-extension-api/WorkItemTracking';

const BACKEND_URL = 'https://ai-codegen-production.up.railway.app/context';
const STATE_KEY = 'ai-gen:last-result';
const CAPABILITIES_URL = 'https://ai-codegen-production.up.railway.app/capabilities';
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
  stages: Record<string, PipelineStageState>;
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
  };
  work_item?: Record<string, unknown>;
  repo_context?: Record<string, unknown>;
  refinement?: Record<string, unknown>;
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
  };
};

export type AiGenState = {
  workItem: NormalizedWorkItem;
  response: AiGenResponse;
  generatedAt: string;
  capabilities?: BackendCapabilities;
  pipeline?: PipelineState;
  handoff?: HandoffRecord;
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
  const state = {
    workItem,
    response,
    generatedAt: new Date().toISOString(),
    capabilities,
    pipeline,
  };
  saveGeneratedState(state);
  return state;
}

export async function createPipeline(workItem: NormalizedWorkItem, response: AiGenResponse): Promise<PipelineState> {
  return postJson<PipelineState>(PIPELINE_CREATE_URL, {
    source: 'azure_devops',
    work_item: workItem,
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
  feedbackAuthor = 'azure_devops'
): Promise<PipelineState> {
  return postJson<PipelineState>(`${PIPELINE_BASE_URL}/${encodeURIComponent(pipelineId)}/run-stage`, {
    stage,
    regenerate,
    feedback_comment: feedbackComment,
    feedback_author: feedbackComment ? feedbackAuthor : undefined
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
  return postJson<PipelineState>(`${PIPELINE_BASE_URL}/${encodeURIComponent(pipelineId)}/approve-stage`, {
    stage,
    approved_by: approvedBy
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
    const response = await fetch(CAPABILITIES_URL, { method: 'GET' });
    if (!response.ok) {
      return undefined;
    }
    return await response.json() as BackendCapabilities;
  } catch {
    return undefined;
  }
}

export async function refreshPipelineState(
  workItem: NormalizedWorkItem,
  currentState?: AiGenState,
  pipelineOverride?: PipelineState
): Promise<AiGenState> {
  const [capabilities, pipeline] = await Promise.all([
    loadCapabilities(),
    pipelineOverride ? Promise.resolve(pipelineOverride) : loadPipelineForWorkItem(workItem.id)
  ]);
  const targetPipeline = pipelineOverride || pipeline || currentState?.pipeline;
  const targetStage = activeStageName(targetPipeline);
  const handoff = targetPipeline && targetStage && targetPipeline.stages[targetStage]?.handoff_id
    ? await loadHandoff(targetPipeline.stages[targetStage]?.handoff_id || '')
    : currentState?.handoff;
  const refreshed = {
    workItem,
    response: currentState?.response || await generateAiGenPrompt(workItem),
    generatedAt: new Date().toISOString(),
    capabilities,
    pipeline: targetPipeline,
    handoff
  };
  saveGeneratedState(refreshed);
  return refreshed;
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
  const ordered = ['ba', 'ui', 'dev', 'test', 'critic'];
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
