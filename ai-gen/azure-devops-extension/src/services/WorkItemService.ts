import * as SDK from 'azure-devops-extension-sdk';
import { getClient } from 'azure-devops-extension-api';
import { WorkItemTrackingRestClient, IWorkItemFormService, WorkItemTrackingServiceIds } from 'azure-devops-extension-api/WorkItemTracking';

export class WorkItemService {
  public static async getFormService(): Promise<IWorkItemFormService> {
    return await SDK.getService<IWorkItemFormService>(WorkItemTrackingServiceIds.WorkItemFormService);
  }

  public static async getClient(): Promise<WorkItemTrackingRestClient> {
    return getClient(WorkItemTrackingRestClient);
  }

  public static async getWorkItem(id: number, project?: string): Promise<any> {
    const client = await this.getClient();
    return await client.getWorkItem(id, project, ["System.Title", "System.Description", "System.State", "System.WorkItemType", "System.AssignedTo", "System.IterationPath", "System.AreaPath"]);
  }
}
