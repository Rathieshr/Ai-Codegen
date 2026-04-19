import * as vscode from 'vscode';

export type BackendMode = 'auto' | 'local' | 'railway';
export type BackendSource = 'local' | 'railway' | 'none';

export type BackendResolution = {
  url: string | null;
  source: BackendSource;
  healthy: boolean;
  reason: string;
  mode: BackendMode;
};

const DEFAULT_LOCAL_BACKEND_URL = 'http://127.0.0.1:8000';
const DEFAULT_RAILWAY_BACKEND_URL = 'https://ai-codegen-production.up.railway.app';
const HEALTH_TIMEOUT_MS = 1800;

export function getConfiguredBackendMode(): BackendMode {
  const mode = vscode.workspace
    .getConfiguration('ai-gen')
    .get<string>('backendMode', 'auto');

  return mode === 'local' || mode === 'railway' ? mode : 'auto';
}

export function getLocalBackendUrl(): string {
  return normalizeBaseUrl(vscode.workspace
    .getConfiguration('ai-gen')
    .get<string>('localBackendUrl', DEFAULT_LOCAL_BACKEND_URL));
}

export function getRailwayBackendUrl(): string {
  return normalizeBaseUrl(vscode.workspace
    .getConfiguration('ai-gen')
    .get<string>('railwayBackendUrl', DEFAULT_RAILWAY_BACKEND_URL));
}

export async function resolveBackendUrl(): Promise<BackendResolution> {
  const mode = getConfiguredBackendMode();
  const localUrl = getLocalBackendUrl();
  const railwayUrl = getRailwayBackendUrl();

  if (mode === 'local') {
    const healthy = await checkBackendHealth(localUrl);
    return {
      url: healthy ? localUrl : null,
      source: healthy ? 'local' : 'none',
      healthy,
      mode,
      reason: healthy
        ? 'Using local backend because local mode is selected and /health succeeded.'
        : `Local backend unavailable at ${localUrl}.`
    };
  }

  if (mode === 'railway') {
    if (!railwayUrl) {
      return {
        url: null,
        source: 'none',
        healthy: false,
        mode,
        reason: 'Railway backend mode is selected, but ai-gen.railwayBackendUrl is empty.'
      };
    }

    const healthy = await checkBackendHealth(railwayUrl);
    return {
      url: healthy ? railwayUrl : null,
      source: healthy ? 'railway' : 'none',
      healthy,
      mode,
      reason: healthy
        ? 'Using Railway backend because railway mode is selected and /health succeeded.'
        : `Railway backend unavailable at ${railwayUrl}.`
    };
  }

  if (await checkBackendHealth(localUrl)) {
    return {
      url: localUrl,
      source: 'local',
      healthy: true,
      mode,
      reason: 'Using local backend because /health succeeded.'
    };
  }

  if (railwayUrl && await checkBackendHealth(railwayUrl)) {
    return {
      url: railwayUrl,
      source: 'railway',
      healthy: true,
      mode,
      reason: 'Using Railway backend because local backend is unavailable.'
    };
  }

  return {
    url: null,
    source: 'none',
    healthy: false,
    mode,
    reason: railwayUrl
      ? 'No ai-gen backend available. Checked local and Railway.'
      : 'No ai-gen backend available. Checked local; Railway URL is not configured.'
  };
}

export async function checkBackendHealth(url: string): Promise<boolean> {
  if (!url) {
    return false;
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), HEALTH_TIMEOUT_MS);
  try {
    const response = await fetch(`${normalizeBaseUrl(url)}/health`, {
      method: 'GET',
      signal: controller.signal
    });
    return response.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(timeout);
  }
}

export function contextUrl(baseUrl: string): string {
  return `${normalizeBaseUrl(baseUrl)}/context`;
}

export function capabilitiesUrl(baseUrl: string): string {
  return `${normalizeBaseUrl(baseUrl)}/capabilities`;
}

export function snapshotUrl(baseUrl: string): string {
  return `${normalizeBaseUrl(baseUrl)}/execution/snapshot`;
}

export function validateUrl(baseUrl: string): string {
  return `${normalizeBaseUrl(baseUrl)}/execution/validate`;
}

function normalizeBaseUrl(value: string | undefined): string {
  const trimmed = (value || '').trim();
  if (!trimmed) {
    return '';
  }
  const withScheme = /^https?:\/\//i.test(trimmed) ? trimmed : `${defaultScheme(trimmed)}://${trimmed}`;
  const withoutContext = withScheme.endsWith('/context')
    ? withScheme.slice(0, -'/context'.length)
    : withScheme;
  return withoutContext.replace(/\/+$/, '');
}

function defaultScheme(value: string): 'http' | 'https' {
  return /^(localhost|127\.0\.0\.1|0\.0\.0\.0)(:\d+)?($|\/)/i.test(value)
    ? 'http'
    : 'https';
}
