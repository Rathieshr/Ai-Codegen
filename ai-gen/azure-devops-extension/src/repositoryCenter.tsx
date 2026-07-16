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
  metadata?: { sourceRoots?: string[]; folders?: string[]; files?: Array<{ path?: string }>; rootFiles?: string[] };
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
  services: Array<Record<string, unknown>>;
  apis: Array<Record<string, unknown>>;
  tests: Array<Record<string, unknown>>;
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
      const endpoint = snapshot ? 'incremental-scan' : 'scan';
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
                    <Signal label="Snapshot" value={health.snapshotId ? `v${health.snapshotVersion}` : 'Pending'} status={health.snapshotCreatedAt || 'No completed snapshot'} />
                    <Signal label="Sync Status" value={health.syncStatus} status={health.pendingScanCount ? `${health.pendingScanCount} pending` : 'No pending sync'} />
                    <Signal label="Engineering Graph" value={health.engineeringGraphStatus} status={`${health.engineeringGraph.nodeCount || 0} nodes`} />
                  </div>
                  <div className="hei-repository-metrics">
                    <Metric label="Modules" value={health.modulesIndexed || health.engineeringGraph.counts?.Module || 0} />
                    <Metric label="Services" value={health.engineeringGraph.counts?.Service || health.services.length} />
                    <Metric label="Files Indexed" value={health.filesIndexed || 0} />
                    <Metric label="Symbols" value={health.symbolsIndexed || 0} />
                    <Metric label="Tests" value={health.engineeringGraph.counts?.Test || health.tests.length} />
                    <Metric label="APIs" value={health.engineeringGraph.counts?.API || health.apis.length} />
                    <Metric label="Background Jobs" value={health.backgroundJobSummary.total || 0} />
                    <Metric label="Health" value={health.health} />
                  </div>
                  {health.warnings?.length ? <div className="hei-repository-warning">{health.warnings.map((warning) => <span key={warning}>{warning}</span>)}</div> : null}
                  <div className="hei-repository-actions">
                    <button className="planner-button primary" type="button" onClick={() => void syncRepository()} disabled={!canManage || syncing}>{syncing ? 'Synchronizing...' : 'Sync'}</button>
                    <button className="planner-button secondary" type="button" onClick={() => void loadRepository(selected.repositoryId)} disabled={loading}>Refresh</button>
                    <button className="planner-button secondary" type="button" onClick={() => setSnapshotOpen((value) => !value)} disabled={!snapshot}>View Snapshot</button>
                    <button className="planner-button secondary" type="button" onClick={() => window.open(selected.url, '_blank', 'noopener,noreferrer')} disabled={!selected.url}>Open Repository</button>
                    <button className="planner-button secondary" type="button" onClick={() => setDiagnosticsOpen((value) => !value)}>View Diagnostics</button>
                  </div>
                  <div className="hei-repository-content-grid">
                    <EntityList title="Source Roots" items={health.sourceRoots || health.modules} empty="No source folders indexed." />
                    <EntityList title="Services" items={health.services.map(nameOf)} empty="No services identified." />
                    <EntityList title="APIs" items={health.apis.map(nameOf)} empty="No APIs identified." />
                    <EntityList title="Tests" items={health.tests.map(nameOf)} empty="No tests identified." />
                  </div>
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
function EntityList({ title, items, empty, limit = 12 }: { title: string; items: string[]; empty: string; limit?: number }) { const visible = items.slice(0, limit); return <section><strong>{title}{items.length ? ` (${items.length})` : ''}</strong>{items.length ? <><ul>{visible.map((item) => <li key={item}>{item}</li>)}</ul>{items.length > visible.length ? <small>{items.length - visible.length} more available in this snapshot.</small> : null}</> : <p>{empty}</p>}</section>; }
function SnapshotPanel({ snapshot }: { snapshot: RepositorySnapshot }) { const metadata = snapshot.metadata || {}; const files = (metadata.files || []).map((item) => String(item.path || '')).filter(Boolean); return <section className="hei-repository-expanded"><div><strong>Snapshot {snapshot.snapshotId}</strong><RepositoryStatus value={snapshot.status} /></div><div className="hei-repository-snapshot-grid"><Signal label="Version" value={`v${snapshot.version}`} status={snapshot.scanMode} /><Signal label="Branch" value={snapshot.branch} status={snapshot.commitId || 'Commit not recorded'} /><Signal label="Files" value={String(snapshot.totalFiles)} status={`${Object.keys(snapshot.languages || {}).length} languages`} /><Signal label="Created" value={snapshot.createdAt || 'Not recorded'} status="Snapshot timestamp" /></div><div className="hei-repository-diagnostic-lists"><EntityList title="Languages" items={Object.entries(snapshot.languages || {}).map(([name, count]) => `${name}: ${count}`)} empty="No language summary." /><EntityList title="Source Folders" items={metadata.sourceRoots || snapshot.modules || []} empty="No source folders indexed." /><EntityList title="Indexed Files" items={files} empty="No files indexed." limit={40} /></div></section>; }
function DiagnosticsPanel({ health }: { health: RepositoryHealth }) { return <section className="hei-repository-expanded"><div><strong>Repository Diagnostics</strong><RepositoryStatus value={health.availability} /></div><div className="hei-repository-snapshot-grid"><Signal label="Scan Duration" value={`${health.scanDurationMs || 0} ms`} status="Latest synchronization" /><Signal label="Graph Relationships" value={String(health.engineeringGraph.relationshipCount || 0)} status="Indexed relationships" /><Signal label="Pending Jobs" value={String(health.backgroundJobSummary.pending || 0)} status={`${health.backgroundJobSummary.failed || 0} failed`} /><Signal label="Agent" value={String(health.agentStatus?.status || 'Idle')} status="Repository agent" /></div><div className="hei-repository-diagnostic-lists"><EntityList title="Symbol Types" items={Object.entries(health.symbolCounts || {}).map(([name, count]) => `${name}: ${count}`)} empty="No symbols indexed." /><EntityList title="Background Jobs" items={(health.backgroundJobs || []).map((job) => `${String(job.jobType || job.type || job.jobId || 'Repository job')}: ${String(job.status || 'Pending')}`)} empty="No repository jobs recorded." /></div></section>; }
function nameOf(item: Record<string, unknown>): string { return String(item.name || item.path || item.nodeId || 'Unnamed repository item'); }
function message(error: unknown, fallback: string): string { return error instanceof Error ? error.message : fallback; }
