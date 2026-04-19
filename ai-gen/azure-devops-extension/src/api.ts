import * as SDK from 'azure-devops-extension-sdk';
import { IWorkItemFormService, WorkItemTrackingServiceIds } from 'azure-devops-extension-api/WorkItemTracking';

const BACKEND_URL = 'https://ai-codegen-production.up.railway.app/context';
const STATE_KEY = 'ai-gen:last-result';

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
  [key: string]: unknown;
};

export type AiGenState = {
  workItem: NormalizedWorkItem;
  response: AiGenResponse;
  generatedAt: string;
};

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
  const state = {
    workItem,
    response,
    generatedAt: new Date().toISOString()
  };
  saveGeneratedState(state);
  return state;
}

function text(value: unknown): string {
  return value == null ? '' : String(value);
}

function primitiveId(value: unknown): number | string {
  return typeof value === 'number' || typeof value === 'string' ? value : '';
}

function htmlToText(value: string): string {
  if (!value) {
    return '';
  }
  const container = document.createElement('div');
  container.innerHTML = value;
  return (container.textContent || container.innerText || '').trim();
}
