import React, { FormEvent, useEffect, useMemo, useState } from 'react';
import './styles.css';

export type PlanningCenterItem = {
  id: string;
  type: 'Requirement' | 'Epic' | 'Feature' | 'Story' | 'Task' | 'Recommendation' | string;
  title: string;
  description: string;
  parentId: string;
  depth: number;
  childCount: number;
  status: string;
  approvalStatus: string;
  storyPoints: number;
  dependencies: string[];
  readiness: string;
  risks: string[];
  riskLevel: string;
  confidence: number;
  recommendationCount: number;
  source: string;
  sourceItemId: string;
  updatedAt: string;
  canApprove: boolean;
  canReject: boolean;
  canGenerateExecutionPackage: boolean;
  details?: Record<string, unknown>;
};

type PlanningCenterResponse = {
  schemaVersion: string;
  summary: Record<string, number>;
  items: PlanningCenterItem[];
  recommendations: Array<Record<string, unknown>>;
  filters: { types: string[]; statuses: string[]; readiness: string[] };
  pagination: { total: number; offset: number; limit: number; returned: number; hasMore: boolean };
};

type Props = {
  baseUrl: string;
  projectId: string;
  actor: string;
  currentWorkItemId?: string;
  canContribute: boolean;
  onGenerateExecutionPackage: () => void;
  onError: (message: string) => void;
};

const TYPE_LABELS: Array<[keyof PlanningCenterResponse['summary'], string]> = [
  ['requirements', 'Requirements'], ['epics', 'Epics'], ['features', 'Features'], ['stories', 'Stories'], ['tasks', 'Tasks'],
];

export function PlanningCenter({
  baseUrl, projectId, actor, currentWorkItemId, canContribute, onGenerateExecutionPackage, onError,
}: Props) {
  const [data, setData] = useState<PlanningCenterResponse>();
  const [selectedId, setSelectedId] = useState('');
  const [search, setSearch] = useState('');
  const [type, setType] = useState('');
  const [status, setStatus] = useState('');
  const [readiness, setReadiness] = useState('');
  const [loading, setLoading] = useState(false);
  const [actionId, setActionId] = useState('');
  const [detailsOpen, setDetailsOpen] = useState(false);

  useEffect(() => { void load(true); }, [projectId]);
  useEffect(() => {
    if (!currentWorkItemId || !data?.items.length) return;
    const match = data.items.find((item) => [item.id, item.sourceItemId].includes(currentWorkItemId));
    if (match) setSelectedId(match.id);
  }, [currentWorkItemId, data?.items]);

  const selected = useMemo(
    () => data?.items.find((item) => item.id === selectedId) || data?.items[0],
    [data, selectedId],
  );

  async function load(reset = true) {
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: '250' });
      if (projectId) params.set('projectId', projectId);
      if (search.trim()) params.set('search', search.trim());
      if (type) params.set('type', type);
      if (status) params.set('status', status);
      if (readiness) params.set('readiness', readiness);
      const response = await fetch(`${baseUrl}/planning?${params.toString()}`);
      const payload = await response.json() as PlanningCenterResponse & { error?: { message?: string } };
      if (!response.ok) throw new Error(payload.error?.message || `Planning Center returned HTTP ${response.status}`);
      setData(payload);
      if (reset && payload.items.length && !payload.items.some((item) => item.id === selectedId)) {
        setSelectedId(payload.items[0].id);
      }
    } catch (error) {
      onError(error instanceof Error ? error.message : 'Unable to load Planning Center.');
    } finally {
      setLoading(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void load(true);
  }

  async function decide(item: PlanningCenterItem, decision: 'approve' | 'reject') {
    setActionId(item.id);
    try {
      const response = await fetch(`${baseUrl}/planning/${encodeURIComponent(item.id)}/${decision}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ actor }),
      });
      const payload = await response.json() as { error?: { message?: string } };
      if (!response.ok) throw new Error(payload.error?.message || `Unable to ${decision} planning item.`);
      await load(false);
    } catch (error) {
      onError(error instanceof Error ? error.message : `Unable to ${decision} planning item.`);
    } finally {
      setActionId('');
    }
  }

  function generate(item: PlanningCenterItem) {
    if (!currentWorkItemId || ![item.id, item.sourceItemId].includes(currentWorkItemId)) {
      onError(`Open ${item.type} ${item.sourceItemId || item.id} in Azure DevOps before generating its Execution Package.`);
      return;
    }
    onGenerateExecutionPackage();
  }

  return (
    <section className="hei-planning-center" aria-label="Planning Center">
      <header className="hei-planning-titlebar">
        <div><span>Planning Intelligence</span><h2>Planning Center</h2><p>Review the backlog, recommendations, readiness, dependencies, and risk in one place.</p></div>
        <div><StatusBadge value={loading ? 'Refreshing' : `${data?.pagination.total || 0} items`} /><button className="planner-button secondary" type="button" onClick={() => void load(true)} disabled={loading}>Refresh</button></div>
      </header>

      <div className="hei-planning-metrics">
        {TYPE_LABELS.map(([key, label]) => <Metric key={key} label={label} value={data?.summary[key] || 0} />)}
        <Metric label="Recommendations" value={data?.summary.recommendations || 0} />
        <Metric label="Needs Review" value={data?.summary.needsReview || 0} emphasis />
        <Metric label="Confidence" value={`${data?.summary.averageConfidence || 0}%`} />
      </div>

      <form className="hei-planning-filters" onSubmit={submit} role="search">
        <label><span>Search</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search title, dependency, risk" /></label>
        <label><span>Type</span><select value={type} onChange={(event) => setType(event.target.value)}><option value="">All types</option>{(data?.filters.types || []).map((value) => <option key={value}>{value}</option>)}</select></label>
        <label><span>Status</span><select value={status} onChange={(event) => setStatus(event.target.value)}><option value="">All statuses</option>{(data?.filters.statuses || []).map((value) => <option key={value}>{value}</option>)}</select></label>
        <label><span>Readiness</span><select value={readiness} onChange={(event) => setReadiness(event.target.value)}><option value="">All readiness</option>{(data?.filters.readiness || []).map((value) => <option key={value}>{value}</option>)}</select></label>
        <button className="planner-button primary" type="submit" disabled={loading}>Apply</button>
        <button className="planner-button secondary" type="button" onClick={() => { setSearch(''); setType(''); setStatus(''); setReadiness(''); setTimeout(() => void load(true), 0); }}>Clear</button>
      </form>

      {!data?.items.length ? (
        <div className="hei-planning-empty"><strong>No planning items match this view.</strong><span>Analyze or generate a planning artifact, or clear the filters.</span></div>
      ) : (
        <div className="hei-planning-layout">
          <div className="hei-planning-backlog" role="list" aria-label="Planning backlog">
            {data.items.map((item) => (
              <button key={item.id} type="button" role="listitem" className={`hei-planning-card ${selected?.id === item.id ? 'selected' : ''}`} onClick={() => setSelectedId(item.id)}>
                <div><TypeBadge value={item.type} /><StatusBadge value={item.approvalStatus} /></div>
                <strong>{item.title}</strong>
                <span>{item.readiness} · {item.confidence}% confidence</span>
                <footer><small>{item.storyPoints ? `${item.storyPoints} points` : 'Not estimated'}</small><small>{item.dependencies.length} dependencies</small><small>{item.childCount} children</small></footer>
              </button>
            ))}
          </div>
          {selected ? (
            <article className="hei-planning-details">
              <div className="hei-planning-detail-heading"><div><TypeBadge value={selected.type} /><h3>{selected.title}</h3></div><StatusBadge value={selected.readiness} /></div>
              <p>{selected.description || 'No description captured.'}</p>
              <div className="hei-planning-detail-grid">
                <Detail label="Approval" value={selected.approvalStatus} />
                <Detail label="Story Points" value={selected.storyPoints || 'Not estimated'} />
                <Detail label="Risk" value={selected.riskLevel} />
                <Detail label="Confidence" value={`${selected.confidence}%`} />
                <Detail label="Recommendations" value={selected.recommendationCount} />
                <Detail label="Children" value={selected.childCount} />
              </div>
              <DetailList title="Dependencies" values={selected.dependencies} empty="No dependencies identified." />
              <DetailList title="Risks" values={selected.risks} empty="No planning risks identified." />
              <div className="hei-planning-actions">
                <button className="planner-button primary" type="button" onClick={() => void decide(selected, 'approve')} disabled={!canContribute || !selected.canApprove || Boolean(actionId)}>Approve</button>
                <button className="planner-button secondary" type="button" onClick={() => void decide(selected, 'reject')} disabled={!canContribute || !selected.canReject || Boolean(actionId)}>Reject</button>
                <button className="planner-button secondary" type="button" onClick={() => setDetailsOpen((value) => !value)}>{detailsOpen ? 'Hide Details' : 'Open Details'}</button>
                {selected.type === 'Story' || selected.type === 'Task' ? <button className="planner-button secondary" type="button" onClick={() => generate(selected)} disabled={!selected.canGenerateExecutionPackage}>Generate Execution Package</button> : null}
              </div>
              {detailsOpen ? <div className="hei-planning-source-details"><Detail label="Planning ID" value={selected.id} /><Detail label="Source" value={selected.source} /><Detail label="Updated" value={selected.updatedAt || 'Not recorded'} /></div> : null}
            </article>
          ) : null}
        </div>
      )}
      {data?.pagination.hasMore ? <p className="hei-planning-limit">Showing the first {data.pagination.returned} of {data.pagination.total} matching items. Narrow the filters to inspect the remaining backlog.</p> : null}
    </section>
  );
}

function Metric({ label, value, emphasis = false }: { label: string; value: string | number; emphasis?: boolean }) {
  return <div className={emphasis ? 'emphasis' : ''}><span>{label}</span><strong>{value}</strong></div>;
}

function Detail({ label, value }: { label: string; value: string | number }) {
  return <div><span>{label}</span><strong>{value}</strong></div>;
}

function DetailList({ title, values, empty }: { title: string; values: string[]; empty: string }) {
  return <section className="hei-planning-list"><strong>{title}</strong>{values.length ? <ul>{values.map((value) => <li key={value}>{value}</li>)}</ul> : <p>{empty}</p>}</section>;
}

function TypeBadge({ value }: { value: string }) { return <span className="hei-type-badge">{value}</span>; }
function StatusBadge({ value }: { value: string }) { return <span className={`hei-status-badge status-${value.toLowerCase().replace(/[^a-z]+/g, '-')}`}>{value}</span>; }
