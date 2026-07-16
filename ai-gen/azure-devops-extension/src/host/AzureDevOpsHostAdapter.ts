import * as SDK from 'azure-devops-extension-sdk';
import { HEIHostAdapter, HEIHostContext, HEITheme, correlationId, detectTheme, normalizeHostRole, routeParameters } from './HostAdapter';

type WebContext = {
  account?: { id?: string; name?: string; uri?: string };
  collection?: { id?: string; name?: string; uri?: string };
  project?: { id?: string; name?: string };
  team?: { id?: string; name?: string };
  user?: { id?: string; name?: string; displayName?: string; email?: string; uniqueName?: string };
};

export class AzureDevOpsHostAdapter implements HEIHostAdapter {
  readonly kind = 'azure-devops' as const;
  private initialization?: Promise<void>;

  async initialize(): Promise<HEIHostContext> {
    const started = performance.now();
    if (!this.initialization) {
      this.initialization = SDK.init({ loaded: false, applyTheme: true });
    }
    try {
      await withTimeout(this.initialization, 10000, 'Azure DevOps did not complete the HEI extension handshake.');
    } catch (reason) {
      this.initialization = undefined;
      const detail = reason instanceof Error ? reason.message : 'Unable to initialize the Azure DevOps extension host.';
      void SDK.notifyLoadFailed(detail).catch(() => undefined);
      throw new Error(detail);
    }

    // Release the Azure DevOps host loader before resolving optional HEI context.
    void SDK.notifyLoadSucceeded().catch(() => undefined);
    const web = SDK.getWebContext() as unknown as WebContext;
    const user = SDK.getUser() as unknown as WebContext['user'];
    const extension = SDK.getExtensionContext();
    const route = routeParameters();
    const organization = web.account || web.collection || {};
    const context: HEIHostContext = {
      hostType: this.kind,
      organization: { id: String(organization.id || ''), name: String(organization.name || ''), uri: String(organization.uri || '') },
      project: { id: String(web.project?.id || ''), name: String(web.project?.name || '') },
      team: { id: String(web.team?.id || ''), name: String(web.team?.name || '') },
      sprint: { id: route.iterationId || '', name: route.iteration || '', path: route.iterationPath || '' },
      user: {
        id: String(user?.id || web.user?.id || ''),
        name: String(user?.displayName || user?.name || web.user?.displayName || web.user?.name || 'HEI User'),
        email: String(user?.email || user?.uniqueName || web.user?.email || web.user?.uniqueName || ''),
        // Keep the single HEI hub aligned with Project Intelligence while ADO
        // group mapping is paused. An explicit routed role still wins.
        role: normalizeHostRole(route.role, 'admin'),
      },
      repository: { id: route.repositoryId || '', name: route.repository || '', branch: route.branch || '' },
      extension: { id: String(extension.id || ''), publisherId: String(extension.publisherId || ''), version: String(extension.version || '') },
      route: { view: route.view || 'overview', workItemId: route.workItemId || '', repositoryId: route.repositoryId || '' },
      theme: detectTheme(),
      correlationId: route.correlationId || correlationId(),
    };
    document.documentElement.dataset.heiHost = this.kind;
    document.documentElement.dataset.heiStartupMs = String(Math.round(performance.now() - started));
    return context;
  }

  async getAccessToken(): Promise<string | undefined> {
    try { return await SDK.getAccessToken(); } catch { return undefined; }
  }

  onThemeChanged(callback: (theme: HEITheme) => void): () => void {
    const observer = new MutationObserver(() => callback(detectTheme()));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class', 'style', 'data-theme'] });
    if (document.body) observer.observe(document.body, { attributes: true, attributeFilter: ['class', 'style'] });
    return () => observer.disconnect();
  }

  navigate(route: Record<string, string>): void {
    const url = new URL(window.location.href);
    Object.entries(route).forEach(([key, value]) => value ? url.searchParams.set(key, value) : url.searchParams.delete(key));
    window.history.pushState(route, '', url.toString());
    window.dispatchEvent(new PopStateEvent('popstate', { state: route }));
  }
}

function withTimeout<T>(promise: Promise<T>, timeoutMs: number, message: string): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timeout = window.setTimeout(() => reject(new Error(message)), timeoutMs);
    promise.then(
      (value) => { window.clearTimeout(timeout); resolve(value); },
      (reason) => { window.clearTimeout(timeout); reject(reason); },
    );
  });
}
