export type HEITheme = 'light' | 'dark' | 'high-contrast';

export type HEIHostContext = {
  hostType: 'azure-devops' | 'standalone';
  organization: { id: string; name: string; uri: string };
  project: { id: string; name: string };
  team: { id: string; name: string };
  sprint: { id: string; name: string; path: string };
  user: { id: string; name: string; email: string; role: string };
  repository: { id: string; name: string; branch: string };
  extension: { id: string; publisherId: string; version: string };
  route: { view: string; workItemId: string; repositoryId: string };
  theme: HEITheme;
  correlationId: string;
};

export interface HEIHostAdapter {
  readonly kind: HEIHostContext['hostType'];
  initialize(): Promise<HEIHostContext>;
  getAccessToken(): Promise<string | undefined>;
  onThemeChanged(callback: (theme: HEITheme) => void): () => void;
  navigate(route: Record<string, string>): void;
}

export function routeParameters(): Record<string, string> {
  const params = new URLSearchParams(window.location.search);
  const hash = window.location.hash.replace(/^#\/?/, '');
  const hashParams = new URLSearchParams(hash.includes('?') ? hash.slice(hash.indexOf('?') + 1) : hash);
  const output: Record<string, string> = {};
  params.forEach((value, key) => { output[key] = value; });
  hashParams.forEach((value, key) => { if (!output[key]) output[key] = value; });
  return output;
}

export function detectTheme(): HEITheme {
  const value = `${document.documentElement.className} ${document.body?.className || ''} ${document.documentElement.dataset.theme || ''}`.toLowerCase();
  if (value.includes('high-contrast') || value.includes('highcontrast')) return 'high-contrast';
  if (value.includes('dark')) return 'dark';
  return 'light';
}

export function correlationId(): string {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? `hei_${crypto.randomUUID()}`
    : `hei_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

export function normalizeHostRole(value: unknown, fallback: 'admin' | 'contributor' | 'viewer'): string {
  const role = String(value || '').trim().toLowerCase();
  return role === 'admin' || role === 'contributor' || role === 'viewer' ? role : fallback;
}
