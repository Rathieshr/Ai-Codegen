import * as SDK from 'azure-devops-extension-sdk';
import { generateFromCurrentWorkItem } from './api';

SDK.init({
  loaded: true,
  applyTheme: true
});

SDK.ready().then(() => {
  SDK.register(SDK.getContributionId(), {
    execute: async () => {
      try {
        await generateFromCurrentWorkItem();
        await openWorkItemTab();
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Unable to generate ai-gen prompt';
        window.alert(`Unable to generate ai-gen prompt: ${message}`);
      }
    }
  });
});

async function openWorkItemTab(): Promise<void> {
  const host = SDK.getHost();
  const pageContext = SDK.getPageContext() as unknown as {
    webContext: {
      collection?: { uri?: string };
      project?: { name?: string };
    };
  };
  const baseUri = pageContext.webContext.collection?.uri || `${window.location.origin}/`;
  const project = pageContext.webContext.project?.name;
  if (!project) {
    window.alert('ai-gen prompt generated. Open the ai-gen tab to view it.');
    return;
  }
  const url = `${baseUri}${encodeURIComponent(project)}/_workitems`;
  window.open(url, host.name ? '_blank' : '_self');
}
