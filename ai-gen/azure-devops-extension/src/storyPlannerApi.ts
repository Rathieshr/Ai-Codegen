import * as SDK from 'azure-devops-extension-sdk';
import { CommonServiceIds, IProjectPageService } from 'azure-devops-extension-api/Common/CommonServices';
import { getClient } from 'azure-devops-extension-api/Common/Client';
import { IWorkItemFormService, WorkItemTrackingRestClient, WorkItemTrackingServiceIds } from 'azure-devops-extension-api/WorkItemTracking';
import * as WebApi from 'azure-devops-extension-api/WebApi/WebApi';
import { CreationPreview, PlannerSession, WorkItemContext } from './storyPlannerTypes';

const BASE_URL = 'https://ai-codegen-production.up.railway.app/story-planner';
const REQUEST_TIMEOUT_MS = 12000;

type CreationResultPayload = {
  story: {
    azure_work_item_id?: number | null;
    status: 'pending' | 'creating' | 'created' | 'failed';
    error?: string | null;
  };
  tasks: Array<{
    id?: string;
    title: string;
    azure_work_item_id?: number | null;
    status: 'pending' | 'creating' | 'created' | 'failed';
    error?: string | null;
  }>;
};

export async function getCurrentWorkItemContext(): Promise<WorkItemContext> {
  const service = await withTimeout(
    SDK.getService<IWorkItemFormService>(WorkItemTrackingServiceIds.WorkItemFormService),
    'Timed out while connecting to the Azure DevOps work item form.'
  );
  const fields = await withTimeout(
    service.getFieldValues([
      'System.Id',
      'System.Title',
      'System.WorkItemType',
      'System.Description',
    ]),
    'Timed out while loading Azure DevOps work item fields.'
  );
  const projectService = await withTimeout(
    SDK.getService<IProjectPageService>(CommonServiceIds.ProjectPageService),
    'Timed out while loading Azure DevOps project context.'
  );
  const project = await withTimeout(
    projectService.getProject(),
    'Timed out while reading the current Azure DevOps project.'
  );
  return {
    id: Number(fields['System.Id'] || 0),
    title: String(fields['System.Title'] || ''),
    type: String(fields['System.WorkItemType'] || ''),
    description: String(fields['System.Description'] || ''),
    project: String(project?.name || SDK.getWebContext().project?.name || ''),
  };
}

export async function startPlannerSession(requirement: string): Promise<PlannerSession> {
  return postJson<PlannerSession>(`${BASE_URL}/sessions`, { requirement });
}

export async function loadPlannerSession(sessionId: string): Promise<PlannerSession> {
  return getJson<PlannerSession>(`${BASE_URL}/sessions/${encodeURIComponent(sessionId)}`);
}

export async function editPlannerStage(sessionId: string, stage: string, payload: Record<string, unknown>): Promise<PlannerSession> {
  return postJson<PlannerSession>(`${BASE_URL}/sessions/${encodeURIComponent(sessionId)}/edit`, { stage, payload });
}

export async function regeneratePlannerStage(sessionId: string, stage: string, userInput: string): Promise<PlannerSession> {
  return postJson<PlannerSession>(`${BASE_URL}/sessions/${encodeURIComponent(sessionId)}/regenerate`, { stage, user_input: userInput });
}

export async function approvePlannerStage(sessionId: string, stage: string): Promise<PlannerSession> {
  return postJson<PlannerSession>(`${BASE_URL}/sessions/${encodeURIComponent(sessionId)}/approve`, { stage });
}

export async function loadCreationPreview(sessionId: string): Promise<CreationPreview> {
  return postJson<CreationPreview>(`${BASE_URL}/sessions/${encodeURIComponent(sessionId)}/creation-preview`, {});
}

export async function storeCreationResult(sessionId: string, payload: CreationResultPayload): Promise<PlannerSession> {
  return postJson<PlannerSession>(`${BASE_URL}/sessions/${encodeURIComponent(sessionId)}/creation-result`, payload);
}

export async function createAzureDevOpsItems(preview: CreationPreview, workItem: WorkItemContext): Promise<CreationResultPayload> {
  const client = getClient(WorkItemTrackingRestClient);
  const storyPatch: WebApi.JsonPatchOperation[] = [
    { op: WebApi.Operation.Add, path: '/fields/System.Title', value: preview.preview.story.fields['System.Title'] || preview.preview.story.title, from: '' },
    { op: WebApi.Operation.Add, path: '/fields/System.Description', value: preview.preview.story.fields['System.Description'] || preview.preview.story.description, from: '' },
    { op: WebApi.Operation.Add, path: '/fields/Microsoft.VSTS.Common.AcceptanceCriteria', value: preview.preview.story.fields['Microsoft.VSTS.Common.AcceptanceCriteria'] || '', from: '' },
  ];
  if (workItem.id > 0) {
    storyPatch.push({
      op: WebApi.Operation.Add,
      path: '/relations/-',
      from: '',
      value: {
        rel: 'System.LinkTypes.Hierarchy-Reverse',
        url: buildWorkItemUrl(workItem.id),
      },
    });
  }

  const storyResult: CreationResultPayload['story'] = { status: 'creating' };
  const taskResults: CreationResultPayload['tasks'] = [];

  try {
    const story = await client.createWorkItem(storyPatch, workItem.project, preview.preview.story.type);
    storyResult.azure_work_item_id = story.id;
    storyResult.status = 'created';

    for (const task of preview.preview.tasks) {
      const taskPatch: WebApi.JsonPatchOperation[] = [
        { op: WebApi.Operation.Add, path: '/fields/System.Title', value: task.fields['System.Title'] || task.title, from: '' },
        { op: WebApi.Operation.Add, path: '/fields/System.Description', value: task.fields['System.Description'] || task.description, from: '' },
      ];
      if (task.fields['Microsoft.VSTS.Scheduling.StoryPoints']) {
        taskPatch.push({
          op: WebApi.Operation.Add,
          path: '/fields/Microsoft.VSTS.Scheduling.StoryPoints',
          from: '',
          value: task.fields['Microsoft.VSTS.Scheduling.StoryPoints'],
        });
      }
      taskPatch.push({
        op: WebApi.Operation.Add,
        path: '/relations/-',
        from: '',
        value: {
          rel: 'System.LinkTypes.Hierarchy-Reverse',
          url: buildWorkItemUrl(Number(story.id)),
        },
      });
      try {
        const createdTask = await client.createWorkItem(taskPatch, workItem.project, task.type);
        taskResults.push({
          id: task.id,
          title: task.title,
          azure_work_item_id: createdTask.id,
          status: 'created',
        });
      } catch (error) {
        taskResults.push({
          id: task.id,
          title: task.title,
          azure_work_item_id: null,
          status: 'failed',
          error: error instanceof Error ? error.message : String(error),
        });
      }
    }
  } catch (error) {
    storyResult.status = 'failed';
    storyResult.error = error instanceof Error ? error.message : String(error);
    for (const task of preview.preview.tasks) {
      taskResults.push({
        id: task.id,
        title: task.title,
        azure_work_item_id: null,
        status: 'pending',
      });
    }
  }

  return { story: storyResult, tasks: taskResults };
}

function buildWorkItemUrl(workItemId: number): string {
  const host = SDK.getHost();
  const project = SDK.getWebContext().project?.name || '';
  return `${window.location.origin}/${encodeURIComponent(host.name)}/${encodeURIComponent(project)}/_apis/wit/workItems/${workItemId}`;
}

async function getJson<T>(url: string): Promise<T> {
  const response = await fetchWithTimeout(url, { method: 'GET' });
  if (!response.ok) {
    throw new Error(await response.text() || `Backend returned HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

async function postJson<T>(url: string, body: Record<string, unknown>): Promise<T> {
  const response = await fetchWithTimeout(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(await response.text() || `Backend returned HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

async function fetchWithTimeout(url: string, init: RequestInit): Promise<Response> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new Error(`Timed out while contacting AI Story Planner backend at ${url}.`);
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
}

async function withTimeout<T>(promise: Promise<T>, message: string): Promise<T> {
  let timer = 0;
  const timeout = new Promise<never>((_, reject) => {
    timer = window.setTimeout(() => reject(new Error(message)), REQUEST_TIMEOUT_MS);
  });
  try {
    return await Promise.race([promise, timeout]);
  } finally {
    window.clearTimeout(timer);
  }
}
