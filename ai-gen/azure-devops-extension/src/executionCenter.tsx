import React, { useEffect, useMemo, useState } from 'react';
import './styles.css';

type Stage = { stage: string; status: string; startTime: string; endTime: string; durationMs: number; detail: string; logs: Array<{ event: string; at: string }>; diagnostics: Record<string, unknown>; responsibleAgent: string; correlationId: string; retryable: boolean };
type Artifact = { id: string; status: string; generatedAt?: string; version?: string };
type ExecutionItem = {
  id: string;
  title: string;
  sourceArtifact: { id: string; type: string; title: string };
  status: string;
  currentStage: string;
  executionStatus: string;
  package: Artifact;
  plan: Artifact;
  prompt: Artifact;
  provider: { name: string; model: string };
  runtime: { sessionId: string; status: string; startedAt: string; completedAt: string; duration: number; recoverable: boolean; attempt: number };
  validation: { id: string; status: string; summary: string };
  qa: { id: string; status: string; summary: string };
  memory: { status: string; count: number };
  prCandidate: { id: string; status: string; summary: string };
  executionDetails: {
    promptUsed: { id: string; sections: Array<Record<string, unknown>>; warnings: string[] };
    provider: string; model: string; filesChanged: Array<Record<string, unknown> | string>;
    validationScore?: number; qaSummary: string; prSummary: string; memoryCandidate: Record<string, unknown>;
  };
  timeline: Stage[];
  lineage: Record<string, string>;
  correlationId: string;
  warnings: string[];
  updatedAt: string;
};

type ExecutionResponse = {
  summary: { total: number; inProgress: number; completed: number; failed: number; cancelled: number; pendingValidation: number; pendingQA: number; memoryCandidates: number };
  items: ExecutionItem[];
  filters: { statuses: string[]; providers: string[] };
};

export function ExecutionCenter({ baseUrl, onError }: { baseUrl: string; onError: (message: string) => void }) {
  const [data, setData] = useState<ExecutionResponse>();
  const [selectedId, setSelectedId] = useState('');
  const [compareId, setCompareId] = useState('');
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [provider, setProvider] = useState('');
  const [loading, setLoading] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [panel, setPanel] = useState<'none' | 'runtime' | 'diagnostics' | 'compare'>('none');
  const [diagnostics, setDiagnostics] = useState<Record<string, unknown>>();

  useEffect(() => { void load(); }, []);
  const selected = data?.items.find((item) => item.id === selectedId) || data?.items[0];
  const comparison = data?.items.find((item) => item.id === compareId);
  const visible = useMemo(() => {
    const query = search.trim().toLowerCase();
    return (data?.items || []).filter((item) =>
      (!query || `${item.title} ${item.id} ${item.sourceArtifact.title}`.toLowerCase().includes(query))
      && (!status || item.status === status)
      && (!provider || item.provider.name === provider));
  }, [data, search, status, provider]);

  async function load(preferredId?: string) {
    setLoading(true);
    try {
      const response = await fetch(`${baseUrl}/execution?limit=250`);
      const payload = await response.json() as ExecutionResponse & { error?: { message?: string } };
      if (!response.ok) throw new Error(payload.error?.message || `Execution Center returned HTTP ${response.status}`);
      setData(payload);
      setSelectedId((current) => preferredId || (payload.items.some((item) => item.id === current) ? current : payload.items[0]?.id || ''));
    } catch (error) {
      onError(message(error, 'Unable to load engineering executions.'));
    } finally {
      setLoading(false);
    }
  }

  async function showDiagnostics() {
    if (!selected) return;
    try {
      const response = await fetch(`${baseUrl}/execution/${encodeURIComponent(selected.id)}/diagnostics`);
      const payload = await response.json() as Record<string, unknown> & { error?: { message?: string } };
      if (!response.ok) throw new Error(payload.error?.message || `Execution diagnostics returned HTTP ${response.status}`);
      setDiagnostics(payload); setPanel('diagnostics');
    } catch (error) { onError(message(error, 'Unable to load execution diagnostics.')); }
  }

  async function retry() {
    if (!selected) return;
    setRetrying(true);
    try {
      const response = await fetch(`${baseUrl}/execution/${encodeURIComponent(selected.id)}/retry`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ reason: 'Retried from Execution Center.' }),
      });
      const payload = await response.json() as { error?: { message?: string } };
      if (!response.ok) throw new Error(payload.error?.message || `Execution retry returned HTTP ${response.status}`);
      await load(selected.id); setPanel('runtime');
    } catch (error) { onError(message(error, 'Execution could not be retried.')); }
    finally { setRetrying(false); }
  }

  function compare() {
    if (!selected || !data) return;
    const candidate = data.items.find((item) => item.id !== selected.id);
    setCompareId((current) => current && current !== selected.id ? current : candidate?.id || '');
    setPanel('compare');
  }

  return (
    <section className="hei-execution-center" aria-label="Execution Center">
      <header className="hei-execution-titlebar">
        <div><span>Engineering Execution</span><h2>Execution Center</h2><p>Trace every package from approved planning through runtime, validation, QA, and memory.</p></div>
        <div><Status value={selected?.status || (loading ? 'Loading' : 'No Executions')} /><button className="planner-button secondary" type="button" onClick={() => void load()} disabled={loading}>Refresh</button></div>
      </header>

      <div className="hei-execution-metrics">
        <Metric label="Executions" value={data?.summary.total || 0} />
        <Metric label="In Progress" value={data?.summary.inProgress || 0} />
        <Metric label="Completed" value={data?.summary.completed || 0} />
        <Metric label="Failed" value={data?.summary.failed || 0} tone="danger" />
        <Metric label="Validation Pending" value={data?.summary.pendingValidation || 0} />
        <Metric label="QA Pending" value={data?.summary.pendingQA || 0} />
        <Metric label="Memory Candidates" value={data?.summary.memoryCandidates || 0} />
      </div>

      {!data?.items.length ? <Empty loading={loading} /> : (
        <div className="hei-execution-layout">
          <aside className="hei-execution-queue">
            <div className="hei-execution-filters">
              <label><span>Search</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Execution or work item" /></label>
              <label><span>Status</span><select value={status} onChange={(event) => setStatus(event.target.value)}><option value="">All</option>{data.filters.statuses.map((value) => <option key={value}>{value}</option>)}</select></label>
              <label><span>Provider</span><select value={provider} onChange={(event) => setProvider(event.target.value)}><option value="">All</option>{data.filters.providers.map((value) => <option key={value}>{value}</option>)}</select></label>
            </div>
            <div role="list">
              {visible.map((item) => <button key={item.id} type="button" role="listitem" className={item.id === selected?.id ? 'selected' : ''} onClick={() => { setSelectedId(item.id); setPanel('none'); }}>
                <div><strong>{item.title}</strong><Status value={item.status} /></div>
                <span>{item.sourceArtifact.type} {item.sourceArtifact.id || 'not linked'}</span>
                <small>{item.currentStage} · {item.provider.name}</small>
              </button>)}
            </div>
          </aside>

          {selected ? <main className="hei-execution-details">
            <div className="hei-execution-heading"><div><span>{selected.sourceArtifact.type} {selected.sourceArtifact.id}</span><h3>{selected.title}</h3><p>{selected.id} · {selected.correlationId || 'Correlation pending'}</p></div><Status value={selected.executionStatus} /></div>
            <section className="hei-execution-lifecycle" aria-label="Execution lifecycle timeline">
              <div className="hei-execution-section-heading"><div><span>Execution Timeline</span><h4>Planning to PR Intelligence</h4></div><small>{selected.timeline.filter((stage) => stage.status === 'Completed').length} of {selected.timeline.length} stages complete</small></div>
              {selected.timeline.map((stage, index) => <StagePanel key={stage.stage} stage={stage} index={index + 1} onRetry={stage.retryable ? () => void retry() : undefined} retrying={retrying} />)}
            </section>

            <ExecutionDetails item={selected} />
            {selected.warnings.length ? <div className="hei-execution-warnings"><strong>Warnings</strong>{selected.warnings.map((warning) => <span key={warning}>{warning}</span>)}</div> : null}
            <div className="hei-execution-actions">
              <button className="planner-button primary" type="button" onClick={() => setPanel('none')}>Open</button>
              <button className="planner-button secondary" type="button" onClick={() => void retry()} disabled={!selected.runtime.recoverable || retrying}>{retrying ? 'Retrying...' : 'Retry'}</button>
              <button className="planner-button secondary" type="button" onClick={compare} disabled={data.items.length < 2}>Compare</button>
              <button className="planner-button secondary" type="button" onClick={() => void showDiagnostics()}>View Diagnostics</button>
              <button className="planner-button secondary" type="button" onClick={() => setPanel('runtime')} disabled={!selected.runtime.sessionId}>View Runtime</button>
            </div>
            {panel === 'runtime' ? <RuntimePanel item={selected} /> : null}
            {panel === 'diagnostics' && diagnostics ? <JsonPanel title="Execution Diagnostics" value={diagnostics} /> : null}
            {panel === 'compare' ? <ComparePanel current={selected} comparison={comparison} choices={data.items.filter((item) => item.id !== selected.id)} onChange={setCompareId} /> : null}
          </main> : null}
        </div>
      )}
    </section>
  );
}

function Metric({ label, value, tone = '' }: { label: string; value: number; tone?: string }) { return <div className={tone}><span>{label}</span><strong>{value}</strong></div>; }
function Status({ value }: { value: string }) { return <span className={`hei-execution-status status-${slug(value)}`}>{value}</span>; }
function Empty({ loading }: { loading: boolean }) { return <div className="hei-execution-empty"><strong>{loading ? 'Loading engineering executions...' : 'No executions available.'}</strong><span>{loading ? 'Joining packages, runtime sessions, validation, QA, and memory.' : 'Build an Execution Package from an approved Story or Task to begin.'}</span></div>; }
function RuntimePanel({ item }: { item: ExecutionItem }) { return <section className="hei-execution-expanded"><div><strong>AI Runtime</strong><Status value={item.runtime.status} /></div><div className="hei-execution-runtime-grid"><Info label="Session" value={item.runtime.sessionId} /><Info label="Provider" value={`${item.provider.name} · ${item.provider.model}`} /><Info label="Started" value={item.runtime.startedAt || 'Not started'} /><Info label="Completed" value={item.runtime.completedAt || 'In progress'} /><Info label="Duration" value={`${item.runtime.duration || 0} ms`} /><Info label="Attempt" value={String(item.runtime.attempt || 0)} /></div></section>; }
function ComparePanel({ current, comparison, choices, onChange }: { current: ExecutionItem; comparison?: ExecutionItem; choices: ExecutionItem[]; onChange: (id: string) => void }) { return <section className="hei-execution-expanded"><div><strong>Compare Executions</strong><select value={comparison?.id || ''} onChange={(event) => onChange(event.target.value)}><option value="">Select execution</option>{choices.map((item) => <option key={item.id} value={item.id}>{item.title} · {item.id}</option>)}</select></div>{comparison ? <div className="hei-execution-compare"><ComparisonColumn item={current} /><ComparisonColumn item={comparison} /></div> : <p>Select another execution to compare lifecycle state, provider, lineage, and artifacts.</p>}</section>; }
function ComparisonColumn({ item }: { item: ExecutionItem }) { return <div><strong>{item.title}</strong><Info label="Status" value={item.status} /><Info label="Current Stage" value={item.currentStage} /><Info label="Provider" value={`${item.provider.name} · ${item.provider.model}`} /><Info label="Package" value={item.package.id || 'Missing'} /><Info label="Runtime" value={item.runtime.status} /><Info label="Warnings" value={String(item.warnings.length)} /></div>; }
function JsonPanel({ title, value }: { title: string; value: Record<string, unknown> }) { return <section className="hei-execution-expanded"><div><strong>{title}</strong></div><pre>{JSON.stringify(value, null, 2)}</pre></section>; }
function Info({ label, value }: { label: string; value: string }) { return <div><span>{label}</span><strong>{value || '—'}</strong></div>; }
function StagePanel({ stage, index, onRetry, retrying }: { stage: Stage; index: number; onRetry?: () => void; retrying: boolean }) {
  const logs = stage.logs || [];
  return <details className={`hei-execution-stage stage-${slug(stage.status)}`} open={stage.status === 'Failed' || stage.status === 'Active'}>
    <summary><i aria-hidden="true">{index}</i><span><strong>{stage.stage}</strong><small>{stage.detail}</small></span><Status value={stage.status} /></summary>
    <div className="hei-execution-stage-body">
      <div className="hei-execution-stage-facts">
        <Info label="Start Time" value={formatTime(stage.startTime)} /><Info label="End Time" value={formatTime(stage.endTime)} />
        <Info label="Duration" value={formatDuration(stage.durationMs)} /><Info label="Responsible Agent" value={stage.responsibleAgent} />
        <Info label="Correlation ID" value={stage.correlationId || 'Not assigned'} />
      </div>
      {stage.status === 'Failed' || stage.status === 'Cancelled' ? <div className="hei-stage-failure"><strong>{stage.stage} {stage.status.toLowerCase()}</strong><span>{stage.detail}</span></div> : null}
      <div className="hei-execution-stage-evidence">
        <section><strong>Logs</strong>{logs.length ? logs.map((log, logIndex) => <div key={`${log.event}-${logIndex}`}><span>{log.event}</span><small>{formatTime(log.at)}</small></div>) : <p>No lifecycle logs recorded for this stage.</p>}</section>
        <details><summary>Diagnostics</summary><pre>{JSON.stringify(stage.diagnostics || {}, null, 2)}</pre></details>
      </div>
      {onRetry ? <button className="planner-button secondary" type="button" onClick={onRetry} disabled={retrying}>{retrying ? 'Retrying...' : `Retry ${stage.stage}`}</button> : null}
    </div>
  </details>;
}
function ExecutionDetails({ item }: { item: ExecutionItem }) {
  const details = item.executionDetails || { promptUsed: { id: item.prompt.id, sections: [], warnings: [] }, provider: item.provider.name, model: item.provider.model, filesChanged: [], validationScore: undefined, qaSummary: '', prSummary: '', memoryCandidate: {} };
  return <section className="hei-execution-detail-section"><div className="hei-execution-section-heading"><div><span>Execution Details</span><h4>Engineering outcome</h4></div></div><div className="hei-execution-detail-grid">
    <details><summary><span>Prompt Used</span><strong>{details.promptUsed.id || 'Not generated'}</strong></summary><pre>{details.promptUsed.sections.length ? JSON.stringify(details.promptUsed.sections, null, 2) : 'Prompt sections are not available.'}</pre></details>
    <DetailCard title="Provider" value={details.provider || item.provider.name || 'Not selected'} detail={details.model || item.provider.model || 'Model not selected'} />
    <details><summary><span>Files Changed</span><strong>{details.filesChanged.length}</strong></summary>{details.filesChanged.length ? <ul>{details.filesChanged.map((file, index) => <li key={index}>{typeof file === 'string' ? file : String(file.path || file.file || file.name || 'Changed file')}</li>)}</ul> : <p>No changed files have been reported.</p>}</details>
    <DetailCard title="Validation Score" value={details.validationScore == null ? 'Not available' : `${details.validationScore}%`} detail={item.validation.summary || item.validation.status} />
    <DetailCard title="QA Summary" value={item.qa.status} detail={details.qaSummary || item.qa.summary || 'QA has not produced a summary.'} />
    <DetailCard title="Generated PR Summary" value={item.prCandidate.status} detail={details.prSummary || item.prCandidate.summary || 'PR Intelligence has not generated a summary.'} />
    <DetailCard title="Memory Candidate" value={item.memory.status} detail={objectLabel(details.memoryCandidate, `${item.memory.count} candidate(s)`)} />
    <DetailCard title="Execution Package" value={item.package.status} detail={`${item.package.id || 'Not built'}${item.package.version ? ` · v${item.package.version}` : ''}`} />
  </div></section>;
}
function DetailCard({ title, value, detail }: { title: string; value: string; detail: string }) { return <article><span>{title}</span><strong>{value}</strong><p>{detail}</p></article>; }
function objectLabel(value: Record<string, unknown>, fallback: string) { return String(value.title || value.summary || value.suggestedCategory || value.candidateId || fallback); }
function formatTime(value: string) { if (!value) return 'Not recorded'; const date = new Date(value); return Number.isNaN(date.valueOf()) ? value : date.toLocaleString(); }
function formatDuration(value: number) { if (!value) return 'Not recorded'; if (value < 1000) return `${value} ms`; const seconds = Math.round(value / 100) / 10; return seconds < 60 ? `${seconds} sec` : `${Math.floor(seconds / 60)} min ${Math.round(seconds % 60)} sec`; }
function slug(value: string): string { return value.toLowerCase().replace(/[^a-z]+/g, '-').replace(/^-|-$/g, ''); }
function message(error: unknown, fallback: string): string { return error instanceof Error ? error.message : fallback; }
