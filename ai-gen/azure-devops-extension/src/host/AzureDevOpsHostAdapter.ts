import * as SDK from 'azure-devops-extension-sdk';
import { HEIHostAdapter, HEIHostContext, HEITheme, correlationId, detectTheme, routeParameters } from './HostAdapter';

type WebContext = {
  account?: { id?: string; name?: string; uri?: string };
  collection?: { id?: string; name?: string; uri?: string };
  project?: { id?: string; name?: string };
  team?: { id?: string; name?: string };
  user?: { id?: string; name?: string; displayName?: string; email?: string; uniqueName?: string };
};

export class AzureDevOpsHostAdapter implements HEIHostAdapter {
  readonly kind = 'azure-devops' as const;
  private initialized = false;

  async initialize(): Promise<HEIHostContext> {
    const started = performance.now();
    if (!this.initialized) {
      SDK.init({ loaded: false, applyTheme: true });
      this.initialized = true;
    }
    await SDK.ready();
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
        role: normalizedRole(route.role),
      },
      repository: { id: route.repositoryId || '', name: route.repository || '', branch: route.branch || '' },
      extension: { id: String(extension.id || ''), publisherId: String(extension.publisherId || ''), version: String(extension.version || '') },
      route: { view: route.view || 'overview', workItemId: route.workItemId || '', repositoryId: route.repositoryId || '' },
      theme: detectTheme(),
      correlationId: route.correlationId || correlationId(),
    };
    document.documentElement.dataset.heiHost = this.kind;
    document.documentElement.dataset.heiStartupMs = String(Math.round(performance.now() - started));
    SDK.notifyLoadSucceeded();
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

function normalizedRole(value: string): string {
  const role = value.toLowerCase();
  if (role === 'admin' || role === 'contributor' || role === 'viewer') return role;
  return 'contributor';
}
