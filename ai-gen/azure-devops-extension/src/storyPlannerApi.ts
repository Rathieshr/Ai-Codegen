import * as SDK from 'azure-devops-extension-sdk';
import { CommonServiceIds, IProjectPageService } from 'azure-devops-extension-api/Common/CommonServices';
import { getClient } from 'azure-devops-extension-api/Common/Client';
import { IWorkItemFormService, WorkItemTrackingRestClient, WorkItemTrackingServiceIds } from 'azure-devops-extension-api/WorkItemTracking';
import { CreationPreview, PlannerSession, WorkItemContext } from './storyPlannerTypes';

const BASE_URL = 'https://ai-codegen-production.up.railway.app/story-planner';
const BACKEND_REQUEST_TIMEOUT_MS = 180000;
const AZURE_REQUEST_TIMEOUT_MS = 30000;

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
      'Microsoft.VSTS.Common.AcceptanceCriteria',
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
  const comments = await loadWorkItemComments(Number(fields['System.Id'] || 0), String(project?.name || SDK.getWebContext().project?.name || ''));
  return {
    id: Number(fields['System.Id'] || 0),
    title: String(fields['System.Title'] || ''),
    type: String(fields['System.WorkItemType'] || ''),
    description: String(fields['System.Description'] || ''),
    acceptanceCriteria: String(fields['Microsoft.VSTS.Common.AcceptanceCriteria'] || ''),
    comments,
    project: String(project?.name || SDK.getWebContext().project?.name || ''),
    collectionUri: getCollectionUri(),
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

export async function createAzureDevOpsItems(
  preview: CreationPreview,
  workItem: WorkItemContext,
  onProgress: (message: string) => void = () => undefined
): Promise<CreationResultPayload> {
  const collectionUri = workItem.collectionUri || getCollectionUri();
  onProgress('Requesting Azure DevOps access token.');
  const accessToken = await withTimeout(SDK.getAccessToken(), 'Timed out while requesting Azure DevOps access token.');
  if (!collectionUri || !workItem.project) {
    throw new Error('Azure DevOps project context is unavailable.');
  }
  const storyResult: CreationResultPayload['story'] = { status: 'creating' };
  const taskResults: CreationResultPayload['tasks'] = [];

  try {
    onProgress(`Creating User Story: ${preview.preview.story.title}`);
    const storyId = await createWorkItemViaRest(
      collectionUri,
      workItem.project,
      accessToken,
      preview.preview.story.type,
      preview.preview.story.fields,
      workItem.id > 0 ? workItem.id : undefined,
      'Timed out while creating the Azure DevOps User Story.'
    );
    storyResult.azure_work_item_id = storyId;
    storyResult.status = 'created';
    onProgress(`Created User Story #${storyId}.`);

    for (const task of preview.preview.tasks) {
      try {
        onProgress(`Creating Task: ${task.title}`);
        const createdTaskId = await createWorkItemViaRest(
          collectionUri,
          workItem.project,
          accessToken,
          task.type,
          task.fields,
          storyId,
          `Timed out while creating Azure DevOps task: ${task.title}`
        );
        taskResults.push({
          id: task.id,
          title: task.title,
          azure_work_item_id: createdTaskId,
          status: 'created',
        });
        onProgress(`Created Task #${createdTaskId}: ${task.title}`);
      } catch (error) {
        onProgress(`Task failed: ${task.title} - ${error instanceof Error ? error.message : String(error)}`);
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
    onProgress(`User Story creation failed: ${storyResult.error}`);
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

async function getJson<T>(url: string): Promise<T> {
  const response = await fetchWithTimeout(url, { method: 'GET' }, BACKEND_REQUEST_TIMEOUT_MS);
  if (!response.ok) {
    throw new Error(await response.text() || `Backend returned HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

async function postJson<T>(url: string, body: Record<string, unknown>): Promise<T> {
  const response = await fetchWithTimeout(
    url,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
    BACKEND_REQUEST_TIMEOUT_MS
  );
  if (!response.ok) {
    throw new Error(await response.text() || `Backend returned HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

async function fetchWithTimeout(url: string, init: RequestInit, timeoutMs = AZURE_REQUEST_TIMEOUT_MS): Promise<Response> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
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
    timer = window.setTimeout(() => reject(new Error(message)), AZURE_REQUEST_TIMEOUT_MS);
  });
  try {
    return await Promise.race([promise, timeout]);
  } finally {
    window.clearTimeout(timer);
  }
}

async function loadWorkItemComments(workItemId: number, project: string): Promise<string[]> {
  if (!workItemId || !project) {
    return [];
  }
  try {
    const client = getClient(WorkItemTrackingRestClient);
    const response = await withTimeout(
      client.getComments(workItemId, project, undefined, 10),
      'Timed out while loading Azure DevOps comments.'
    );
    const comments = Array.isArray(response?.comments) ? response.comments : [];
    return comments
      .map((comment) => String(comment?.text || '').trim())
      .filter(Boolean)
      .slice(-5);
  } catch {
    return [];
  }
}

async function createWorkItemViaRest(
  collectionUri: string,
  projectName: string,
  accessToken: string,
  type: string,
  fields: Record<string, string | null>,
  parentWorkItemId?: number,
  timeoutMessage?: string
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
        url: `${trimTrailingSlash(collectionUri)}/_apis/wit/workItems/${parentWorkItemId}`,
      },
    });
  }
  const typeName = `$${encodeURIComponent(type)}`;
  const response = await withTimeout(
    fetch(
      `${trimTrailingSlash(collectionUri)}/${encodeURIComponent(projectName)}/_apis/wit/workitems/${typeName}?api-version=7.1`,
      {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${accessToken}`,
          'Content-Type': 'application/json-patch+json',
        },
        body: JSON.stringify(operations),
      }
    ),
    timeoutMessage || `Timed out while creating Azure DevOps ${type}.`
  );
  if (!response.ok) {
    let body = '';
    try {
      body = await response.text();
    } catch {
      body = '';
    }
    throw new Error(`Azure DevOps returned HTTP ${response.status} while creating ${type}${body ? `: ${body.slice(0, 600)}` : ''}.`);
  }
  const body = await response.json() as { id: number };
  return body.id;
}

function getCollectionUri(): string {
  const pageContext = SDK.getPageContext() as unknown as {
    webContext?: {
      collection?: { uri?: string };
    };
  };
  return pageContext.webContext?.collection?.uri || `${window.location.origin}/`;
}

function trimTrailingSlash(value: string): string {
  return value.endsWith('/') ? value.slice(0, -1) : value;
}
