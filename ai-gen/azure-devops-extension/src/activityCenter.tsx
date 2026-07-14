import React, { useEffect, useMemo, useState } from 'react';

type Activity = {
  activityId: string; category: string; eventType: string; title: string; summary: string; status: string;
  source: string; sourceType: string; actor: string; artifactType: string; artifactId: string;
  correlationId: string; occurredAt: string; replayable: boolean; details: Record<string, unknown>;
};
type ActivityResponse = {
  activity: Activity[]; count: number; total: number; hasMore: boolean; categories: string[];
  summary: { total: number; needsAttention: number; correlations: number; categories: Record<string, number> };
};
type CorrelationTrace = { correlationId: string; activity: Activity[]; count: number; stages: string[]; startedAt: string; completedAt: string; status: string };

export function ActivityCenter({ baseUrl, onError }: { baseUrl: string; onError?: (message: string) => void }) {
  const [response, setResponse] = useState<ActivityResponse>();
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('');
  const [status, setStatus] = useState('');
  const [selected, setSelected] = useState<Activity>();
  const [trace, setTrace] = useState<CorrelationTrace>();
  const [replayMessage, setReplayMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [visibleCount, setVisibleCount] = useState(80);

  useEffect(() => { void load(); }, [baseUrl, category, status]);
  const visibleActivity = useMemo(() => (response?.activity || []).slice(0, visibleCount), [response, visibleCount]);
  const grouped = useMemo(() => groupByDay(visibleActivity), [visibleActivity]);

  async function load() {
    setBusy(true);
    try {
      const params = new URLSearchParams({ limit: '250' });
      if (search.trim()) params.set('search', search.trim());
      if (category) params.set('category', category);
      if (status) params.set('status', status);
      setResponse(await request<ActivityResponse>(`${baseUrl}/activity?${params.toString()}`)); setVisibleCount(80);
    } catch (error) { onError?.(message(error)); }
    finally { setBusy(false); }
  }

  async function openDetails(item: Activity) {
    setBusy(true); setTrace(undefined); setReplayMessage('');
    try { setSelected((await request<{ activity: Activity }>(`${baseUrl}/activity/${encodeURIComponent(item.activityId)}`)).activity); }
    catch (error) { onError?.(message(error)); }
    finally { setBusy(false); }
  }

  async function openTrace(item: Activity) {
    if (!item.correlationId) return;
    setBusy(true); setSelected(item); setReplayMessage('');
    try { setTrace(await request<CorrelationTrace>(`${baseUrl}/activity/correlation/${encodeURIComponent(item.correlationId)}`)); }
    catch (error) { onError?.(message(error)); }
    finally { setBusy(false); }
  }

  async function replay(item: Activity) {
    setBusy(true); setSelected(item);
    try {
      const value = await request<{ message: string; correlationTrace?: CorrelationTrace }>(`${baseUrl}/activity/${encodeURIComponent(item.activityId)}/replay`, { method: 'POST' });
      setReplayMessage(value.message); setTrace(value.correlationTrace);
    } catch (error) { onError?.(message(error)); }
    finally { setBusy(false); }
  }

  return <section className="activity-center" aria-label="Activity Center">
    <header className="activity-center-header">
      <div><span className="hei-eyebrow">Engineering Timeline</span><h2>Activity Center</h2><p>Trace repository, planning, execution, validation, QA, memory, approvals, and Azure DevOps activity in one place.</p></div>
      <button type="button" onClick={() => void load()} disabled={busy}>{busy ? 'Refreshing...' : 'Refresh'}</button>
    </header>

    <div className="activity-summary">
      <Metric label="Activity" value={response?.summary.total || 0} detail="Matching records" />
      <Metric label="Correlations" value={response?.summary.correlations || 0} detail="Lifecycle traces" />
      <Metric label="Needs Attention" value={response?.summary.needsAttention || 0} detail="Failed or blocked" alert />
      <Metric label="Stages" value={Object.keys(response?.summary.categories || {}).length} detail="Lifecycle categories" />
    </div>

    <form className="activity-toolbar" onSubmit={(event) => { event.preventDefault(); void load(); }}>
      <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search activity, artifact, actor, or correlation" aria-label="Search activity" />
      <select value={category} onChange={(event) => setCategory(event.target.value)} aria-label="Filter category"><option value="">All categories</option>{(response?.categories || []).map((item) => <option key={item}>{item}</option>)}</select>
      <select value={status} onChange={(event) => setStatus(event.target.value)} aria-label="Filter status"><option value="">All statuses</option><option>Completed</option><option>In Progress</option><option>Failed</option><option>Recorded</option></select>
      <button type="submit">Search</button>
    </form>

    <div className={`activity-layout ${selected ? 'has-detail' : ''}`}>
      <div className="activity-timeline">
        {Object.entries(grouped).map(([day, items]) => <section key={day}><h3>{day}</h3>{items.map((item) => <article key={item.activityId} className={selected?.activityId === item.activityId ? 'selected' : ''}>
          <span className={`activity-marker marker-${slug(item.category)}`} aria-hidden="true" />
          <div className="activity-row-main"><div><span className="activity-category">{item.category}</span><strong>{item.title}</strong></div><time>{formatTime(item.occurredAt)}</time><p>{item.summary}</p><small>{item.source} · {item.status}{item.actor ? ` · ${item.actor}` : ''}</small></div>
          <div className="activity-actions"><button type="button" onClick={() => void openDetails(item)}>Open Details</button>{item.correlationId ? <button type="button" onClick={() => void openTrace(item)}>Correlation Trace</button> : null}<button type="button" onClick={() => void replay(item)}>Replay View</button></div>
        </article>)}</section>)}
        {!response?.activity.length ? <Empty /> : null}
        {(response?.activity.length || 0) > visibleCount ? <button className="activity-load-more" type="button" onClick={() => setVisibleCount((value) => value + 80)}>Load More Activity</button> : null}
      </div>

      {selected ? <aside className="activity-detail"><header><div><span>{selected.category}</span><h3>{selected.title}</h3></div><button type="button" onClick={() => { setSelected(undefined); setTrace(undefined); setReplayMessage(''); }}>Close</button></header>
        {replayMessage ? <div className="activity-replay-note"><strong>View-only replay</strong><span>{replayMessage}</span></div> : null}
        <dl><Data label="Status" value={selected.status} /><Data label="Time" value={formatDate(selected.occurredAt)} /><Data label="Source" value={selected.source} /><Data label="Actor" value={selected.actor || 'Not recorded'} /><Data label="Artifact" value={[selected.artifactType, selected.artifactId].filter(Boolean).join(' ') || 'Not recorded'} /><Data label="Correlation" value={selected.correlationId || 'Not recorded'} /></dl>
        <p>{selected.summary}</p>
        {trace ? <section className="correlation-trace"><h4>Correlation Trace</h4><span>{trace.count} records · {trace.status}</span>{trace.activity.map((item) => <div key={item.activityId}><time>{formatTime(item.occurredAt)}</time><strong>{item.category}</strong><span>{item.title}</span></div>)}</section> : null}
        <details><summary>Raw recorded details</summary><pre>{JSON.stringify(selected.details, null, 2)}</pre></details>
      </aside> : null}
    </div>
  </section>;
}

function Metric({ label, value, detail, alert = false }: { label: string; value: number; detail: string; alert?: boolean }) { return <div className={alert ? 'alert' : ''}><span>{label}</span><strong>{value}</strong><small>{detail}</small></div>; }
function Data({ label, value }: { label: string; value: string }) { return <div><dt>{label}</dt><dd>{value}</dd></div>; }
function Empty() { return <div className="activity-empty"><strong>No activity found</strong><span>Engineering lifecycle events will appear here as work progresses.</span></div>; }
function groupByDay(items: Activity[]) { return items.reduce<Record<string, Activity[]>>((groups, item) => { const date = new Date(item.occurredAt); const key = Number.isNaN(date.getTime()) ? 'Date not recorded' : date.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' }); (groups[key] ||= []).push(item); return groups; }, {}); }
function slug(value: string) { return value.toLowerCase().replace(/[^a-z]+/g, '-'); }
function formatTime(value: string) { const date = new Date(value); return Number.isNaN(date.getTime()) ? value : date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }); }
function formatDate(value: string) { const date = new Date(value); return Number.isNaN(date.getTime()) ? value : date.toLocaleString(); }
function message(error: unknown) { return error instanceof Error ? error.message : String(error); }
async function request<T>(url: string, init?: RequestInit): Promise<T> { const response = await fetch(url, init); const data = await response.json().catch(() => ({})); if (!response.ok) throw new Error(data?.error?.message || `Activity Center returned HTTP ${response.status}.`); return data as T; }
