import React, { useEffect, useMemo, useState } from 'react';

type ServiceHealth = { id: string; name: string; status: string; latencyMs: number };
export type CommandCenterHealthSnapshot = {
  version: string; status: string; platformHealth: Record<string, unknown>;
  jobs: { total: number; running: number; queued: number; failed: number; byStatus: Record<string, number>; recent: Array<Record<string, unknown>> };
  queues: { depth: number; running: number; failed: number; health: string };
  events: { total: number; recent: Array<Record<string, unknown>>; byType: Record<string, number> };
  sdk: { name: string; status: string; contract: string; transport: string; methodCount: number };
  services: ServiceHealth[];
  performance: { snapshotLatencyMs: number; serviceLatencyMs: Record<string, number>; slowestService: string; refreshMode: string; cacheEnabled: boolean };
  storage: { status: string; fileCount: number; megabytesUsed: number; writable: boolean };
  database: { type: string; status: string; persistent: boolean; files: number };
  memory: { status: string; processMegabytes: number; metric: string };
  notifications: { total: number; unread: number; items: Array<Record<string, unknown>> };
  diagnostics: { warningCount?: number; available?: boolean; adminOnly?: boolean; warnings?: Array<Record<string, unknown>>; activityRecords?: number; auditRecords?: number; agentRuns?: number; probeCount?: number };
  cache: { status: string; ageMs: number; ttlSeconds: number }; generatedAt: string;
};

export function CommandCenterHealth({ baseUrl, role, onError }: { baseUrl: string; role: string; onError?: (message: string) => void }) {
  const [snapshot, setSnapshot] = useState<CommandCenterHealthSnapshot>();
  const [details, setDetails] = useState<'jobs' | 'events' | 'services' | 'diagnostics'>('services');
  const [busy, setBusy] = useState(false);
  const [offline, setOffline] = useState(!navigator.onLine);
  const isAdmin = role.toLowerCase().includes('admin');

  useEffect(() => {
    let cancelled = false;
    const refresh = () => { if (!cancelled && document.visibilityState === 'visible' && navigator.onLine) void load(false); };
    void load(false);
    const interval = window.setInterval(refresh, 30000);
    const visibility = () => refresh();
    const online = () => { setOffline(false); refresh(); };
    const offlineHandler = () => setOffline(true);
    document.addEventListener('visibilitychange', visibility); window.addEventListener('online', online); window.addEventListener('offline', offlineHandler);
    return () => { cancelled = true; window.clearInterval(interval); document.removeEventListener('visibilitychange', visibility); window.removeEventListener('online', online); window.removeEventListener('offline', offlineHandler); };
  }, [baseUrl, role]);

  async function load(force: boolean) {
    setBusy(true);
    try {
      const endpoint = isAdmin ? 'diagnostics' : 'health';
      setSnapshot(await request<CommandCenterHealthSnapshot>(`${baseUrl}/command-center/${endpoint}?force=${force}&role=${encodeURIComponent(isAdmin ? 'admin' : 'viewer')}`, isAdmin ? { headers: { 'X-HEI-Role': 'admin' } } : undefined));
      setOffline(false);
    } catch (error) { setOffline(!navigator.onLine); onError?.(message(error)); }
    finally { setBusy(false); }
  }

  const services = useMemo(() => snapshot?.services || [], [snapshot]);
  return <section className="command-health" aria-label="Command Center Health" aria-live="polite">
    <header className="command-health-header"><div><span className="hei-eyebrow">Production Operations</span><h2>Platform Health</h2><p>Operational readiness for the Command Center, platform services, queues, storage, and SDK.</p></div><div><Status value={offline ? 'Offline' : snapshot?.status || 'Loading'} /><button type="button" onClick={() => void load(true)} disabled={busy || offline}>{busy ? 'Refreshing...' : 'Refresh Now'}</button></div></header>
    {offline ? <div className="command-health-offline"><strong>Offline</strong><span>Showing the last available health snapshot. Refresh resumes when the connection returns.</span></div> : null}

    <div className="command-health-metrics">
      <Metric label="Platform" value={snapshot?.status || 'Loading'} detail={`HEI ${snapshot?.version || '7.10'}`} />
      <Metric label="Jobs" value={snapshot?.jobs.total ?? 0} detail={`${snapshot?.jobs.running || 0} running · ${snapshot?.jobs.failed || 0} failed`} />
      <Metric label="Queue" value={snapshot?.queues.depth ?? 0} detail={snapshot?.queues.health || 'Loading'} />
      <Metric label="Events" value={snapshot?.events.total ?? 0} detail="Recorded lifecycle events" />
      <Metric label="Latency" value={`${snapshot?.performance.snapshotLatencyMs || 0} ms`} detail={`Slowest: ${snapshot?.performance.slowestService || 'None'}`} />
      <Metric label="Storage" value={`${snapshot?.storage.megabytesUsed || 0} MB`} detail={`${snapshot?.storage.fileCount || 0} persisted files`} />
      <Metric label="Memory" value={`${snapshot?.memory.processMegabytes || 0} MB`} detail={snapshot?.memory.metric || 'Peak RSS'} />
      <Metric label="SDK" value={snapshot?.sdk.status || 'Loading'} detail={`${snapshot?.sdk.methodCount || 0} service contracts`} />
    </div>

    <div className="command-health-grid">
      <section><header><h3>Services</h3><span>{services.filter((item) => item.status === 'Healthy').length}/{services.length} healthy</span></header><div className="health-service-grid">{services.map((service) => <div key={service.id}><Status value={service.status} /><strong>{service.name}</strong><small>{service.latencyMs} ms</small></div>)}{!services.length ? <p>No service probes available.</p> : null}</div></section>
      <section><header><h3>Platform Runtime</h3></header><dl><Data label="Database" value={snapshot?.database.type || 'Loading'} /><Data label="Database Status" value={snapshot?.database.status || 'Loading'} /><Data label="Storage Writable" value={snapshot?.storage.writable ? 'Yes' : 'No'} /><Data label="Cache" value={snapshot ? `${snapshot.cache.status} · ${Math.round(snapshot.cache.ageMs)} ms old` : 'Loading'} /><Data label="Background Refresh" value={snapshot?.performance.refreshMode || 'Loading'} /><Data label="Notifications" value={`${snapshot?.notifications.unread || 0} unread`} /></dl></section>
    </div>

    <nav className="command-health-tabs" aria-label="Health details">{(['services', 'jobs', 'events', 'diagnostics'] as const).map((item) => <button key={item} type="button" className={details === item ? 'active' : ''} onClick={() => setDetails(item)} disabled={item === 'diagnostics' && !isAdmin}>{title(item)}</button>)}</nav>
    <section className="command-health-detail">
      {details === 'services' ? <ServiceTable services={services} /> : null}
      {details === 'jobs' ? <RecordList items={snapshot?.jobs.recent || []} empty="No jobs recorded." titleKey="jobType" statusKey="status" /> : null}
      {details === 'events' ? <RecordList items={snapshot?.events.recent || []} empty="No events recorded." titleKey="eventType" statusKey="source" /> : null}
      {details === 'diagnostics' && isAdmin ? <pre>{JSON.stringify(snapshot?.diagnostics || {}, null, 2)}</pre> : null}
    </section>
    <footer>Generated {snapshot?.generatedAt ? formatDate(snapshot.generatedAt) : 'when the platform responds'} · Cached for {snapshot?.cache.ttlSeconds || 10} seconds</footer>
  </section>;
}

function Metric({ label, value, detail }: { label: string; value: React.ReactNode; detail: string }) { return <div><span>{label}</span><strong>{value}</strong><small>{detail}</small></div>; }
function Data({ label, value }: { label: string; value: string }) { return <div><dt>{label}</dt><dd>{value}</dd></div>; }
function Status({ value }: { value: string }) { return <span className={`command-health-status status-${value.toLowerCase().replace(/[^a-z]+/g, '-')}`}>{value}</span>; }
function ServiceTable({ services }: { services: ServiceHealth[] }) { return <div className="command-health-table" role="table"><div role="row"><strong>Service</strong><strong>Status</strong><strong>Latency</strong></div>{services.map((item) => <div role="row" key={item.id}><span>{item.name}</span><Status value={item.status} /><span>{item.latencyMs} ms</span></div>)}</div>; }
function RecordList({ items, empty, titleKey, statusKey }: { items: Array<Record<string, unknown>>; empty: string; titleKey: string; statusKey: string }) { return <div className="command-health-records">{items.length ? items.map((item, index) => <article key={String(item.jobId || item.eventId || index)}><strong>{String(item[titleKey] || 'Platform record')}</strong><Status value={String(item[statusKey] || 'Recorded')} /><small>{formatDate(String(item.createdAt || ''))}</small></article>) : <p>{empty}</p>}</div>; }
function title(value: string) { return value.charAt(0).toUpperCase() + value.slice(1); }
function formatDate(value: string) { const date = new Date(value); return Number.isNaN(date.getTime()) ? value || 'Not recorded' : date.toLocaleString(); }
function message(error: unknown) { return error instanceof Error ? error.message : String(error); }
async function request<T>(url: string, init?: RequestInit): Promise<T> { const response = await fetch(url, init); const data = await response.json().catch(() => ({})); if (!response.ok) throw new Error(data?.error?.message || `Command Center health returned HTTP ${response.status}.`); return data as T; }
