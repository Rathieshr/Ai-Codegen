import React, { useEffect, useMemo, useState } from 'react';
import { HEIHostContext } from './host';

export type RepositoryMapping = {
  organization_url: string;
  ado_project: string;
  repository_id: string;
  repository_name: string;
  branch: string;
  intelligenceRepositoryId?: string;
};

type AdoProject = { id: string; name: string };
type AdoRepository = { id: string; name: string; defaultBranch?: string; remoteUrl?: string; webUrl?: string };
type AzureDevOpsConnection = {
  connectionId: string;
  organizationUrl: string;
  organizationName: string;
  projectId: string;
  projectName: string;
  authenticationMode: string;
  status: string;
  credentialConfigured?: boolean;
  lastValidatedAt?: string;
  validationMessage?: string;
};

export function SettingsWorkspace({
  baseUrl, context, mapping, onMappingChanged, onOpenRepository, onError,
}: {
  baseUrl: string;
  context: HEIHostContext;
  mapping?: RepositoryMapping;
  onMappingChanged: (mapping: RepositoryMapping) => void;
  onOpenRepository: () => void;
  onError: (message: string) => void;
}) {
  const [projects, setProjects] = useState<AdoProject[]>([]);
  const [repositories, setRepositories] = useState<AdoRepository[]>([]);
  const [branches, setBranches] = useState<string[]>([]);
  const [adoProject, setAdoProject] = useState(mapping?.ado_project || context.project.name);
  const [repositoryId, setRepositoryId] = useState(mapping?.repository_id || '');
  const [branch, setBranch] = useState(mapping?.branch || context.repository.branch || 'main');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState('');
  const [connection, setConnection] = useState<AzureDevOpsConnection>();
  const [connectionBusy, setConnectionBusy] = useState(false);
  const [connectionNotice, setConnectionNotice] = useState('');
  const [organizationUrl, setOrganizationUrl] = useState(context.organization.uri);
  const [secretReference, setSecretReference] = useState('ADO_PAT');

  const selectedRepository = useMemo(
    () => repositories.find((repository) => repository.id === repositoryId),
    [repositories, repositoryId],
  );

  useEffect(() => {
    setAdoProject(mapping?.ado_project || context.project.name);
    setRepositoryId(mapping?.repository_id || '');
    setBranch(mapping?.branch || context.repository.branch || 'main');
  }, [mapping?.ado_project, mapping?.repository_id, mapping?.branch, context.project.name]);

  useEffect(() => { void loadProjects(); void loadAzureDevOpsConnection(); }, []);
  useEffect(() => { if (adoProject) void loadRepositories(adoProject); }, [adoProject]);
  useEffect(() => { if (adoProject && repositoryId) void loadBranches(adoProject, repositoryId); }, [adoProject, repositoryId]);

  async function loadProjects() {
    setLoading(true);
    try {
      const payload = await readJson<{ projects?: AdoProject[]; configured?: boolean; error?: string }>(
        `${baseUrl}/project-intelligence/connectors/azure-devops/projects`,
      );
      const items = payload.projects || [];
      setProjects(items);
      if (!adoProject) setAdoProject(items.find((item) => item.name === context.project.name)?.name || items[0]?.name || context.project.name);
      if (payload.configured === false) setNotice('Azure DevOps connector credentials are not configured on the HEI backend.');
    } catch (error) { onError(errorMessage(error, 'Unable to discover Azure DevOps projects.')); }
    finally { setLoading(false); }
  }

  async function loadRepositories(project: string) {
    setLoading(true);
    try {
      const payload = await readJson<{ repositories?: AdoRepository[] }>(
        `${baseUrl}/project-intelligence/connectors/azure-devops/repositories?ado_project=${encodeURIComponent(project)}`,
      );
      const items = payload.repositories || [];
      setRepositories(items);
      setRepositoryId((current) => items.some((item) => item.id === current) ? current : '');
    } catch (error) { setRepositories([]); onError(errorMessage(error, 'Unable to discover repositories.')); }
    finally { setLoading(false); }
  }

  async function loadBranches(project: string, id: string) {
    try {
      const payload = await readJson<{ branches?: string[] }>(
        `${baseUrl}/project-intelligence/connectors/azure-devops/branches?ado_project=${encodeURIComponent(project)}&repository_id=${encodeURIComponent(id)}`,
      );
      const items = (payload.branches || []).map(normalizeBranch).filter(Boolean);
      setBranches(items);
      const defaultBranch = normalizeBranch(selectedRepository?.defaultBranch || '');
      setBranch((current) => items.includes(current) ? current : defaultBranch || items[0] || 'main');
    } catch (error) { setBranches([]); onError(errorMessage(error, 'Unable to discover repository branches.')); }
  }

  async function loadAzureDevOpsConnection() {
    try {
      const payload = await readJson<{ connections?: AzureDevOpsConnection[] }>(`${baseUrl}/integrations/azure-devops/connections`);
      const items = payload.connections || [];
      const current = items.find((item) => item.projectId === context.project.id)
        || items.find((item) => item.projectName === context.project.name)
        || (items.length === 1 ? items[0] : undefined);
      setConnection(current);
      if (current?.organizationUrl) setOrganizationUrl(current.organizationUrl);
    } catch (error) {
      onError(errorMessage(error, 'Unable to load Azure DevOps connections.'));
    }
  }

  async function connectAzureDevOps() {
    if (!organizationUrl.trim()) { setConnectionNotice('Enter the Azure DevOps organization URL.'); return; }
    setConnectionBusy(true); setConnectionNotice('');
    try {
      let current = connection;
      if (!current) {
        current = await writeJson<AzureDevOpsConnection>(`${baseUrl}/integrations/azure-devops/connections`, {
          organizationUrl: organizationUrl.trim(),
          organizationName: context.organization.name,
          projectId: context.project.id || context.project.name,
          projectName: context.project.name,
          authenticationMode: 'PAT',
          secretReference: secretReference.trim() || 'ADO_PAT',
          permissions: ['Project.Read', 'WorkItems.Read', 'Code.Read', 'Build.Read'],
        });
      }
      const validated = await writeJson<AzureDevOpsConnection>(
        `${baseUrl}/integrations/azure-devops/connections/${encodeURIComponent(current.connectionId)}/validate`,
        undefined,
      );
      setConnection(validated);
      setConnectionNotice(validated.status === 'Connected'
        ? 'Azure DevOps connection validated. Synchronize the project to load work items, sprints, pull requests, and builds.'
        : validated.validationMessage || 'Azure DevOps validation failed. Review the backend credential reference and permissions.');
    } catch (error) {
      onError(errorMessage(error, 'Unable to connect Azure DevOps.'));
    } finally {
      setConnectionBusy(false);
    }
  }

  async function synchronizeAzureDevOps() {
    if (!connection?.connectionId) { setConnectionNotice('Connect and validate Azure DevOps before synchronizing.'); return; }
    setConnectionBusy(true); setConnectionNotice('');
    try {
      await writeJson(
        `${baseUrl}/integrations/azure-devops/projects/${encodeURIComponent(context.project.id || context.project.name)}/sync`,
        { connectionId: connection.connectionId, syncType: 'ManualSync' },
      );
      setConnectionNotice('Azure DevOps synchronization queued. Open Azure DevOps Center to review synchronized engineering state.');
    } catch (error) {
      onError(errorMessage(error, 'Unable to synchronize Azure DevOps.'));
    } finally {
      setConnectionBusy(false);
    }
  }

  async function saveMapping() {
    if (!selectedRepository) { setNotice('Select a repository before saving the mapping.'); return; }
    setSaving(true); setNotice('');
    try {
      const next: RepositoryMapping = {
        organization_url: mapping?.organization_url || context.organization.uri,
        ado_project: adoProject,
        repository_id: selectedRepository.id,
        repository_name: selectedRepository.name,
        branch: branch || 'main',
      };
      const intelligenceRepositoryId = await ensureRepositoryRegistration(baseUrl, next, selectedRepository, context);
      const saved = await writeJson<{ mapping: RepositoryMapping }>(
        `${baseUrl}/project-intelligence/connectors/azure-devops/mapping`,
        { project_id: context.project.id || context.project.name, mapping: next },
      );
      const configured = { ...saved.mapping, intelligenceRepositoryId };
      onMappingChanged(configured);
      setNotice('Repository mapping saved. Repository Intelligence will reuse this project configuration.');
    } catch (error) { onError(errorMessage(error, 'Unable to save repository mapping.')); }
    finally { setSaving(false); }
  }

  return (
    <section className="hei-settings-workspace" aria-label="HEI Settings">
      <header><span>Administration</span><h2>Settings</h2><p>Configure the project repository and review the current HEI host context.</p></header>

      <article className="hei-repository-mapping-card">
        <div className="hei-settings-card-heading">
          <div><span>System of Record</span><h3>Azure DevOps Connection</h3><p>Connect this project to synchronize work items, iterations, pull requests, and builds.</p></div>
          <strong>{connection?.status || 'Not Connected'}</strong>
        </div>
        <div className="hei-repository-mapping-form">
          <label><span>Organization URL</span><input value={organizationUrl} onChange={(event) => setOrganizationUrl(event.target.value)} disabled={connectionBusy || Boolean(connection)} placeholder="https://dev.azure.com/organization" /></label>
          <label><span>Project</span><input value={context.project.name} readOnly /></label>
          <label><span>Credential Reference</span><input value={secretReference} onChange={(event) => setSecretReference(event.target.value)} disabled={connectionBusy || Boolean(connection)} placeholder="ADO_PAT" /></label>
        </div>
        <p className="hei-settings-help">The credential reference names a secure backend environment variable. HEI never stores or returns the PAT value.</p>
        {connection?.validationMessage ? <p className="hei-settings-validation">{connection.validationMessage}</p> : null}
        {connectionNotice ? <p className="hei-settings-notice" role="status">{connectionNotice}</p> : null}
        <div className="hei-settings-actions">
          <button className="planner-button primary" type="button" onClick={() => void connectAzureDevOps()} disabled={connectionBusy || connection?.status === 'Connected'}>{connectionBusy ? 'Connecting...' : connection ? 'Validate Connection' : 'Connect Azure DevOps'}</button>
          <button className="planner-button secondary" type="button" onClick={() => void synchronizeAzureDevOps()} disabled={connectionBusy || connection?.status !== 'Connected'}>Synchronize Project</button>
          <button className="planner-button secondary" type="button" onClick={() => void loadAzureDevOpsConnection()} disabled={connectionBusy}>Refresh Connection</button>
        </div>
      </article>

      <article className="hei-repository-mapping-card">
        <div className="hei-settings-card-heading">
          <div><span>Project Configuration</span><h3>Repository Mapping</h3><p>Select the Azure DevOps repository and branch HEI should use for this project.</p></div>
          <strong>{mapping?.repository_id ? 'Connected' : 'Not Connected'}</strong>
        </div>
        <div className="hei-repository-mapping-form">
          <label><span>Azure DevOps Project</span><select value={adoProject} onChange={(event) => { setAdoProject(event.target.value); setRepositoryId(''); }} disabled={loading || saving}>
            {!projects.some((project) => project.name === adoProject) && adoProject ? <option value={adoProject}>{adoProject}</option> : null}
            {projects.map((project) => <option key={project.id || project.name} value={project.name}>{project.name}</option>)}
          </select></label>
          <label><span>Repository</span><select value={repositoryId} onChange={(event) => setRepositoryId(event.target.value)} disabled={loading || saving || !adoProject}>
            <option value="">Select repository</option>
            {repositories.map((repository) => <option key={repository.id} value={repository.id}>{repository.name}</option>)}
          </select></label>
          <label><span>Branch</span><select value={branch} onChange={(event) => setBranch(event.target.value)} disabled={saving || !repositoryId}>
            {!branches.includes(branch) && branch ? <option value={branch}>{branch}</option> : null}
            {branches.map((item) => <option key={item} value={item}>{item}</option>)}
          </select></label>
        </div>
        {notice ? <p className="hei-settings-notice" role="status">{notice}</p> : null}
        <div className="hei-settings-actions">
          <button className="planner-button primary" type="button" onClick={() => void saveMapping()} disabled={saving || loading || !repositoryId}>{saving ? 'Saving...' : 'Save Repository Mapping'}</button>
          <button className="planner-button secondary" type="button" onClick={() => void loadRepositories(adoProject)} disabled={loading || saving || !adoProject}>Refresh Repositories</button>
          {mapping?.repository_id ? <button className="planner-button secondary" type="button" onClick={onOpenRepository}>Open Repository Intelligence</button> : null}
        </div>
      </article>

      <div className="hei-settings-grid">
        <Group title="Azure DevOps Context"><Item label="Organization" value={context.organization.name} /><Item label="Project" value={context.project.name} /><Item label="Team" value={context.team.name} /><Item label="Sprint" value={context.sprint.name || context.sprint.path} /></Group>
        <Group title="Active Repository"><Item label="Repository" value={mapping?.repository_name || context.repository.name} /><Item label="Branch" value={mapping?.branch || context.repository.branch} /><Item label="Repository ID" value={mapping?.repository_id || context.repository.id} /></Group>
        <Group title="Host"><Item label="Host" value={context.hostType} /><Item label="Theme" value={context.theme} /><Item label="Extension" value={`${context.extension.publisherId}.${context.extension.id}`} /><Item label="Version" value={context.extension.version} /></Group>
        <Group title="Diagnostics"><Item label="Correlation ID" value={context.correlationId} /><Item label="User" value={context.user.name} /><Item label="Role" value={context.user.role} /></Group>
      </div>
    </section>
  );
}

async function ensureRepositoryRegistration(baseUrl: string, mapping: RepositoryMapping, repository: AdoRepository, context: HEIHostContext): Promise<string> {
  const listed = await readJson<{ repositories?: Array<{ repositoryId: string; url: string; metadata?: Record<string, unknown> }> }>(`${baseUrl}/repositories`);
  const remoteUrl = repository.webUrl || repository.remoteUrl || azureDevOpsRepositoryUrl(context, mapping, repository.name);
  const existing = (listed.repositories || []).find((item) =>
    item.metadata?.azureDevOpsRepositoryId === repository.id || normalizeUrl(item.url) === normalizeUrl(remoteUrl),
  );
  if (existing) return existing.repositoryId;
  const created = await writeJson<{ repositoryId: string }>(`${baseUrl}/repositories`, {
    name: repository.name,
    url: remoteUrl,
    defaultBranch: mapping.branch,
    repositoryType: 'AzureDevOps',
    authenticationType: 'PAT',
    projectId: context.project.id || context.project.name,
    requestedBy: context.user.name,
    metadata: { azureDevOpsRepositoryId: repository.id, adoProject: mapping.ado_project, branch: mapping.branch },
  });
  return created.repositoryId;
}

async function readJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  const payload = await response.json() as T & { error?: string | { message?: string } };
  if (!response.ok) throw new Error(typeof payload.error === 'string' ? payload.error : payload.error?.message || `HEI returned HTTP ${response.status}.`);
  return payload;
}

async function writeJson<T>(url: string, body?: unknown): Promise<T> {
  const response = await fetch(url, {
    method: 'POST',
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const payload = await response.json() as T & { error?: string | { message?: string } };
  if (!response.ok) throw new Error(typeof payload.error === 'string' ? payload.error : payload.error?.message || `HEI returned HTTP ${response.status}.`);
  return payload;
}

function normalizeBranch(value: string): string { return value.replace(/^refs\/heads\//, ''); }
function normalizeUrl(value: string): string { return value.trim().replace(/\/$/, '').toLowerCase(); }
function azureDevOpsRepositoryUrl(context: HEIHostContext, mapping: RepositoryMapping, repositoryName: string): string {
  const organizationUrl = (mapping.organization_url || context.organization.uri).replace(/\/$/, '');
  return `${organizationUrl}/${encodeURIComponent(mapping.ado_project)}/_git/${encodeURIComponent(repositoryName)}`;
}
function errorMessage(value: unknown, fallback: string): string { return value instanceof Error ? value.message : fallback; }
function Group({ title, children }: { title: string; children: React.ReactNode }) { return <article><h3>{title}</h3>{children}</article>; }
function Item({ label, value }: { label: string; value: string }) { return <div><span>{label}</span><strong>{value || 'Not available'}</strong></div>; }
