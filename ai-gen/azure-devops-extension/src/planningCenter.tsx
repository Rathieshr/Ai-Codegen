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

type EngineeringEstimation = {
  estimateId: string; artifactId: string; artifactType: string; version: number; status: string; overrideReason?: string;
  effectiveEstimate: {
    engineeringHours: number; engineeringDays: number; storyPoints: number; confidence: number; risk: string; complexity: string;
    estimatedSprintCount: number; estimatedTestCases: number; estimatedPullRequests: number; repositoryReuse: number;
    topEstimationDrivers: string[]; warnings: string[]; taskEstimates: Array<{ taskId: string; taskName: string; estimatedDuration: string; storyPointContribution: number; complexity: string; confidence: number }>;
    report: { features: number; stories: number; tasks: number; engineeringDays: number; storyPoints: number; estimatedSprintCount: number; averageStorySize: number; confidence: number; risk: string; repositoryReuse: number; estimatedTestCases: number; estimatedPullRequests: number; highRiskStories: number; suggestedTeamSize: number };
  };
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
  ['epics', 'Epics'], ['features', 'Features'], ['stories', 'Stories'], ['tasks', 'Tasks'],
];

type PlanningTreeNode = PlanningCenterItem & { children: PlanningTreeNode[] };
const HIERARCHY_TYPES = new Set(['Epic', 'Feature', 'Story', 'Task']);
const TYPE_ORDER: Record<string, number> = { Epic: 0, Feature: 1, Story: 2, Task: 3 };

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
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [checkedIds, setCheckedIds] = useState<Set<string>>(new Set());
  const [estimates, setEstimates] = useState<Record<string, EngineeringEstimation>>({});
  const [estimationBusy, setEstimationBusy] = useState('');
  const [overrideOpen, setOverrideOpen] = useState(false);
  const [overrideHours, setOverrideHours] = useState('');
  const [overridePoints, setOverridePoints] = useState('');
  const [overrideReason, setOverrideReason] = useState('');

  useEffect(() => { void load(true); }, [projectId]);
  useEffect(() => {
    if (!currentWorkItemId || !data?.items.length) return;
    const match = data.items.find((item) => [item.id, item.sourceItemId].includes(currentWorkItemId));
    if (match) setSelectedId(match.id);
  }, [currentWorkItemId, data?.items]);

  const selected = useMemo(
    () => data?.items.find((item) => item.id === selectedId) || data?.items.find((item) => HIERARCHY_TYPES.has(item.type)) || data?.items[0],
    [data, selectedId],
  );
  const hierarchyItems = useMemo(() => (data?.items || []).filter((item) => HIERARCHY_TYPES.has(item.type)), [data]);
  const tree = useMemo(() => buildTree(hierarchyItems), [hierarchyItems]);
  const visibleNodes = useMemo(() => flattenVisible(tree, expandedIds), [tree, expandedIds]);
  const breadcrumbs = useMemo(() => selected ? buildBreadcrumbs(selected, hierarchyItems) : [], [selected, hierarchyItems]);
  const selectedForReview = useMemo(() => hierarchyItems.filter((item) => checkedIds.has(item.id)), [checkedIds, hierarchyItems]);
  const selectedEstimate = selected ? estimates[selected.id] : undefined;

  useEffect(() => {
    if (!hierarchyItems.length) return;
    setExpandedIds((current) => {
      if (current.size) return current;
      return new Set(tree.map((item) => item.id));
    });
  }, [hierarchyItems, tree]);
  useEffect(() => {
    if (breadcrumbs.length < 2) return;
    setExpandedIds((current) => new Set([...current, ...breadcrumbs.slice(0, -1).map((item) => item.id)]));
  }, [breadcrumbs]);
  useEffect(() => {
    if (!selected || selected.type === 'Recommendation' || estimates[selected.id] || estimationBusy === selected.id) return;
    void estimate(selected);
  }, [selected?.id, data?.items]);

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
      if (reset) setCheckedIds(new Set());
      if (reset && payload.items.length && !payload.items.some((item) => item.id === selectedId)) {
        setSelectedId(payload.items.find((item) => HIERARCHY_TYPES.has(item.type))?.id || payload.items[0].id);
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
      await submitDecision(item, decision);
      await load(false);
    } catch (error) {
      onError(error instanceof Error ? error.message : `Unable to ${decision} planning item.`);
    } finally {
      setActionId('');
    }
  }

  async function decideSelected(decision: 'approve' | 'reject') {
    const actionable = selectedForReview.filter((item) => decision === 'approve' ? item.canApprove : item.canReject);
    if (!actionable.length) {
      onError(`No selected items can be ${decision === 'approve' ? 'approved' : 'rejected'}.`);
      return;
    }
    setActionId('bulk');
    try {
      for (const item of actionable) {
        const itemEstimate = decision === 'approve' ? estimates[item.id] || await estimate(item) : undefined;
        if (decision === 'approve' && !itemEstimate) throw new Error(`Generate the Engineering Estimation Report before approving ${item.title}.`);
        await submitDecision(item, decision, itemEstimate);
      }
      setCheckedIds(new Set());
      await load(false);
    } catch (error) {
      onError(error instanceof Error ? error.message : `Unable to ${decision} selected planning items.`);
    } finally {
      setActionId('');
    }
  }

  async function submitDecision(item: PlanningCenterItem, decision: 'approve' | 'reject', suppliedEstimate?: EngineeringEstimation) {
    const estimateValue = suppliedEstimate || estimates[item.id];
    if (decision === 'approve' && estimateValue && estimateValue.status !== 'Approved') {
      const estimateResponse = await fetch(`${baseUrl}/planning/estimate/${encodeURIComponent(estimateValue.estimateId)}/approve?actor=${encodeURIComponent(actor)}`, { method: 'POST' });
      if (!estimateResponse.ok) throw new Error('The Engineering Estimation Report could not be approved with this planning item.');
    }
    const response = await fetch(`${baseUrl}/planning/${encodeURIComponent(item.id)}/${decision}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ actor }),
    });
    const payload = await response.json() as { error?: { message?: string } };
    if (!response.ok) throw new Error(payload.error?.message || `Unable to ${decision} ${item.type} '${item.title}'.`);
  }

  async function estimate(item: PlanningCenterItem, recalculate = false): Promise<EngineeringEstimation | undefined> {
    setEstimationBusy(item.id);
    try {
      const children = descendantsOf(item.id, hierarchyItems);
      const details = item.details || {};
      const repositoryContext = firstObject(details.repositoryContext, details.repository, details.repositoryIntelligence);
      const payload = {
        ...(recalculate && estimates[item.id] ? { estimateId: estimates[item.id].estimateId } : {}),
        artifact: item, children,
        repositoryContext,
        engineeringMemory: firstObject(details.memoryContext, details.engineeringMemory),
        acceptanceCriteria: arrayValue(details.acceptanceCriteria || details.acceptance_criteria),
        dependencyAnalysis: item.dependencies,
        riskAnalysis: item.risks,
      };
      const response = await fetch(`${baseUrl}/planning/estimate${recalculate ? '/recalculate' : ''}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      const result = await response.json() as EngineeringEstimation & { error?: { message?: string } };
      if (!response.ok) throw new Error(result.error?.message || 'Unable to generate the Engineering Estimation Report.');
      setEstimates((current) => ({ ...current, [item.id]: result }));
      setOverrideHours(String(result.effectiveEstimate.engineeringHours || ''));
      setOverridePoints(String(result.effectiveEstimate.storyPoints || ''));
      return result;
    } catch (error) { onError(error instanceof Error ? error.message : 'Unable to generate the Engineering Estimation Report.'); return undefined; }
    finally { setEstimationBusy(''); }
  }

  async function overrideEstimate(item: PlanningCenterItem) {
    const current = estimates[item.id];
    if (!current) return;
    setEstimationBusy(item.id);
    try {
      const response = await fetch(`${baseUrl}/planning/estimate/${encodeURIComponent(current.estimateId)}/override`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ engineeringHours: Number(overrideHours), storyPoints: Number(overridePoints), overrideReason, actor }),
      });
      const result = await response.json() as EngineeringEstimation & { error?: { message?: string } };
      if (!response.ok) throw new Error(result.error?.message || 'Unable to save the estimate override.');
      setEstimates((values) => ({ ...values, [item.id]: result }));
      setOverrideOpen(false); setOverrideReason('');
    } catch (error) { onError(error instanceof Error ? error.message : 'Unable to save the estimate override.'); }
    finally { setEstimationBusy(''); }
  }

  function toggleExpanded(itemId: string) {
    setExpandedIds((current) => { const next = new Set(current); if (next.has(itemId)) next.delete(itemId); else next.add(itemId); return next; });
  }

  function toggleChecked(itemId: string) {
    setCheckedIds((current) => { const next = new Set(current); if (next.has(itemId)) next.delete(itemId); else next.add(itemId); return next; });
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

      <div className="hei-planning-metrics compact">
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
        <>
          <nav className="hei-planning-breadcrumbs" aria-label="Planning hierarchy breadcrumb">
            {breadcrumbs.length ? breadcrumbs.map((item, index) => <React.Fragment key={item.id}><button type="button" onClick={() => setSelectedId(item.id)}>{item.type}: {item.title}</button>{index < breadcrumbs.length - 1 ? <span aria-hidden="true">›</span> : null}</React.Fragment>) : <span>Select an Epic, Feature, Story, or Task.</span>}
          </nav>
          <div className="hei-planning-tree-toolbar">
            <div><strong>Planning Hierarchy</strong><span>{visibleNodes.length} visible · {checkedIds.size} selected</span></div>
            <div>
              <button className="planner-button secondary" type="button" onClick={() => setExpandedIds(new Set(hierarchyItems.filter((item) => item.childCount).map((item) => item.id)))}>Expand All</button>
              <button className="planner-button secondary" type="button" onClick={() => setExpandedIds(new Set())}>Collapse All</button>
              <button className="planner-button primary" type="button" onClick={() => void decideSelected('approve')} disabled={!canContribute || !checkedIds.size || Boolean(actionId)}>Approve Selected</button>
              <button className="planner-button secondary" type="button" onClick={() => void decideSelected('reject')} disabled={!canContribute || !checkedIds.size || Boolean(actionId)}>Reject Selected</button>
            </div>
          </div>
          <div className="hei-planning-layout hierarchy">
          <div className="hei-planning-tree" role="tree" aria-label="Planning hierarchy" aria-multiselectable="true">
            {visibleNodes.map(({ item, level, hasChildren }) => (
              <div key={item.id} role="treeitem" aria-level={level + 1} aria-expanded={hasChildren ? expandedIds.has(item.id) : undefined} aria-selected={checkedIds.has(item.id)} className={`hei-planning-tree-node ${selected?.id === item.id ? 'selected' : ''}`} style={{ '--tree-level': level } as React.CSSProperties}>
                <button className="hei-planning-tree-toggle" type="button" onClick={() => hasChildren && toggleExpanded(item.id)} aria-label={hasChildren ? `${expandedIds.has(item.id) ? 'Collapse' : 'Expand'} ${item.title}` : `${item.title} has no children`} disabled={!hasChildren}>{hasChildren ? (expandedIds.has(item.id) ? '−' : '+') : '·'}</button>
                <input type="checkbox" checked={checkedIds.has(item.id)} onChange={() => toggleChecked(item.id)} aria-label={`Select ${item.type} ${item.title}`} />
                <button className="hei-planning-tree-content" type="button" onClick={() => setSelectedId(item.id)}>
                  <span><TypeBadge value={item.type} /><strong>{item.title}</strong></span>
                  <span className="hei-planning-tree-status"><StatusBadge value={item.approvalStatus} /><StatusBadge value={item.readiness} /></span>
                  <span className="hei-planning-tree-facts"><small>{item.confidence}% confidence</small><small>{item.dependencies.length} dependencies</small><small>{item.storyPoints ? `${item.storyPoints} points` : 'Not estimated'}</small><small>{item.riskLevel} risk</small><small>{item.childCount} children</small><small>{item.recommendationCount} recommendations</small></span>
                </button>
              </div>
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
              <EstimationReport estimate={selectedEstimate} loading={estimationBusy === selected.id} onRecalculate={() => void estimate(selected, true)} onEdit={() => {
                setOverrideHours(String(selectedEstimate?.effectiveEstimate.engineeringHours || ''));
                setOverridePoints(String(selectedEstimate?.effectiveEstimate.storyPoints || ''));
                setOverrideOpen((value) => !value);
              }} />
              {overrideOpen && selectedEstimate ? <div className="hei-estimation-override">
                <label><span>Engineering Hours</span><input type="number" min="1" value={overrideHours} onChange={(event) => setOverrideHours(event.target.value)} /></label>
                <label><span>Story Points</span><input type="number" min="1" value={overridePoints} onChange={(event) => setOverridePoints(event.target.value)} /></label>
                <label className="wide"><span>Override Reason</span><textarea value={overrideReason} onChange={(event) => setOverrideReason(event.target.value)} placeholder="Explain the engineering evidence behind this adjustment." /></label>
                <button className="planner-button primary" type="button" onClick={() => void overrideEstimate(selected)} disabled={!overrideHours || !overridePoints || !overrideReason.trim() || Boolean(estimationBusy)}>Save Override</button>
                <button className="planner-button secondary" type="button" onClick={() => setOverrideOpen(false)}>Cancel</button>
              </div> : null}
              <div className="hei-planning-actions">
                <button className="planner-button primary" type="button" onClick={() => void decide(selected, 'approve')} disabled={!canContribute || !selected.canApprove || Boolean(actionId) || !selectedEstimate || estimationBusy === selected.id}>Approve</button>
                <button className="planner-button secondary" type="button" onClick={() => void decide(selected, 'reject')} disabled={!canContribute || !selected.canReject || Boolean(actionId)}>Reject</button>
                <button className="planner-button secondary" type="button" onClick={() => setDetailsOpen((value) => !value)}>{detailsOpen ? 'Hide Details' : 'Open Details'}</button>
                {selected.type === 'Story' || selected.type === 'Task' ? <button className="planner-button secondary" type="button" onClick={() => generate(selected)} disabled={!selected.canGenerateExecutionPackage}>Generate Execution Package</button> : null}
              </div>
              {detailsOpen ? <div className="hei-planning-source-details"><Detail label="Planning ID" value={selected.id} /><Detail label="Source" value={selected.source} /><Detail label="Updated" value={selected.updatedAt || 'Not recorded'} /></div> : null}
            </article>
          ) : null}
          </div>
        </>
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

function EstimationReport({ estimate, loading, onRecalculate, onEdit }: { estimate?: EngineeringEstimation; loading: boolean; onRecalculate: () => void; onEdit: () => void }) {
  if (!estimate) return <section className="hei-estimation-report loading"><div><span>Engineering Estimation</span><h4>{loading ? 'Calculating from engineering evidence...' : 'Estimation Report not available'}</h4></div><p>HEI uses task decomposition, repository context, acceptance criteria, risk, dependencies, and approved Engineering Memory.</p>{!loading ? <button className="planner-button secondary" type="button" onClick={onRecalculate}>Retry Estimation</button> : null}</section>;
  const value = estimate.effectiveEstimate;
  const report = value.report;
  return <section className="hei-estimation-report" aria-label="Engineering Estimation Report">
    <header><div><span>Planning Summary</span><h4>Engineering Estimation Report</h4><p>Standard Engineering Estimation · Version {estimate.version}{estimate.status === 'Overridden' ? ' · Human override applied' : ''}</p></div><StatusBadge value={estimate.status} /></header>
    <div className="hei-estimation-metrics">
      <Detail label="Engineering Effort" value={`${report.engineeringDays} days`} />
      <Detail label="Story Points" value={report.storyPoints} />
      <Detail label="Confidence" value={`${report.confidence}%`} />
      <Detail label="Repository Reuse" value={`${report.repositoryReuse}%`} />
      <Detail label="High Risk Stories" value={report.highRiskStories} />
      <Detail label="Estimated Tests" value={report.estimatedTestCases} />
      <Detail label="Estimated PRs" value={report.estimatedPullRequests} />
      <Detail label="Sprint Count" value={report.estimatedSprintCount} />
    </div>
    <div className="hei-estimation-body"><section><strong>Top Estimation Drivers</strong>{value.topEstimationDrivers.length ? <ul>{value.topEstimationDrivers.map((driver) => <li key={driver}>{driver}</li>)}</ul> : <p>No estimation drivers were supplied.</p>}</section><section><strong>Task Foundation</strong>{value.taskEstimates.slice(0, 8).map((task) => <div className="hei-estimation-task" key={task.taskId || task.taskName}><span>{task.taskName}</span><strong>{task.estimatedDuration} · {task.storyPointContribution} pts</strong><small>{task.complexity} · {task.confidence}% confidence</small></div>)}</section></div>
    {value.warnings.length ? <details><summary>{value.warnings.length} confidence warning{value.warnings.length === 1 ? '' : 's'}</summary><ul>{value.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></details> : null}
    <div className="hei-estimation-actions"><button className="planner-button secondary" type="button" onClick={onRecalculate} disabled={loading}>{loading ? 'Recalculating...' : 'Recalculate'}</button><button className="planner-button secondary" type="button" onClick={onEdit}>Edit Estimate</button></div>
  </section>;
}

function buildTree(items: PlanningCenterItem[]): PlanningTreeNode[] {
  const nodes = new Map(items.map((item) => [item.id, { ...item, children: [] } as PlanningTreeNode]));
  const sourceIds = new Map(items.filter((item) => item.sourceItemId).map((item) => [item.sourceItemId, item.id]));
  const roots: PlanningTreeNode[] = [];
  nodes.forEach((node) => {
    const parentId = nodes.has(node.parentId) ? node.parentId : sourceIds.get(node.parentId) || '';
    const parent = parentId ? nodes.get(parentId) : undefined;
    if (parent && parent.id !== node.id) parent.children.push(node); else roots.push(node);
  });
  const sort = (values: PlanningTreeNode[]) => values.sort((left, right) => (TYPE_ORDER[left.type] ?? 99) - (TYPE_ORDER[right.type] ?? 99) || left.title.localeCompare(right.title)).forEach((item) => sort(item.children));
  sort(roots);
  return roots;
}

function flattenVisible(tree: PlanningTreeNode[], expanded: Set<string>): Array<{ item: PlanningTreeNode; level: number; hasChildren: boolean }> {
  const output: Array<{ item: PlanningTreeNode; level: number; hasChildren: boolean }> = [];
  const visit = (nodes: PlanningTreeNode[], level: number) => nodes.forEach((item) => {
    output.push({ item, level, hasChildren: Boolean(item.children.length) });
    if (item.children.length && expanded.has(item.id)) visit(item.children, level + 1);
  });
  visit(tree, 0);
  return output;
}

function buildBreadcrumbs(selected: PlanningCenterItem, items: PlanningCenterItem[]): PlanningCenterItem[] {
  const byId = new Map(items.map((item) => [item.id, item]));
  const sourceIds = new Map(items.filter((item) => item.sourceItemId).map((item) => [item.sourceItemId, item]));
  const path: PlanningCenterItem[] = [];
  const visited = new Set<string>();
  let cursor: PlanningCenterItem | undefined = selected;
  while (cursor && !visited.has(cursor.id)) {
    visited.add(cursor.id);
    path.unshift(cursor);
    cursor = byId.get(cursor.parentId) || sourceIds.get(cursor.parentId);
  }
  return path;
}

function descendantsOf(parentId: string, items: PlanningCenterItem[]): PlanningCenterItem[] {
  const output: PlanningCenterItem[] = [];
  const visited = new Set<string>();
  const visit = (id: string) => {
    if (visited.has(id)) return;
    visited.add(id);
    const sourceId = items.find((candidate) => candidate.id === id)?.sourceItemId;
    items.filter((item) => item.parentId === id || Boolean(sourceId && item.parentId === sourceId)).forEach((item) => { output.push(item); visit(item.id); });
  };
  visit(parentId);
  return output;
}
function firstObject(...values: unknown[]): Record<string, unknown> { return values.find((value) => value && typeof value === 'object' && !Array.isArray(value)) as Record<string, unknown> || {}; }
function arrayValue(value: unknown): unknown[] { return Array.isArray(value) ? value : value == null ? [] : [value]; }

function TypeBadge({ value }: { value: string }) { return <span className="hei-type-badge">{value}</span>; }
function StatusBadge({ value }: { value: string }) { return <span className={`hei-status-badge status-${value.toLowerCase().replace(/[^a-z]+/g, '-')}`}>{value}</span>; }
