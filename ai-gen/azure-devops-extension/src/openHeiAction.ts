import * as SDK from 'azure-devops-extension-sdk';
import { CommonServiceIds, IHostNavigationService } from 'azure-devops-extension-api/Common/CommonServices';
import { IWorkItemFormService, WorkItemTrackingServiceIds } from 'azure-devops-extension-api/WorkItemTracking';

SDK.init({ loaded: true, applyTheme: true });

SDK.ready().then(() => {
  SDK.register(SDK.getContributionId(), {
    execute: async () => {
      try {
        const workItem = await SDK.getService<IWorkItemFormService>(WorkItemTrackingServiceIds.WorkItemFormService);
        const id = await workItem.getId();
        const web = SDK.getWebContext() as unknown as { collection?: { uri?: string }; account?: { uri?: string }; project?: { name?: string } };
        const collectionUri = String(web.collection?.uri || web.account?.uri || '');
        const project = String(web.project?.name || '');
        if (!collectionUri || !project || !id) throw new Error('Azure DevOps project and work item context are required.');
        const params = new URLSearchParams({ view: 'planning', workItemId: String(id) });
        const url = `${collectionUri}${encodeURIComponent(project)}/_apps/hub/AiIntelliCodegen.hei-engineering-platform.hei-command-center?${params.toString()}`;
        const navigation = await SDK.getService<IHostNavigationService>(CommonServiceIds.HostNavigationService);
        navigation.navigate(url);
      } catch (error) {
        window.alert(error instanceof Error ? error.message : 'Unable to open HEI.');
      }
    },
  });
});
