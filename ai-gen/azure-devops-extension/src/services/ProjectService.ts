import * as SDK from 'azure-devops-extension-sdk';
import { CommonServiceIds, IProjectPageService } from 'azure-devops-extension-api/Common/CommonServices';

export class ProjectService {
  public static async getProject(): Promise<{ id: string; name: string } | undefined> {
    try {
      const projectService = await SDK.getService<IProjectPageService>(CommonServiceIds.ProjectPageService);
      return await projectService.getProject();
    } catch (e) {
      // Fallback for context
      const webContext = SDK.getWebContext();
      if (webContext.project) {
        return { id: webContext.project.id, name: webContext.project.name };
      }
      return undefined;
    }
  }

  public static getPageContext(): any {
    return SDK.getPageContext();
  }
}
