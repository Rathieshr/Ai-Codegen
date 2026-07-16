import React, { Suspense, lazy, useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { EngineeringCommandCenterShell, EngineeringWorkspace, WorkspaceNavigationItem, WorkspacePreferences } from './engineeringCommandCenterShell';
import { DashboardOverview } from './overviewDashboard';
import { createHostAdapter, HEIHostAdapter, HEIHostContext } from './host';
import type { RepositoryMapping } from './settingsWorkspace';
import './storyPlanner.css';

const OverviewDashboard = lazy(() => import('./overviewDashboard').then((module) => ({ default: module.OperationalOverviewDashboard })));
const NewRequirementWorkspace = lazy(() => import('./newRequirementWorkspace').then((module) => ({ default: module.NewRequirementWorkspace })));
const PlanningCenter = lazy(() => import('./planningCenter').then((module) => ({ default: module.PlanningCenter })));
const RepositoryCenter = lazy(() => import('./repositoryCenter').then((module) => ({ default: module.RepositoryCenter })));
const ExecutionCenter = lazy(() => import('./executionCenter').then((module) => ({ default: module.ExecutionCenter })));
const ApprovalCenter = lazy(() => import('./approvalCenter').then((module) => ({ default: module.ApprovalCenter })));
const AzureDevOpsCenter = lazy(() => import('./azureDevOpsCenter').then((module) => ({ default: module.AzureDevOpsCenter })));
const AgentCenter = lazy(() => import('./agentCenter').then((module) => ({ default: module.AgentCenter })));
const ActivityCenter = lazy(() => import('./activityCenter').then((module) => ({ default: module.ActivityCenter })));
const SettingsWorkspace = lazy(() => import('./settingsWorkspace').then((module) => ({ default: module.SettingsWorkspace })));

const BASE_URL = 'https://ai-codegen-production.up.railway.app';
const ROUTES = ['overview', 'new-requirement', 'planning', 'repository', 'execution', 'approvals', 'azure-devops', 'agents', 'activity', 'settings'] as const;
type HEIRoute = typeof ROUTES[number];

const adapter = createHostAdapter();

export function HEIApplication({ hostAdapter = adapter }: { hostAdapter?: HEIHostAdapter }) {
  const [context, setContext] = useState<HEIHostContext>();
  const [workspace, setWorkspace] = useState<EngineeringWorkspace>();
  const [route, setRoute] = useState<HEIRoute>('overview');
  const [overview, setOverview] = useState<DashboardOverview>();
  const [repositoryMapping, setRepositoryMapping] = useState<RepositoryMapping>();
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const [startupAttempt, setStartupAttempt] = useState(0);

  useEffect(() => {
    const started = performance.now();
    let active = true;
    setBusy(true);
    setError('');
    hostAdapter.initialize().then((hostContext) => {
      if (!active) return;
      setContext(hostContext);
      setRoute(normalizeRoute(hostContext.route.view));
      document.documentElement.dataset.heiTheme = hostContext.theme;
      const fallback = fallbackWorkspace(hostContext);
      setWorkspace(fallback);
      setBusy(false);
      void loadRepositoryConfiguration(hostContext).then((loaded) => {
        if (!active || !loaded) return;
        setRepositoryMapping(loaded);
        setContext((current) => current ? { ...current, repository: { id: loaded.repository_id, name: loaded.repository_name, branch: loaded.branch } } : current);
      }).catch((reason) => void recordDiagnostic(hostContext, 'RepositoryMappingFallback', { reason: message(reason) }));
      void recordDiagnostic(hostContext, 'HubLoaded', { startupMs: Math.round(performance.now() - started), theme: hostContext.theme, hostType: hostContext.hostType });
      void requestWorkspace(hostContext).then((loaded) => {
        if (!active) return;
        setWorkspace({ ...loaded, preferences: { ...loaded.preferences, theme: hostContext.theme }, navigation: navigationFor(hostContext.user.role) });
        void recordDiagnostic(hostContext, 'WorkspaceLoaded', { workspaceId: loaded.workspaceId, projectId: hostContext.project.id, userId: hostContext.user.id });
      }).catch((reason) => {
        void recordDiagnostic(hostContext, 'WorkspaceFallback', { reason: message(reason) });
      });
    }).catch((reason) => {
      if (!active) return;
      setError(message(reason)); setBusy(false);
    });
    const pop = () => setRoute(normalizeRoute(new URLSearchParams(window.location.search).get('view') || 'overview'));
    window.addEventListener('popstate', pop);
    return () => { active = false; window.removeEventListener('popstate', pop); };
  }, [hostAdapter, startupAttempt]);

  useEffect(() => context ? hostAdapter.onThemeChanged((theme) => {
    setContext((current) => current ? { ...current, theme } : current);
    document.documentElement.dataset.heiTheme = theme;
    setWorkspace((current) => current ? { ...current, preferences: { ...current.preferences, theme } } : current);
    void recordDiagnostic(context, 'ThemeChanged', { theme });
  }) : undefined, [context?.correlationId, hostAdapter]);

  useEffect(() => { if (context && route === 'overview') void loadOverview(context); }, [context?.project.id, route]);

  const role = context?.user.role || 'viewer';
  const canContribute = role === 'admin' || role === 'contributor';
  const canAdmin = role === 'admin';
  const projectId = context?.project.id || context?.project.name || '';
  const actor = context?.user.name || 'HEI User';
  const activeNavigation = useMemo(() => workspace?.navigation.find((item) => item.id === route)?.id || 'overview', [workspace, route]);

  function navigate(next: HEIRoute) {
    if (!context || next === route) return;
    hostAdapter.navigate({ view: next, workItemId: context.route.workItemId, repositoryId: context.route.repositoryId });
    setRoute(next);
    void recordDiagnostic(context, 'Navigation', { from: route, to: next });
  }

  function reportError(value: string) {
    setError(value);
    if (context) void recordDiagnostic(context, 'HubError', { view: route, message: value.slice(0, 500) });
  }

  async function updatePreferences(changes: Partial<WorkspacePreferences>) {
    if (!context || !workspace) return;
    setWorkspace({ ...workspace, preferences: { ...workspace.preferences, ...changes } });
    try {
      const response = await fetchWithTimeout(`${BASE_URL}/workspace/preferences`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json', 'X-HEI-User': context.user.id },
        body: JSON.stringify({ userId: context.user.id, role, ...changes }),
      }, 8000);
      if (!response.ok) throw new Error('Unable to save workspace preferences.');
      const preferences = await response.json() as WorkspacePreferences;
      setWorkspace((current) => current ? { ...current, preferences } : current);
    } catch (reason) { setError(message(reason)); }
  }

  async function loadOverview(hostContext: HEIHostContext) {
    try {
      const query = hostContext.project.id ? `?projectId=${encodeURIComponent(hostContext.project.id)}` : '';
      const response = await fetchWithTimeout(`${BASE_URL}/dashboard/overview${query}`, undefined, 8000);
      if (!response.ok) throw new Error(`Overview returned HTTP ${response.status}.`);
      const value = await response.json() as DashboardOverview;
      const normalized = {
        ...value,
        currentProject: {
          ...value.currentProject,
          projectId: hostContext.project.id || value.currentProject.projectId,
          name: hostContext.project.name || value.currentProject.name,
          configured: Boolean(hostContext.project.id || hostContext.project.name),
        },
      };
      setOverview(normalized);
      setWorkspace((current) => current ? { ...current, notifications: dashboardNotifications(normalized) } : current);
    } catch (reason) { setError(message(reason)); }
  }

  if (error && !context) return (
    <div className="hei-hub-startup-error" role="alert">
      <strong>HEI could not start</strong>
      <span>{error}</span>
      <button type="button" onClick={() => setStartupAttempt((value) => value + 1)}>Retry HEI startup</button>
      <small>If this continues, reload Azure DevOps and verify that extension content is allowed for this organization.</small>
    </div>
  );
  if (busy || !context) return <div className="hei-hub-loading" role="status"><strong>Starting HEI</strong><span>Connecting to the Azure DevOps workspace...</span></div>;

  return (
    <EngineeringCommandCenterShell
      workspace={workspace}
      activeNavigationId={activeNavigation}
      projectName={context.project.name}
      userName={context.user.name}
      roleLabel={roleLabel(role)}
      logoSrc="../../static/hei-icon-light.png"
      logoDarkSrc="../../static/hei-icon-dark.png"
      busy={busy}
      onNavigate={(item) => navigate(normalizeRoute(item.id))}
      onPreferencesChange={(changes) => void updatePreferences(changes)}
    >
      {error ? <div className="hei-hub-error" role="alert"><span>{error}</span><button type="button" onClick={() => setError('')}>Dismiss</button></div> : null}
      <Suspense fallback={<div className="hei-hub-route-loading" role="status">Loading {routeLabel(route)}...</div>}>
        {route === 'overview' ? <OverviewDashboard overview={overview} loading={busy} repositoryName={repositoryMapping?.repository_name || context.repository.name} onOpenRepository={() => navigate('repository')} onConfigureRepository={() => navigate('settings')} onRefresh={() => void loadOverview(context)} /> : null}
        {route === 'new-requirement' ? <NewRequirementWorkspace baseUrl={BASE_URL} context={context} onOpenApprovals={() => navigate('approvals')} onError={reportError} /> : null}
        {route === 'planning' ? <PlanningCenter baseUrl={BASE_URL} projectId={projectId} actor={actor} currentWorkItemId={context.route.workItemId} canContribute={canContribute} onGenerateExecutionPackage={() => navigate('execution')} onError={reportError} /> : null}
        {route === 'repository' ? <RepositoryCenter baseUrl={BASE_URL} preferredRepositoryId={repositoryMapping?.intelligenceRepositoryId || context.repository.id} actor={actor} canManage={canAdmin} onError={reportError} /> : null}
        {route === 'execution' ? <ExecutionCenter baseUrl={BASE_URL} onError={reportError} /> : null}
        {route === 'approvals' ? <ApprovalCenter baseUrl={BASE_URL} actor={actor} role={role} canApprove={canContribute} onError={reportError} /> : null}
        {route === 'azure-devops' ? <AzureDevOpsCenter baseUrl={BASE_URL} projectId={projectId} canApprove={canContribute} onOpenApprovals={() => navigate('approvals')} onError={reportError} /> : null}
        {route === 'agents' ? <AgentCenter baseUrl={BASE_URL} canRetry={canContribute} onOpenActivity={() => navigate('activity')} onError={reportError} /> : null}
        {route === 'activity' ? <ActivityCenter baseUrl={BASE_URL} onError={reportError} /> : null}
        {route === 'settings' ? <SettingsWorkspace baseUrl={BASE_URL} context={context} mapping={repositoryMapping} onMappingChanged={(next) => { setRepositoryMapping(next); setContext((current) => current ? { ...current, repository: { id: next.repository_id, name: next.repository_name, branch: next.branch } } : current); }} onOpenRepository={() => navigate('repository')} onError={reportError} /> : null}
      </Suspense>
    </EngineeringCommandCenterShell>
  );
}

async function requestWorkspace(context: HEIHostContext): Promise<EngineeringWorkspace> {
  const query = new URLSearchParams({ userId: context.user.id, role: context.user.role });
  const response = await fetchWithTimeout(`${BASE_URL}/workspace?${query.toString()}`, { headers: { 'X-HEI-User': context.user.id } }, 6000);
  if (!response.ok) throw new Error(`Workspace returned HTTP ${response.status}.`);
  return response.json() as Promise<EngineeringWorkspace>;
}

async function loadRepositoryConfiguration(context: HEIHostContext): Promise<RepositoryMapping | undefined> {
  const projectId = context.project.id || context.project.name;
  if (!projectId) return undefined;
  const mappingResponse = await fetchWithTimeout(`${BASE_URL}/project-intelligence/connectors/azure-devops/mapping?project_id=${encodeURIComponent(projectId)}`, undefined, 6000);
  if (!mappingResponse.ok) throw new Error(`Repository mapping returned HTTP ${mappingResponse.status}.`);
  const payload = await mappingResponse.json() as { mapping?: RepositoryMapping };
  const mapping = payload.mapping;
  if (!mapping?.repository_id) return undefined;
  const repositoriesResponse = await fetchWithTimeout(`${BASE_URL}/repositories`, undefined, 6000);
  if (!repositoriesResponse.ok) return mapping;
  const repositories = await repositoriesResponse.json() as { repositories?: Array<{ repositoryId: string; url: string; metadata?: Record<string, unknown> }> };
  const registered = (repositories.repositories || []).find((item) => item.metadata?.azureDevOpsRepositoryId === mapping.repository_id);
  return { ...mapping, intelligenceRepositoryId: registered?.repositoryId };
}

async function recordDiagnostic(context: HEIHostContext, eventType: string, metadata: Record<string, unknown>) {
  try {
    await fetchWithTimeout(`${BASE_URL}/workspace/diagnostics`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'X-HEI-User': context.user.id },
      body: JSON.stringify({ eventType, correlationId: context.correlationId, projectId: context.project.id, metadata }),
    }, 3000);
  } catch { /* Diagnostics must never block the hub. */ }
}

function navigationFor(role: string): WorkspaceNavigationItem[] {
  const canContribute = role === 'admin' || role === 'contributor';
  const canAdmin = role === 'admin';
  return [
    item('overview', 'Overview', 'home'),
    ...(canContribute ? [item('new-requirement', 'New Requirement', 'new')] : []),
    item('planning', 'Planning', 'plan'),
    item('repository', 'Repository', 'repo'),
    item('execution', 'Execution', 'exec'),
    ...(canContribute ? [item('approvals', 'Approvals', 'approve')] : []),
    item('azure-devops', 'Azure DevOps', 'ado'),
    ...(canContribute ? [item('agents', 'Agents', 'agent')] : []),
    item('activity', 'Activity', 'activity'),
    ...(canAdmin ? [item('settings', 'Administration', 'settings')] : []),
  ];
}

function item(id: HEIRoute, label: string, icon: string): WorkspaceNavigationItem { return { id, label, icon, target: id, enabled: true, lazy: id !== 'overview' }; }
function normalizeRoute(value: string): HEIRoute { return ROUTES.includes(value as HEIRoute) ? value as HEIRoute : 'overview'; }
function routeLabel(value: HEIRoute): string { return value.split('-').map((part) => part[0].toUpperCase() + part.slice(1)).join(' '); }
function roleLabel(value: string): string { return value === 'admin' ? 'HEI Administrator' : value === 'contributor' ? 'HEI Contributor' : 'HEI Viewer'; }
function message(value: unknown): string { return value instanceof Error ? value.message : String(value || 'HEI encountered an unexpected error.'); }
function dashboardNotifications(value: DashboardOverview) { return (value.notifications.items || []).map((entry) => ({ id: String(entry.id || entry.notificationId || ''), title: String(entry.title || 'HEI update'), message: String(entry.message || ''), severity: String(entry.severity || 'Info'), target: String(entry.target || entry.view || 'activity') })); }
function fallbackWorkspace(context: HEIHostContext): EngineeringWorkspace { return { workspaceId: 'hei-command-center', name: 'Engineering Command Center', description: 'Engineering Operating Console', version: '7.0', currentUser: { userId: context.user.id, role: context.user.role }, preferences: { userId: context.user.id, theme: 'system', density: 'comfortable', sidebarCollapsed: false, defaultWorkspace: 'overview', notificationsEnabled: true, commandPaletteEnabled: true }, navigation: navigationFor(context.user.role), capabilities: { lazyLoading: true, internalRouting: true }, status: { state: 'Ready', message: 'HEI services available', checkedAt: new Date().toISOString() }, notifications: [] }; }

async function fetchWithTimeout(input: RequestInfo | URL, init?: RequestInit, timeoutMs = 8000): Promise<Response> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(input, { ...init, signal: controller.signal });
  } catch (reason) {
    if (reason instanceof DOMException && reason.name === 'AbortError') throw new Error(`HEI service request timed out after ${Math.round(timeoutMs / 1000)} seconds.`);
    throw reason;
  } finally {
    window.clearTimeout(timeout);
  }
}

const root = document.getElementById('root');
if (root) createRoot(root).render(<HEIApplication />);
