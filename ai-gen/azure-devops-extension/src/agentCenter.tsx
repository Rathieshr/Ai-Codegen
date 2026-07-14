import React, { useEffect, useMemo, useState } from 'react';

type LastRun = { status: string; at: string; id: string };
type AgentJob = {
  jobId: string; sourceType: string; title: string; status: string; currentStep: string; nextAction: string;
  createdAt: string; completedAt: string; durationMs?: number; retryCount: number; error: string;
  retryable: boolean; correlationId: string;
};
type RuntimeRun = { runId: string; status: string; startedAt: string; completedAt: string; durationMs?: number; error: string; correlationId: string };
type Agent = {
  agentId: string; name: string; responsibility: string; enabled: boolean; status: string; health: string;
  queue: number; jobCount: number; runtimeCount: number; failures: number; successRate?: number;
  averageDurationMs: number; lastRun: LastRun; nextRun: string; triggers: string[]; actions: string[];
  checkpoint: string; warnings: string[]; jobs?: AgentJob[]; runtimeRuns?: RuntimeRun[];
  logs?: Array<Record<string, unknown>>; diagnostics?: Record<string, unknown>;
};
type AgentCenterResponse = {
  agents: Agent[];
  summary: { total: number; enabled: number; running: number; queued: number; failed: number; disabled: number; pendingJobs: number; totalJobs: number };
  policyMode: string;
};

export function AgentCenter({
  baseUrl, canRetry, onOpenActivity, onError,
}: {
  baseUrl: string;
  canRetry: boolean;
  onOpenActivity: () => void;
  onError?: (message: string) => void;
}) {
  const [response, setResponse] = useState<AgentCenterResponse>();
  const [selectedId, setSelectedId] = useState('');
  const [selected, setSelected] = useState<Agent>();
  const [view, setView] = useState<'details' | 'jobs' | 'runtime' | 'logs'>('details');
  const [search, setSearch] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => { void load(); }, [baseUrl]);
  useEffect(() => { if (selectedId) void loadDetails(selectedId); }, [selectedId]);

  const agents = useMemo(() => {
    const query = search.trim().toLowerCase();
    return (response?.agents || []).filter((agent) => !query || `${agent.name} ${agent.status} ${agent.health} ${agent.responsibility}`.toLowerCase().includes(query));
  }, [response, search]);

  async function load() {
    setBusy(true);
    try {
      const value = await request<AgentCenterResponse>(`${baseUrl}/agents`);
      setResponse(value);
      if (selectedId && !value.agents.some((agent) => agent.agentId === selectedId)) { setSelectedId(''); setSelected(undefined); }
    } catch (error) { onError?.(message(error)); }
    finally { setBusy(false); }
  }

  async function loadDetails(agentId: string, targetView?: typeof view) {
    setBusy(true);
    try { setSelected(await request<Agent>(`${baseUrl}/agents/${encodeURIComponent(agentId)}`)); if (targetView) setView(targetView); }
    catch (error) { onError?.(message(error)); }
    finally { setBusy(false); }
  }

  async function retry(job: AgentJob) {
    setBusy(true);
    try {
      await request(`${baseUrl}/agents/jobs/${encodeURIComponent(job.jobId)}/retry`, { method: 'POST' });
      await load(); await loadDetails(selectedId, 'jobs');
    } catch (error) { onError?.(message(error)); }
    finally { setBusy(false); }
  }

  function open(agentId: string, targetView: typeof view = 'details') {
    setSelectedId(agentId); setView(targetView);
    if (agentId === selectedId) void loadDetails(agentId, targetView);
  }

  return (
    <section className="agent-center" aria-label="Agent Center">
      <header className="agent-center-header">
        <div><span className="hei-eyebrow">Agent Runtime</span><h2>Agent Center</h2><p>See what every HEI agent is doing, why it is waiting, and where intervention is required.</p></div>
        <div><span className="agent-policy">Humans approve</span><button type="button" onClick={() => void load()} disabled={busy}>{busy ? 'Refreshing...' : 'Refresh'}</button></div>
      </header>

      <div className="agent-summary">
        <Summary label="Agents" value={response?.summary.total || 0} detail={`${response?.summary.enabled || 0} enabled`} />
        <Summary label="Running" value={response?.summary.running || 0} detail="Active now" tone="running" />
        <Summary label="Queue" value={response?.summary.pendingJobs || 0} detail="Waiting or queued" tone="queued" />
        <Summary label="Jobs" value={response?.summary.totalJobs || 0} detail="Recorded workflows" />
        <Summary label="Failures" value={response?.summary.failed || 0} detail="Agents requiring review" tone="failed" />
        <Summary label="Disabled" value={response?.summary.disabled || 0} detail="Feature flag off" />
      </div>

      <div className="agent-toolbar"><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search agents" aria-label="Search agents" /><button type="button" onClick={onOpenActivity}>Open Activity</button></div>

      <div className="agent-card-grid">
        {agents.map((agent) => <article className={`agent-card ${selectedId === agent.agentId ? 'selected' : ''}`} key={agent.agentId}>
          <div className="agent-card-heading"><div><span>{agent.agentId}</span><h3>{agent.name}</h3></div><AgentStatus value={agent.status} /></div>
          <p>{agent.responsibility}</p>
          <div className="agent-signals">
            <Signal label="Health" value={agent.health} /><Signal label="Queue" value={agent.queue} />
            <Signal label="Jobs" value={agent.jobCount} /><Signal label="Runtime" value={agent.runtimeCount} />
            <Signal label="Failures" value={agent.failures} /><Signal label="Success Rate" value={agent.successRate == null ? 'Not measured' : `${agent.successRate}%`} />
            <Signal label="Duration" value={duration(agent.averageDurationMs)} /><Signal label="Next Run" value={agent.nextRun ? formatDate(agent.nextRun) : 'Not scheduled'} />
          </div>
          <div className="agent-card-actions"><button type="button" onClick={() => open(agent.agentId)}>View Details</button><button type="button" onClick={() => open(agent.agentId, 'logs')}>View Logs</button></div>
        </article>)}
        {!agents.length ? <Empty title="No agents found" detail="Registered HEI agents will appear here." /> : null}
      </div>

      {selected ? <section className="agent-detail">
        <header><div><span>Agent Details</span><h3>{selected.name}</h3></div><div><AgentStatus value={selected.status} /><button type="button" onClick={() => { setSelectedId(''); setSelected(undefined); }}>Close</button></div></header>
        <nav>{(['details', 'jobs', 'runtime', 'logs'] as const).map((item) => <button key={item} type="button" className={view === item ? 'active' : ''} onClick={() => setView(item)}>{title(item)}</button>)}</nav>
        {view === 'details' ? <AgentDetails agent={selected} /> : null}
        {view === 'jobs' ? <JobList jobs={selected.jobs || []} canRetry={canRetry} busy={busy} onRetry={retry} /> : null}
        {view === 'runtime' ? <RuntimeList runs={selected.runtimeRuns || []} /> : null}
        {view === 'logs' ? <LogList logs={selected.logs || []} onOpenActivity={onOpenActivity} /> : null}
      </section> : null}
    </section>
  );
}

function AgentDetails({ agent }: { agent: Agent }) { return <div className="agent-detail-grid">
  <section><h4>Runtime</h4><dl><Data label="Status" value={agent.status} /><Data label="Health" value={agent.health} /><Data label="Last Run" value={agent.lastRun.at ? formatDate(agent.lastRun.at) : 'Never run'} /><Data label="Next Run" value={agent.nextRun ? formatDate(agent.nextRun) : 'Not scheduled'} /><Data label="Average Duration" value={duration(agent.averageDurationMs)} /><Data label="Success Rate" value={agent.successRate == null ? 'Not measured' : `${agent.successRate}%`} /></dl></section>
  <section><h4>Approval Boundary</h4><p>{agent.checkpoint || 'Human review required before consequential action.'}</p><h4>Warnings</h4>{agent.warnings.length ? <ul>{agent.warnings.map((item) => <li key={item}>{item}</li>)}</ul> : <p>No active agent warnings.</p>}</section>
  <section><h4>Triggers</h4>{agent.triggers.length ? <ul>{agent.triggers.map((item) => <li key={item}>{item}</li>)}</ul> : <p>No triggers registered.</p>}</section>
  <section><h4>Prepared Actions</h4>{agent.actions.length ? <ul>{agent.actions.map((item) => <li key={item}>{item}</li>)}</ul> : <p>No actions registered.</p>}</section>
  <details><summary>Diagnostics</summary><pre>{JSON.stringify(agent.diagnostics || {}, null, 2)}</pre></details>
</div>; }

function JobList({ jobs, canRetry, busy, onRetry }: { jobs: AgentJob[]; canRetry: boolean; busy: boolean; onRetry: (job: AgentJob) => void }) { return <div className="agent-record-list">{jobs.length ? jobs.map((job) => <article key={`${job.sourceType}-${job.jobId}`}><AgentStatus value={job.status} /><div><strong>{job.title}</strong><span>{job.sourceType} · {job.currentStep || 'No current step'} · {job.createdAt ? formatDate(job.createdAt) : 'Time not recorded'}</span>{job.error ? <p>{job.error}</p> : null}</div>{job.retryable ? <button type="button" onClick={() => onRetry(job)} disabled={!canRetry || busy}>Retry Failed Job</button> : null}</article>) : <Empty title="No jobs recorded" detail="Queued and completed work for this agent will appear here." />}</div>; }
function RuntimeList({ runs }: { runs: RuntimeRun[] }) { return <div className="agent-record-list">{runs.length ? runs.map((run) => <article key={run.runId}><AgentStatus value={run.status} /><div><strong>{run.runId}</strong><span>{run.startedAt ? formatDate(run.startedAt) : 'Start not recorded'} · {duration(run.durationMs || 0)}</span>{run.error ? <p>{run.error}</p> : null}<small>Correlation: {run.correlationId || 'Not recorded'}</small></div></article>) : <Empty title="No runtime runs" detail="Agent runtime sessions will appear here after execution." />}</div>; }
function LogList({ logs, onOpenActivity }: { logs: Array<Record<string, unknown>>; onOpenActivity: () => void }) { return <div className="agent-record-list">{logs.length ? logs.map((log, index) => <article key={String(log.activityId || index)}><div><strong>{String(log.title || log.activityType || 'Agent activity')}</strong><span>{formatDate(String(log.createdAt || log.timestamp || ''))}</span><p>{String(log.description || '')}</p></div></article>) : <Empty title="No agent logs" detail="No matching activity records were found for this agent." />}<button type="button" onClick={onOpenActivity}>Open Activity</button></div>; }
function Summary({ label, value, detail, tone = '' }: { label: string; value: number; detail: string; tone?: string }) { return <div className={tone}><span>{label}</span><strong>{value}</strong><small>{detail}</small></div>; }
function Signal({ label, value }: { label: string; value: React.ReactNode }) { return <div><span>{label}</span><strong>{value}</strong></div>; }
function Data({ label, value }: { label: string; value: React.ReactNode }) { return <div><dt>{label}</dt><dd>{value}</dd></div>; }
function AgentStatus({ value }: { value: string }) { return <span className={`agent-status status-${value.toLowerCase().replace(/[^a-z]+/g, '-')}`}>{value}</span>; }
function Empty({ title: value, detail }: { title: string; detail: string }) { return <div className="agent-empty"><strong>{value}</strong><span>{detail}</span></div>; }
function duration(milliseconds: number) { if (!milliseconds) return 'Not measured'; if (milliseconds < 1000) return `${Math.round(milliseconds)} ms`; if (milliseconds < 60000) return `${(milliseconds / 1000).toFixed(1)} sec`; return `${(milliseconds / 60000).toFixed(1)} min`; }
function formatDate(value: string) { if (!value) return 'Not recorded'; const date = new Date(value); return Number.isNaN(date.getTime()) ? value : date.toLocaleString(); }
function title(value: string) { return value.charAt(0).toUpperCase() + value.slice(1); }
function message(error: unknown) { return error instanceof Error ? error.message : String(error); }
async function request<T = unknown>(url: string, init?: RequestInit): Promise<T> { const response = await fetch(url, init); const data = await response.json().catch(() => ({})); if (!response.ok) throw new Error(data?.error?.message || `Agent Center returned HTTP ${response.status}.`); return data as T; }
