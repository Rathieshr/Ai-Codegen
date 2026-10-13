import React, { useEffect, useMemo, useState } from 'react';
import './styles.css';

type RepositoryItem = {
  repositoryId: string;
  name: string;
  url: string;
  defaultBranch: string;
  repositoryType: string;
  status: string;
  latestSnapshotId: string;
  latestScanStatus: string;
  graphStatus: string;
};

type RepositorySnapshot = {
  snapshotId: string;
  version: number;
  createdAt: string;
  branch: string;
  commitId: string;
  totalFiles: number;
  languages: Record<string, number>;
  modules: string[];
  status: string;
  scanMode: string;
  metadata?: { sourceRoots?: string[]; folders?: string[]; files?: Array<{ path?: string }>; rootFiles?: string[]; documentationRegistry?: RepositoryDocumentation };
};

type RepositoryDocumentation = {
  status?: string;
  documentsDiscovered?: number;
  documentsIndexed?: number;
  sectionsIndexed?: number;
  statementsIndexed?: number;
  sourceFiles?: string[];
  classifications?: Record<string, number>;
  indexedAt?: string;
};

type RepositoryChange = { path: string; changeType: string };
type RepositorySync = {
  jobId: string;
  status: string;
  trigger: string;
  mode: string;
  requestedAt: string;
  completedAt: string;
  durationMs: number;
  error: string;
};

type RepositoryHealth = {
  repositoryId: string;
  repositoryName: string;
  repositoryStatus: string;
  availability: string;
  health: string;
  branch: string;
  snapshotId: string;
  snapshotVersion: number;
  snapshotCreatedAt: string;
  syncStatus: string;
  engineeringGraphStatus: string;
  filesIndexed: number;
  modulesIndexed: number;
  symbolsIndexed: number;
  scanDurationMs: number;
  pendingScanCount: number;
  engineeringGraph: { nodeCount: number; relationshipCount: number; counts: Record<string, number> };
  modules: string[];
  sourceRoots: string[];
  folders: string[];
  files: string[];
  rootFiles: string[];
  documentation: RepositoryDocumentation;
  services: Array<Record<string, unknown>>;
  controllers: Array<Record<string, unknown>>;
  repositories: Array<Record<string, unknown>>;
  apis: Array<Record<string, unknown>>;
  tests: Array<Record<string, unknown>>;
  entities: Array<Record<string, unknown>>;
  topModifiedFiles: RepositoryChange[];
  recentSnapshots: RepositorySnapshot[];
  syncHistory: RepositorySync[];
  symbolCounts: Record<string, number>;
  backgroundJobs: Array<Record<string, unknown>>;
  backgroundJobSummary: { total: number; pending: number; failed: number };
  warnings: string[];
  lastScan?: Record<string, unknown>;
  agentStatus?: Record<string, unknown>;
};

export function RepositoryCenter({
  baseUrl, preferredRepositoryId, actor, canManage, onError,
}: {
  baseUrl: string;
  preferredRepositoryId?: string;
  actor: string;
  canManage: boolean;
  onError: (message: string) => void;
}) {
  const [repositories, setRepositories] = useState<RepositoryItem[]>([]);
  const [selectedId, setSelectedId] = useState('');
  const [health, setHealth] = useState<RepositoryHealth>();
  const [snapshot, setSnapshot] = useState<RepositorySnapshot>();
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [snapshotOpen, setSnapshotOpen] = useState(false);
  const [diagnosticsOpen, setDiagnosticsOpen] = useState(false);

  useEffect(() => { void loadRepositories(); }, [preferredRepositoryId]);
  useEffect(() => { if (selectedId) void loadRepository(selectedId); }, [selectedId]);

  const selected = repositories.find((item) => item.repositoryId === selectedId);
  const visibleRepositories = useMemo(() => {
    const query = search.trim().toLowerCase();
    return repositories.filter((item) => !query || `${item.name} ${item.url} ${item.defaultBranch}`.toLowerCase().includes(query));
  }, [repositories, search]);

  async function loadRepositories() {
    setLoading(true);
    try {
      const response = await fetch(`${baseUrl}/repositories`);
      const payload = await response.json() as { repositories?: RepositoryItem[]; error?: string };
      if (!response.ok) throw new Error(payload.error || `Repository Center returned HTTP ${response.status}`);
      const items = payload.repositories || [];
      setRepositories(items);
      const preferred = items.find((item) => item.repositoryId === preferredRepositoryId)?.repositoryId;
      setSelectedId((current) => preferred || (items.some((item) => item.repositoryId === current) ? current : items[0]?.repositoryId || ''));
      if (!items.length) { setHealth(undefined); setSnapshot(undefined); }
    } catch (error) {
      onError(message(error, 'Unable to load repositories.'));
    } finally {
      setLoading(false);
    }
  }

  async function loadRepository(repositoryId: string) {
    setLoading(true);
    try {
      const [healthResponse, snapshotResponse] = await Promise.all([
        fetch(`${baseUrl}/repositories/${encodeURIComponent(repositoryId)}/health`),
        fetch(`${baseUrl}/repositories/${encodeURIComponent(repositoryId)}/snapshot`),
      ]);
      const healthPayload = await healthResponse.json() as RepositoryHealth & { error?: string };
      if (!healthResponse.ok) throw new Error(healthPayload.error || `Repository health returned HTTP ${healthResponse.status}`);
      setHealth(healthPayload);
      if (snapshotResponse.ok) setSnapshot(await snapshotResponse.json() as RepositorySnapshot);
      else setSnapshot(undefined);
    } catch (error) {
      setHealth(undefined); setSnapshot(undefined);
      onError(message(error, 'Unable to load repository state.'));
    } finally {
      setLoading(false);
    }
  }

  async function syncRepository() {
    if (!selected) return;
    setSyncing(true);
    try {
      // Remote ADO snapshots may predate recursive documentation discovery. A full
      // synchronization repairs those snapshots and rebuilds the Markdown registry.
      const endpoint = selected.repositoryType === 'AzureDevOps' || !snapshot ? 'scan' : 'incremental-scan';
      const response = await fetch(`${baseUrl}/repositories/${encodeURIComponent(selected.repositoryId)}/${endpoint}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: endpoint === 'scan' ? JSON.stringify({ mode: 'Full', requestedBy: actor }) : undefined,
      });
      const payload = await response.json() as { error?: string };
      if (!response.ok) throw new Error(payload.error || `Repository synchronization returned HTTP ${response.status}`);
      await loadRepositories();
      await loadRepository(selected.repositoryId);
    } catch (error) {
      onError(message(error, 'Repository synchronization failed.'));
    } finally {
      setSyncing(false);
    }
  }

  return (
    <section className="hei-repository-center" aria-label="Repository Center">
      <header className="hei-repository-titlebar">
        <div><span>Repository Intelligence</span><h2>Repository Center</h2><p>Snapshots, engineering structure, synchronization, and repository health.</p></div>
        <div><RepositoryStatus value={health?.health || (repositories.length ? 'Pending' : 'Not Connected')} /><button className="planner-button secondary" type="button" onClick={() => void loadRepositories()} disabled={loading}>Refresh</button></div>
      </header>

      {!repositories.length ? (
        <div className="hei-repository-empty"><strong>No repositories registered.</strong><span>Connect a repository in Administration to begin Repository Intelligence.</span></div>
      ) : (
        <>
          <div className="hei-repository-layout">
            <aside className="hei-repository-list">
              <label><span>Repositories</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search repositories" /></label>
              <div role="list">
                {visibleRepositories.map((item) => (
                  <button key={item.repositoryId} type="button" role="listitem" className={item.repositoryId === selectedId ? 'selected' : ''} onClick={() => setSelectedId(item.repositoryId)}>
                    <div><strong>{item.name}</strong><RepositoryStatus value={item.latestScanStatus || item.status} /></div>
                    <span>{item.defaultBranch} · {item.repositoryType}</span>
                    <small>{item.latestSnapshotId ? 'Snapshot available' : 'Snapshot pending'} · Graph {item.graphStatus}</small>
                  </button>
                ))}
              </div>
            </aside>

            <main className="hei-repository-details">
              {selected && health ? (
                <>
                  <div className="hei-repository-heading"><div><span>{selected.repositoryType}</span><h3>{selected.name}</h3><p>{selected.url}</p></div><RepositoryStatus value={health.availability} /></div>
                  <div className="hei-repository-signals">
                    <Signal label="Branch" value={health.branch || selected.defaultBranch} status="Current branch" />
                    <Signal label="Snapshot" value={health.snapshotId ? `v${health.snapshotVersion}` : 'Pending'} status={formatDate(health.snapshotCreatedAt, 'No completed snapshot')} />
                    <Signal label="Synchronization" value={health.syncStatus} status={health.pendingScanCount ? `${health.pendingScanCount} pending` : 'No pending synchronization'} />
                    <Signal label="Repository Health" value={health.health} status={health.availability} />
                  </div>
                  {health.warnings?.length ? <div className="hei-repository-warning">{health.warnings.map((warning) => <span key={warning}>{warning}</span>)}</div> : null}
                  <div className="hei-repository-actions">
                    <button className="planner-button primary" type="button" onClick={() => void syncRepository()} disabled={!canManage || syncing}>{syncing ? 'Synchronizing...' : 'Sync'}</button>
                    <button className="planner-button secondary" type="button" onClick={() => void loadRepository(selected.repositoryId)} disabled={loading}>Refresh</button>
                    <button className="planner-button secondary" type="button" onClick={() => setSnapshotOpen((value) => !value)} disabled={!snapshot}>View Snapshot</button>
                    <button className="planner-button secondary" type="button" onClick={() => window.open(selected.url, '_blank', 'noopener,noreferrer')} disabled={!selected.url}>Open Repository</button>
                    <button className="planner-button secondary" type="button" onClick={() => setDiagnosticsOpen((value) => !value)}>View Diagnostics</button>
                  </div>
                  <section className="hei-repository-structure" aria-label="Repository structure">
                    <div className="hei-repository-section-heading"><div><span>Engineering Structure</span><strong>Repository map</strong></div><small>Named items from the current snapshot and symbol index.</small></div>
                    <div className="hei-repository-structure-grid">
                      <StructureGroup title="Modules" items={health.modules.length ? health.modules : health.sourceRoots} empty="No modules identified." />
                      <StructureGroup title="Services" items={health.services.map(nameOf)} empty="No services identified." visual />
                      <StructureGroup title="Controllers" items={(health.controllers || []).map(nameOf)} empty="No controllers identified." />
                      <StructureGroup title="Repositories" items={(health.repositories || []).map(nameOf)} empty="No repository types identified." />
                      <StructureGroup title="APIs" items={health.apis.map(nameOf)} empty="No APIs identified." />
                      <StructureGroup title="Tests" items={health.tests.map(nameOf)} empty="No tests identified." />
                      <StructureGroup title="Entities" items={(health.entities || []).map(nameOf)} empty="No domain entities identified." />
                      <StructureGroup title="Documentation" items={health.documentation?.sourceFiles || []} empty="No Markdown documentation indexed." />
                    </div>
                  </section>
                  <div className="hei-repository-operational-grid">
                    <RepositoryHealthPanel health={health} />
                    <GraphStatusPanel health={health} />
                    <TopModifiedFiles items={health.topModifiedFiles || []} />
                    <RecentSnapshots items={health.recentSnapshots || []} currentId={health.snapshotId} />
                    <SyncHistory items={health.syncHistory || []} />
                    <BackgroundJobs items={health.backgroundJobs || []} summary={health.backgroundJobSummary} />
                  </div>
                  <details className="hei-repository-statistics">
                    <summary>Repository Statistics</summary>
                    <div className="hei-repository-metrics">
                      <Metric label="Files Indexed" value={health.filesIndexed || 0} />
                      <Metric label="Symbols" value={health.symbolsIndexed || 0} />
                      <Metric label="Modules" value={health.modulesIndexed || health.engineeringGraph.counts?.Module || 0} />
                      <Metric label="Services" value={health.engineeringGraph.counts?.Service || health.services.length} />
                      <Metric label="Controllers" value={health.engineeringGraph.counts?.Controller || health.controllers?.length || 0} />
                      <Metric label="APIs" value={health.engineeringGraph.counts?.API || health.apis.length} />
                      <Metric label="Tests" value={health.engineeringGraph.counts?.Test || health.tests.length} />
                      <Metric label="Languages" value={Object.keys(snapshot?.languages || {}).length} />
                      <Metric label="Markdown Documents" value={health.documentation?.documentsIndexed || 0} />
                      <Metric label="Markdown Discovered" value={health.documentation?.documentsDiscovered || health.documentation?.documentsIndexed || 0} />
                      <Metric label="Knowledge Sections" value={health.documentation?.sectionsIndexed || 0} />
                    </div>
                  </details>
                  {snapshotOpen && snapshot ? <SnapshotPanel snapshot={snapshot} /> : null}
                  {diagnosticsOpen ? <DiagnosticsPanel health={health} /> : null}
                </>
              ) : <div className="hei-repository-empty"><strong>{loading ? 'Loading repository state...' : 'Repository state is unavailable.'}</strong><span>{loading ? 'Reading the latest snapshot and graph.' : 'Refresh or review repository diagnostics.'}</span></div>}
            </main>
          </div>
        </>
      )}
    </section>
  );
}

function Signal({ label, value, status }: { label: string; value: string; status: string }) { return <div><span>{label}</span><strong>{value}</strong><small>{status}</small></div>; }
function Metric({ label, value }: { label: string; value: string | number }) { return <div><span>{label}</span><strong>{value}</strong></div>; }
function RepositoryStatus({ value }: { value: string }) { return <span className={`hei-repository-status status-${value.toLowerCase().replace(/[^a-z]+/g, '-')}`}>{value}</span>; }
function StructureGroup({ title, items, empty, visual = false }: { title: string; items: string[]; empty: string; visual?: boolean }) {
  const unique = Array.from(new Set(items.filter(Boolean))).slice(0, 10);
  return <section><div><strong>{title}</strong><span>{items.length}</span></div>{unique.length ? <ul className={visual ? 'visual' : ''}>{unique.map((item) => <li key={item}>{item}</li>)}</ul> : <p>{empty}</p>}</section>;
}
function RepositoryHealthPanel({ health }: { health: RepositoryHealth }) {
  const lastScan = health.lastScan || {};
  return <OperationalPanel title="Repository Health" status={health.health}><KeyValue label="Availability" value={health.availability} /><KeyValue label="Last synchronization" value={formatDate(String(lastScan.completedAt || lastScan.startedAt || ''))} /><KeyValue label="Duration" value={formatDuration(health.scanDurationMs)} /><KeyValue label="Warnings" value={health.warnings.length ? String(health.warnings.length) : 'None'} /></OperationalPanel>;
}
function GraphStatusPanel({ health }: { health: RepositoryHealth }) {
  return <OperationalPanel title="Engineering Graph Status" status={health.engineeringGraphStatus}><KeyValue label="Nodes indexed" value={String(health.engineeringGraph.nodeCount || 0)} /><KeyValue label="Relationships" value={String(health.engineeringGraph.relationshipCount || 0)} /><KeyValue label="Snapshot" value={health.snapshotId ? `v${health.snapshotVersion}` : 'Pending'} /><p className="hei-repository-note">Structure status only. Graph visualization is not enabled.</p></OperationalPanel>;
}
function TopModifiedFiles({ items }: { items: RepositoryChange[] }) {
  return <OperationalPanel title="Top Modified Files"><CompactList items={items.map((item) => ({ primary: item.path, secondary: item.changeType }))} empty="No file changes recorded in the current snapshot." /></OperationalPanel>;
}
function RecentSnapshots({ items, currentId }: { items: RepositorySnapshot[]; currentId: string }) {
  return <OperationalPanel title="Recent Snapshots"><CompactList items={items.slice(0, 5).map((item) => ({ primary: `v${item.version} · ${item.branch}`, secondary: `${formatDate(item.createdAt)}${item.snapshotId === currentId ? ' · Current' : ''}` }))} empty="No completed snapshots available." /></OperationalPanel>;
}
function SyncHistory({ items }: { items: RepositorySync[] }) {
  return <OperationalPanel title="Sync History"><CompactList items={items.slice(0, 5).map((item) => ({ primary: `${item.trigger} · ${item.mode || 'Full'}`, secondary: `${item.status} · ${formatDate(item.completedAt || item.requestedAt)}` }))} empty="No synchronization history recorded." /></OperationalPanel>;
}
function BackgroundJobs({ items, summary }: { items: Array<Record<string, unknown>>; summary: RepositoryHealth['backgroundJobSummary'] }) {
  return <OperationalPanel title="Background Jobs" status={summary.failed ? 'Needs Attention' : summary.pending ? 'In Progress' : 'Clear'}><CompactList items={items.slice(0, 5).map((item) => ({ primary: String(item.jobType || item.type || 'Repository synchronization'), secondary: `${String(item.status || 'Pending')} · ${formatDate(String(item.updatedAt || item.createdAt || ''))}` }))} empty="No background jobs recorded." /></OperationalPanel>;
}
function OperationalPanel({ title, status, children }: { title: string; status?: string; children: React.ReactNode }) { return <section className="hei-repository-operational-panel"><header><strong>{title}</strong>{status ? <RepositoryStatus value={status} /> : null}</header>{children}</section>; }
function KeyValue({ label, value }: { label: string; value: string }) { return <div className="hei-repository-key-value"><span>{label}</span><strong>{value}</strong></div>; }
function CompactList({ items, empty }: { items: Array<{ primary: string; secondary: string }>; empty: string }) { return items.length ? <ul className="hei-repository-compact-list">{items.map((item, index) => <li key={`${item.primary}-${index}`}><strong>{item.primary}</strong><span>{item.secondary}</span></li>)}</ul> : <p className="hei-repository-note">{empty}</p>; }
function EntityList({ title, items, empty, limit = 12 }: { title: string; items: string[]; empty: string; limit?: number }) { const visible = items.slice(0, limit); return <section><strong>{title}{items.length ? ` (${items.length})` : ''}</strong>{items.length ? <><ul>{visible.map((item) => <li key={item}>{item}</li>)}</ul>{items.length > visible.length ? <small>{items.length - visible.length} more available in this snapshot.</small> : null}</> : <p>{empty}</p>}</section>; }
function SnapshotPanel({ snapshot }: { snapshot: RepositorySnapshot }) { const metadata = snapshot.metadata || {}; const files = (metadata.files || []).map((item) => String(item.path || '')).filter(Boolean); return <section className="hei-repository-expanded"><div><strong>Snapshot {snapshot.snapshotId}</strong><RepositoryStatus value={snapshot.status} /></div><div className="hei-repository-snapshot-grid"><Signal label="Version" value={`v${snapshot.version}`} status={snapshot.scanMode} /><Signal label="Branch" value={snapshot.branch} status={snapshot.commitId || 'Commit not recorded'} /><Signal label="Files" value={String(snapshot.totalFiles)} status={`${Object.keys(snapshot.languages || {}).length} languages`} /><Signal label="Created" value={snapshot.createdAt || 'Not recorded'} status="Snapshot timestamp" /></div><div className="hei-repository-diagnostic-lists"><EntityList title="Languages" items={Object.entries(snapshot.languages || {}).map(([name, count]) => `${name}: ${count}`)} empty="No language summary." /><EntityList title="Source Folders" items={metadata.sourceRoots || snapshot.modules || []} empty="No source folders indexed." /><EntityList title="Indexed Files" items={files} empty="No files indexed." limit={40} /></div></section>; }
function DiagnosticsPanel({ health }: { health: RepositoryHealth }) { return <section className="hei-repository-expanded"><div><strong>Repository Diagnostics</strong><RepositoryStatus value={health.availability} /></div><div className="hei-repository-snapshot-grid"><Signal label="Scan Duration" value={`${health.scanDurationMs || 0} ms`} status="Latest synchronization" /><Signal label="Graph Relationships" value={String(health.engineeringGraph.relationshipCount || 0)} status="Indexed relationships" /><Signal label="Pending Jobs" value={String(health.backgroundJobSummary.pending || 0)} status={`${health.backgroundJobSummary.failed || 0} failed`} /><Signal label="Agent" value={String(health.agentStatus?.status || 'Idle')} status="Repository agent" /></div><div className="hei-repository-diagnostic-lists"><EntityList title="Symbol Types" items={Object.entries(health.symbolCounts || {}).map(([name, count]) => `${name}: ${count}`)} empty="No symbols indexed." /><EntityList title="Background Jobs" items={(health.backgroundJobs || []).map((job) => `${String(job.jobType || job.type || job.jobId || 'Repository job')}: ${String(job.status || 'Pending')}`)} empty="No repository jobs recorded." /></div></section>; }
function nameOf(item: Record<string, unknown>): string { return String(item.name || item.path || item.nodeId || 'Unnamed repository item'); }
function formatDate(value: string, fallback = 'Not recorded'): string { if (!value) return fallback; const date = new Date(value); return Number.isNaN(date.getTime()) ? value : date.toLocaleString(); }
function formatDuration(value: number): string { if (!value) return 'Not recorded'; return value < 1000 ? `${value} ms` : `${(value / 1000).toFixed(1)} s`; }
function message(error: unknown, fallback: string): string { return error instanceof Error ? error.message : fallback; }
