import { HEIHostAdapter, HEIHostContext, HEITheme, correlationId, detectTheme, routeParameters } from './HostAdapter';

export class StandaloneHostAdapter implements HEIHostAdapter {
  readonly kind = 'standalone' as const;

  async initialize(): Promise<HEIHostContext> {
    const route = routeParameters();
    document.documentElement.dataset.heiHost = this.kind;
    return {
      hostType: this.kind,
      organization: { id: route.organizationId || '', name: route.organization || '', uri: '' },
      project: { id: route.projectId || '', name: route.project || '' },
      team: { id: route.teamId || '', name: route.team || '' },
      sprint: { id: route.iterationId || '', name: route.iteration || '', path: route.iterationPath || '' },
      user: { id: route.userId || 'standalone-user', name: route.userName || 'HEI User', email: '', role: standaloneRole(route.role) },
      repository: { id: route.repositoryId || '', name: route.repository || '', branch: route.branch || '' },
      extension: { id: 'hei-standalone', publisherId: 'HEI', version: '7.0' },
      route: { view: route.view || 'overview', workItemId: route.workItemId || '', repositoryId: route.repositoryId || '' },
      theme: detectTheme(),
      correlationId: route.correlationId || correlationId(),
    };
  }

  async getAccessToken(): Promise<string | undefined> { return undefined; }

  onThemeChanged(callback: (theme: HEITheme) => void): () => void {
    const observer = new MutationObserver(() => callback(detectTheme()));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class', 'data-theme'] });
    return () => observer.disconnect();
  }

  navigate(route: Record<string, string>): void {
    const url = new URL(window.location.href);
    Object.entries(route).forEach(([key, value]) => value ? url.searchParams.set(key, value) : url.searchParams.delete(key));
    window.history.pushState(route, '', url.toString());
    window.dispatchEvent(new PopStateEvent('popstate', { state: route }));
  }
}

function standaloneRole(value: string): string {
  return ['admin', 'contributor', 'viewer'].includes(value.toLowerCase()) ? value.toLowerCase() : 'viewer';
}
