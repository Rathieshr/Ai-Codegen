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
type AdministrationSection = 'azure-devops' | 'repositories' | 'agents' | 'integrations' | 'platform' | 'diagnostics' | 'security' | 'audit' | 'host' | 'feature-flags';
type AgentSummary = {
  agentId: string; name: string; enabled: boolean; status: string; health: string; queue: number; failures: number; nextRun?: string;
};
type AgentCenterPayload = { agents?: AgentSummary[]; summary?: { total?: number; enabled?: number; failed?: number; pendingJobs?: number }; generatedAt?: string };
type AgentPolicyPayload = { featureFlags?: Record<string, boolean>; policies?: string[] };
type PlatformSnapshot = {
  status?: string; version?: string; generatedAt?: string;
  platformHealth?: Record<string, unknown>; jobs?: { total?: number; running?: number; queued?: number; failed?: number };
  queues?: { depth?: number; health?: string }; services?: Array<{ id?: string; name?: string; status?: string; latencyMs?: number }>;
  performance?: { snapshotLatencyMs?: number; slowestService?: string }; storage?: { status?: string; fileCount?: number; megabytesUsed?: number; writable?: boolean };
  database?: { type?: string; status?: string; files?: number }; memory?: { status?: string; processMegabytes?: number };
  diagnostics?: { warnings?: Array<{ service?: string; message?: string }>; warningCount?: number; activityRecords?: number; auditRecords?: number; agentRuns?: number };
};
type AuditEvent = { event_id?: string; event_type?: string; timestamp?: string; pipeline_id?: string; actor?: string; stage?: string; details?: Record<string, unknown> };

const ADMINISTRATION_SECTIONS: Array<{ id: AdministrationSection; label: string; description: string }> = [
  { id: 'azure-devops', label: 'Azure DevOps', description: 'Connection and synchronization' },
  { id: 'repositories', label: 'Repositories', description: 'Project mapping and branches' },
  { id: 'agents', label: 'Agents', description: 'Runtime configuration and health' },
  { id: 'integrations', label: 'Integrations', description: 'Connected engineering systems' },
  { id: 'platform', label: 'Platform', description: 'Services, queues, and storage' },
  { id: 'diagnostics', label: 'Diagnostics', description: 'Operational warnings and latency' },
  { id: 'security', label: 'Security', description: 'Credentials, roles, and policy' },
  { id: 'audit', label: 'Audit', description: 'Administrative activity log' },
  { id: 'host', label: 'Host', description: 'Extension and workspace context' },
  { id: 'feature-flags', label: 'Feature Flags', description: 'Controlled agent activation' },
];

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
  const [section, setSection] = useState<AdministrationSection>('azure-devops');
  const [agents, setAgents] = useState<AgentCenterPayload>();
  const [agentPolicies, setAgentPolicies] = useState<AgentPolicyPayload>();
  const [platform, setPlatform] = useState<PlatformSnapshot>();
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [administrationBusy, setAdministrationBusy] = useState(false);
  const [featureFlagBusy, setFeatureFlagBusy] = useState('');
  const [administrationUpdatedAt, setAdministrationUpdatedAt] = useState('');
  const [administrationWarnings, setAdministrationWarnings] = useState<string[]>([]);

  const selectedRepository = useMemo(
    () => repositories.find((repository) => repository.id === repositoryId),
    [repositories, repositoryId],
  );

  useEffect(() => {
    setAdoProject(mapping?.ado_project || context.project.name);
    setRepositoryId(mapping?.repository_id || '');
    setBranch(mapping?.branch || context.repository.branch || 'main');
  }, [mapping?.ado_project, mapping?.repository_id, mapping?.branch, context.project.name]);

  useEffect(() => { void loadProjects(); void loadAzureDevOpsConnection(); void loadAdministrationData(); }, []);
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

  async function loadAdministrationData() {
    setAdministrationBusy(true);
    const requests = await Promise.allSettled([
      readJson<AgentCenterPayload>(`${baseUrl}/agents`),
      readJson<AgentPolicyPayload>(`${baseUrl}/project-intelligence/agents/policies`),
      readJson<PlatformSnapshot>(`${baseUrl}/command-center/diagnostics?role=admin`),
      readJson<{ events?: AuditEvent[] }>(`${baseUrl}/audit/events?limit=50`),
    ]);
    const warnings: string[] = [];
    if (requests[0].status === 'fulfilled') setAgents(requests[0].value); else warnings.push('Agent runtime data is unavailable.');
    if (requests[1].status === 'fulfilled') setAgentPolicies(requests[1].value); else warnings.push('Agent policy configuration is unavailable.');
    if (requests[2].status === 'fulfilled') setPlatform(requests[2].value); else warnings.push('Platform diagnostics are unavailable.');
    if (requests[3].status === 'fulfilled') setAuditEvents(requests[3].value.events || []); else warnings.push('Audit records are unavailable.');
    setAdministrationWarnings(warnings);
    setAdministrationUpdatedAt(new Date().toISOString());
    setAdministrationBusy(false);
  }

  async function updateFeatureFlag(name: string, enabled: boolean) {
    setFeatureFlagBusy(name);
    try {
      const payload = await writeJson<AgentPolicyPayload>(`${baseUrl}/project-intelligence/agents/flags`, { flags: { [name]: enabled } });
      setAgentPolicies((current) => ({ ...current, ...payload, featureFlags: payload.featureFlags || current?.featureFlags }));
      await loadAdministrationData();
    } catch (error) { onError(errorMessage(error, 'Unable to update the feature flag.')); }
    finally { setFeatureFlagBusy(''); }
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

  const currentSection = ADMINISTRATION_SECTIONS.find((item) => item.id === section) || ADMINISTRATION_SECTIONS[0];
  const connectionHealth = connection?.status || 'Not Connected';
  const platformHealth = platform?.status || (administrationWarnings.length ? 'Degraded' : 'Loading');
  const lastUpdated = administrationUpdatedAt || connection?.lastValidatedAt || 'Not recorded';

  return (
    <section className="hei-settings-workspace hei-administration-center" aria-label="HEI Administration Center">
      <header className="hei-administration-header">
        <div><span>Enterprise Administration</span><h2>Administration Center</h2><p>Configure platform connections, policies, runtime controls, security, and operational diagnostics.</p></div>
        <button className="planner-button secondary" type="button" onClick={() => void loadAdministrationData()} disabled={administrationBusy}>{administrationBusy ? 'Refreshing...' : 'Refresh Administration'}</button>
      </header>

      <div className="hei-administration-layout">
        <nav className="hei-administration-nav" aria-label="Administration sections">
          {ADMINISTRATION_SECTIONS.map((item) => <button key={item.id} type="button" className={section === item.id ? 'active' : ''} onClick={() => setSection(item.id)}><strong>{item.label}</strong><span>{item.description}</span></button>)}
        </nav>

        <main className="hei-administration-content">
          <header className="hei-administration-section-header">
            <div><span>Administration</span><h3>{currentSection.label}</h3><p>{currentSection.description}</p></div>
            <div className="hei-administration-metadata"><Status value={section === 'azure-devops' ? connectionHealth : section === 'repositories' ? (mapping?.repository_id ? 'Connected' : 'Not Connected') : platformHealth} /><small>Last updated<br /><strong>{formatDate(lastUpdated)}</strong></small></div>
          </header>

          {section === 'azure-devops' ? <AdministrationPanel title="Azure DevOps Connection" health={connectionHealth} validation={connection?.validationMessage || 'Validation pending'} diagnostics={connection?.credentialConfigured ? 'Secure credential reference configured' : 'Credential reference required'} updatedAt={connection?.lastValidatedAt || lastUpdated}><article className="hei-repository-mapping-card">
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
      </article></AdministrationPanel> : null}

      {section === 'repositories' ? <AdministrationPanel title="Repository Mapping" health={mapping?.repository_id ? 'Connected' : 'Needs Configuration'} validation={mapping?.repository_id ? 'Project mapping saved' : 'Repository selection required'} diagnostics={mapping?.repository_id ? `${mapping.repository_name} · ${mapping.branch}` : 'No active project mapping'} updatedAt={lastUpdated}><article className="hei-repository-mapping-card">
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
      </article></AdministrationPanel> : null}

      {section === 'agents' ? <AdministrationPanel title="Agent Configuration" health={(agents?.summary?.failed || 0) > 0 ? 'Needs Attention' : 'Healthy'} validation="Human approval policy active" diagnostics={`${agents?.summary?.pendingJobs || 0} queued jobs`} updatedAt={agents?.generatedAt || lastUpdated}>
        <div className="hei-administration-card-grid">{(agents?.agents || []).map((agent) => <article className="hei-administration-card" key={agent.agentId}><div><h4>{agent.name}</h4><Status value={agent.enabled ? agent.health || agent.status : 'Disabled'} /></div><Item label="Runtime" value={agent.status} /><Item label="Queue" value={String(agent.queue || 0)} /><Item label="Failures" value={String(agent.failures || 0)} /><Item label="Next Run" value={agent.nextRun ? formatDate(agent.nextRun) : 'Event driven'} /></article>)}</div>
        {!(agents?.agents || []).length ? <Empty message="No agents are registered. Agent definitions will appear after the runtime is initialized." /> : null}
      </AdministrationPanel> : null}

      {section === 'integrations' ? <AdministrationPanel title="Integration Inventory" health={connection?.status === 'Connected' && mapping?.repository_id ? 'Healthy' : 'Needs Configuration'} validation={connection?.validationMessage || 'Connection validation pending'} diagnostics="Credentials remain in secure backend references" updatedAt={connection?.lastValidatedAt || lastUpdated}>
        <div className="hei-administration-card-grid"><Integration name="Azure DevOps" status={connectionHealth} detail={connection?.organizationName || context.organization.name} /><Integration name="Repository Intelligence" status={mapping?.repository_id ? 'Connected' : 'Not Connected'} detail={mapping?.repository_name || 'Repository mapping required'} /><Integration name="Knowledge Registry" status="Managed by HEI" detail="Project-scoped engineering knowledge" /><Integration name="AI Providers" status="Managed by backend" detail="Provider routing and health are isolated from client settings" /></div>
      </AdministrationPanel> : null}

      {section === 'platform' ? <AdministrationPanel title="Platform Operations" health={platformHealth} validation={`${platform?.services?.length || 0} services inspected`} diagnostics={`${platform?.jobs?.failed || 0} failed jobs · ${platform?.queues?.depth || 0} queued`} updatedAt={platform?.generatedAt || lastUpdated}>
        <div className="hei-settings-grid"><Group title="Runtime"><Item label="Version" value={platform?.version || context.extension.version} /><Item label="Jobs" value={String(platform?.jobs?.total || 0)} /><Item label="Running" value={String(platform?.jobs?.running || 0)} /><Item label="Queue Health" value={platform?.queues?.health || 'Not available'} /></Group><Group title="Persistence"><Item label="Database" value={platform?.database?.type || 'Not available'} /><Item label="Database Health" value={platform?.database?.status || 'Not available'} /><Item label="Storage" value={platform?.storage?.status || 'Not available'} /><Item label="Process Memory" value={platform?.memory?.processMegabytes == null ? 'Not available' : `${platform.memory.processMegabytes} MB`} /></Group></div>
        <div className="hei-administration-service-list">{(platform?.services || []).map((service) => <div key={service.id || service.name}><strong>{service.name || service.id}</strong><Status value={service.status || 'Unknown'} /><span>{service.latencyMs == null ? 'Latency not recorded' : `${service.latencyMs} ms`}</span></div>)}</div>
      </AdministrationPanel> : null}

      {section === 'diagnostics' ? <AdministrationPanel title="Platform Diagnostics" health={platformHealth} validation="Admin access verified" diagnostics={`${platform?.diagnostics?.warnings?.length ?? platform?.diagnostics?.warningCount ?? 0} active warnings`} updatedAt={platform?.generatedAt || lastUpdated}>
        <div className="hei-settings-grid"><Group title="Performance"><Item label="Snapshot Latency" value={platform?.performance?.snapshotLatencyMs == null ? 'Not recorded' : `${platform.performance.snapshotLatencyMs} ms`} /><Item label="Slowest Service" value={platform?.performance?.slowestService || 'Not recorded'} /><Item label="Correlation ID" value={context.correlationId} /></Group><Group title="Records"><Item label="Activity" value={String(platform?.diagnostics?.activityRecords ?? 'Not available')} /><Item label="Audit" value={String(platform?.diagnostics?.auditRecords ?? auditEvents.length)} /><Item label="Agent Runs" value={String(platform?.diagnostics?.agentRuns ?? 'Not available')} /></Group></div>
        <div className="hei-administration-warning-list">{(platform?.diagnostics?.warnings || []).map((warning, index) => <p key={`${warning.service}-${index}`}><strong>{warning.service || 'Platform'}</strong>{warning.message || 'Service warning recorded.'}</p>)}{administrationWarnings.map((warning) => <p key={warning}><strong>Data Source</strong>{warning}</p>)}{!(platform?.diagnostics?.warnings || []).length && !administrationWarnings.length ? <Empty message="No platform warnings are active." /> : null}</div>
      </AdministrationPanel> : null}

      {section === 'security' ? <AdministrationPanel title="Security Controls" health={String(context.user.role || '').toLowerCase().includes('admin') ? 'Healthy' : 'Restricted'} validation="Administrative role required" diagnostics="Secrets are represented by references only" updatedAt={connection?.lastValidatedAt || lastUpdated}>
        <div className="hei-settings-grid"><Group title="Identity"><Item label="User" value={context.user.name} /><Item label="Role" value={context.user.role} /><Item label="Host" value={context.hostType} /><Item label="Project Boundary" value={context.project.name} /></Group><Group title="Credential Policy"><Item label="Authentication" value={connection?.authenticationMode || 'Not configured'} /><Item label="Credential Storage" value={connection?.credentialConfigured ? 'Secure reference configured' : 'Credential reference pending'} /><Item label="Credential Reference" value={secretReference || 'Not configured'} /><Item label="PAT Exposure" value="Never returned to the client" /></Group></div>
        <div className="hei-administration-policy-list">{(agentPolicies?.policies || []).map((policy) => <p key={policy}>{policy}</p>)}</div>
      </AdministrationPanel> : null}

      {section === 'audit' ? <AdministrationPanel title="Audit Logs" health="Available" validation="Append-only event history" diagnostics={`${auditEvents.length} recent events loaded`} updatedAt={auditEvents[0]?.timestamp || lastUpdated}>
        <div className="hei-administration-audit-list">{auditEvents.map((event) => <article key={event.event_id || `${event.event_type}-${event.timestamp}`}><div><strong>{humanize(event.event_type || 'Platform Event')}</strong><Status value={event.stage || 'Recorded'} /></div><p>{event.pipeline_id || 'Platform-wide event'} · {event.actor || 'system'}</p><span>{formatDate(event.timestamp || '')}</span></article>)}{!auditEvents.length ? <Empty message="No audit records have been captured yet." /> : null}</div>
      </AdministrationPanel> : null}

      {section === 'host' ? <AdministrationPanel title="Host Configuration" health="Healthy" validation="Azure DevOps extension context loaded" diagnostics={context.correlationId} updatedAt={lastUpdated}>
        <div className="hei-settings-grid"><Group title="Azure DevOps Context"><Item label="Organization" value={context.organization.name} /><Item label="Project" value={context.project.name} /><Item label="Team" value={context.team.name} /><Item label="Sprint" value={context.sprint.name || context.sprint.path} /></Group><Group title="Extension Host"><Item label="Host" value={context.hostType} /><Item label="Theme" value={context.theme} /><Item label="Extension" value={`${context.extension.publisherId}.${context.extension.id}`} /><Item label="Version" value={context.extension.version} /></Group></div>
      </AdministrationPanel> : null}

      {section === 'feature-flags' ? <AdministrationPanel title="Feature Toggles" health="Controlled" validation="Changes apply to agent preparation only" diagnostics="Agents cannot bypass human approval" updatedAt={lastUpdated}>
        <div className="hei-feature-flag-list">{Object.entries(agentPolicies?.featureFlags || {}).map(([name, enabled]) => <label key={name}><span><strong>{humanize(name)}</strong><small>{enabled ? 'Agent preparation is enabled.' : 'Agent is disabled and will not accept new work.'}</small></span><input type="checkbox" checked={enabled} disabled={featureFlagBusy === name} onChange={(event) => void updateFeatureFlag(name, event.target.checked)} aria-label={`Enable ${humanize(name)}`} /></label>)}{!Object.keys(agentPolicies?.featureFlags || {}).length ? <Empty message="Feature flag configuration is unavailable." /> : null}</div>
      </AdministrationPanel> : null}
        </main>
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
function Status({ value }: { value: string }) {
  const normalized = String(value || 'Unknown').toLowerCase().replace(/[^a-z]/g, '');
  return <span className={`hei-administration-status status-${normalized}`}>{value || 'Unknown'}</span>;
}
function AdministrationPanel({ title, health, validation, diagnostics, updatedAt, children }: {
  title: string; health: string; validation: string; diagnostics: string; updatedAt: string; children: React.ReactNode;
}) {
  return <section className="hei-administration-panel">
    <div className="hei-administration-summary">
      <div><span>Health</span><Status value={health} /></div>
      <div><span>Configuration</span><strong>{title}</strong></div>
      <div><span>Validation</span><strong>{validation}</strong></div>
      <div><span>Diagnostics</span><strong>{diagnostics}</strong></div>
      <div><span>Last Updated</span><strong>{formatDate(updatedAt)}</strong></div>
    </div>
    {children}
  </section>;
}
function Integration({ name, status, detail }: { name: string; status: string; detail: string }) {
  return <article className="hei-administration-card"><div><h4>{name}</h4><Status value={status} /></div><p>{detail}</p><Item label="Validation" value={status} /><Item label="Diagnostics" value={status.toLowerCase().includes('connect') || status.toLowerCase().includes('managed') ? 'No active issue' : 'Configuration required'} /></article>;
}
function Empty({ message }: { message: string }) { return <div className="hei-administration-empty">{message}</div>; }
function formatDate(value: string): string {
  if (!value || value === 'Not recorded') return 'Not recorded';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}
function humanize(value: string): string {
  return String(value || '').replace(/[_-]+/g, ' ').replace(/([a-z])([A-Z])/g, '$1 $2').replace(/\b\w/g, (letter) => letter.toUpperCase());
}
