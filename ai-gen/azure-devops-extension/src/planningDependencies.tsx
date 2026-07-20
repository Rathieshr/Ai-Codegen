import React, { FormEvent, useEffect, useMemo, useState } from 'react';

export type DependencyView = 'Tree' | 'Graph' | 'Table';

export type PlanningDependencyNode = {
  id: string;
  type: string;
  title: string;
  status: string;
  editable: boolean;
  dependencyCount: number;
  dependentCount: number;
  onCriticalPath: boolean;
  blocksOtherWork: boolean;
};

export type PlanningDependencyLink = {
  dependencyId: string;
  sourceId: string;
  sourceTitle: string;
  sourceType: string;
  targetId: string;
  targetTitle: string;
  targetType: string;
  targetReference: string;
  dependencyType: 'Depends On' | 'Blocked By';
  reason: string;
  status: 'Active' | 'Circular' | 'Missing' | 'Broken';
  warning: string;
  criticalPath: boolean;
  editable: boolean;
};

export type PlanningDependenciesData = {
  planningId: string;
  summary: { dependencies: number; active: number; circular: number; missing: number; broken: number };
  nodes: PlanningDependencyNode[];
  dependencies: PlanningDependencyLink[];
  tree: Array<PlanningDependencyNode & { dependsOn: PlanningDependencyLink[] }>;
  graph: { nodes: PlanningDependencyNode[]; edges: PlanningDependencyLink[] };
  table: PlanningDependencyLink[];
  criticalPath: { nodeIds: string[]; dependencyIds: string[]; titles: string[]; totalWeight: number; unit: string };
  warnings: Array<{ type: string; severity: string; message: string; dependencyId?: string; targetReference?: string }>;
  dependencyTypes: Array<'Depends On' | 'Blocked By'>;
};

type DependencyMutation = {
  dependencyId?: string;
  sourceId: string;
  targetId?: string;
  targetReference?: string;
  dependencyType: string;
  reason?: string;
};

type Props = {
  data?: PlanningDependenciesData;
  loading: boolean;
  error: string;
  view: DependencyView;
  selectedId: string;
  canEdit: boolean;
  busy: boolean;
  onView: (view: DependencyView) => void;
  onSave: (request: DependencyMutation) => Promise<void>;
  onDelete: (dependencyId: string) => Promise<void>;
  onSelect: (id: string) => void;
  onRetry: () => void;
};

export function PlanningDependencies({
  data, loading, error, view, selectedId, canEdit, busy, onView, onSave, onDelete, onSelect, onRetry,
}: Props) {
  const [editing, setEditing] = useState<PlanningDependencyLink>();
  const [formOpen, setFormOpen] = useState(false);
  const [sourceId, setSourceId] = useState('');
  const [targetId, setTargetId] = useState('');
  const [dependencyType, setDependencyType] = useState('Depends On');
  const [reason, setReason] = useState('');
  const editableNodes = useMemo(() => data?.nodes.filter((node) => node.editable) || [], [data?.nodes]);

  useEffect(() => {
    if (formOpen || !data) return;
    const preferred = data.nodes.find((node) => node.id === selectedId && node.editable) || editableNodes[0];
    setSourceId(preferred?.id || '');
  }, [data, editableNodes, formOpen, selectedId]);

  function openCreate() {
    const preferred = data?.nodes.find((node) => node.id === selectedId && node.editable) || editableNodes[0];
    setEditing(undefined); setSourceId(preferred?.id || ''); setTargetId(''); setDependencyType('Depends On'); setReason(''); setFormOpen(true);
  }

  function openEdit(link: PlanningDependencyLink) {
    setEditing(link); setSourceId(link.sourceId); setTargetId(link.targetId); setDependencyType(link.dependencyType); setReason(link.reason || ''); setFormOpen(true);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!sourceId || !targetId) return;
    try {
      await onSave({ dependencyId: editing?.dependencyId, sourceId, targetId, dependencyType, reason });
      setFormOpen(false); setEditing(undefined);
    } catch {
      // The parent surfaces the API error; keep this form open for correction.
    }
  }

  if (loading && !data) return <State title="Loading dependencies..." detail="Resolving execution order and critical path." />;
  if (error) return <State title="Dependency Management is unavailable." detail={error} action="Retry" onAction={onRetry} />;
  if (!data) return <State title="No dependency data is available." detail="Open a Planning Pack to resolve its execution order." />;

  return <div className="hei-dependency-workspace">
    <div className="hei-dependency-summary" aria-label="Dependency summary">
      <Summary label="Dependencies" value={data.summary.dependencies} />
      <Summary label="Critical Path" value={data.criticalPath.nodeIds.length ? `${data.criticalPath.totalWeight} pts` : 'None'} />
      <Summary label="Warnings" value={data.warnings.length} attention={data.warnings.length > 0} />
      <Summary label="Blocked Links" value={data.summary.circular + data.summary.broken} attention={data.summary.circular + data.summary.broken > 0} />
    </div>

    {data.warnings.length ? <section className="hei-dependency-warnings" aria-label="Dependency warnings">
      {data.warnings.map((warning, index) => <div className={`hei-dependency-warning severity-${warning.severity.toLowerCase()}`} key={`${warning.type}-${warning.dependencyId || index}`}>
        <strong>{warning.type}</strong><span>{warning.message}{warning.targetReference ? ` Target: ${warning.targetReference}.` : ''}</span>
      </div>)}
    </section> : null}

    {data.criticalPath.titles.length ? <section className="hei-critical-path">
      <div><span>Critical Path</span><strong>{data.criticalPath.totalWeight} {data.criticalPath.unit}</strong></div>
      <ol>{data.criticalPath.titles.map((title, index) => <li key={`${title}-${index}`}>{title}</li>)}</ol>
    </section> : null}

    <div className="hei-dependency-toolbar">
      <div className="hei-dependency-view-tabs" role="tablist" aria-label="Dependency views">
        {(['Tree', 'Graph', 'Table'] as DependencyView[]).map((option) => <button type="button" role="tab" aria-selected={view === option} className={view === option ? 'active' : ''} onClick={() => onView(option)} key={option}>{option}</button>)}
      </div>
      {canEdit && editableNodes.length ? <button className="planner-button primary" type="button" onClick={openCreate} disabled={busy}>Add Dependency</button> : null}
    </div>

    {formOpen ? <form className="hei-dependency-form" onSubmit={submit}>
      <header><div><span>Dependency</span><strong>{editing ? 'Edit execution constraint' : 'Add execution constraint'}</strong></div><button type="button" aria-label="Close dependency form" onClick={() => setFormOpen(false)}>×</button></header>
      <label><span>Artifact</span><select value={sourceId} onChange={(event) => setSourceId(event.target.value)} disabled={Boolean(editing)} required>{editableNodes.map((node) => <option value={node.id} key={node.id}>{node.type}: {node.title}</option>)}</select></label>
      <label><span>Dependency Type</span><select value={dependencyType} onChange={(event) => setDependencyType(event.target.value)}>{data.dependencyTypes.map((type) => <option key={type}>{type}</option>)}</select></label>
      <label><span>Target</span><select value={targetId} onChange={(event) => setTargetId(event.target.value)} required><option value="">Select an artifact</option>{data.nodes.filter((node) => node.id !== sourceId).map((node) => <option value={node.id} key={node.id}>{node.type}: {node.title}</option>)}</select></label>
      <label className="wide"><span>Reason</span><input value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Why must this work happen first?" /></label>
      <div className="hei-dependency-form-actions"><button className="planner-button secondary" type="button" onClick={() => setFormOpen(false)}>Cancel</button><button className="planner-button primary" type="submit" disabled={busy || !sourceId || !targetId}>{busy ? 'Saving...' : 'Save Dependency'}</button></div>
    </form> : null}

    {!data.dependencies.length ? <State title="No dependencies identified." detail="Add a dependency to define execution order and calculate the critical path." /> : view === 'Tree'
      ? <DependencyTree rows={data.tree} onSelect={onSelect} onEdit={openEdit} onDelete={onDelete} busy={busy} />
      : view === 'Graph'
        ? <DependencyGraph links={data.graph.edges} onSelect={onSelect} />
        : <DependencyTable links={data.table} onSelect={onSelect} onEdit={openEdit} onDelete={onDelete} busy={busy} />}
  </div>;
}

function DependencyTree({ rows, onSelect, onEdit, onDelete, busy }: { rows: PlanningDependenciesData['tree']; onSelect: (id: string) => void; onEdit: (link: PlanningDependencyLink) => void; onDelete: (id: string) => Promise<void>; busy: boolean }) {
  return <div className="hei-dependency-tree">{rows.map((node) => <section className="hei-dependency-tree-card" key={node.id}>
    <button className="hei-dependency-node-title" type="button" onClick={() => onSelect(node.id)}><span>{node.type}</span><strong>{node.title}</strong></button>
    <div>{node.dependsOn.map((link) => <DependencyRow link={link} onSelect={onSelect} onEdit={onEdit} onDelete={onDelete} busy={busy} key={link.dependencyId} />)}</div>
  </section>)}</div>;
}

function DependencyGraph({ links, onSelect }: { links: PlanningDependencyLink[]; onSelect: (id: string) => void }) {
  return <div className="hei-dependency-graph" aria-label="Dependency graph">{links.map((link) => <div className={`hei-dependency-edge status-${link.status.toLowerCase()}`} key={link.dependencyId}>
    <button type="button" className="hei-dependency-node" onClick={() => onSelect(link.targetId)} disabled={!link.targetId}><span>{link.targetType}</span><strong>{link.targetTitle}</strong></button>
    <div className="hei-dependency-arrow"><span>{link.dependencyType}</span><i aria-hidden="true">→</i>{link.criticalPath ? <small>Critical path</small> : null}</div>
    <button type="button" className="hei-dependency-node" onClick={() => onSelect(link.sourceId)}><span>{link.sourceType}</span><strong>{link.sourceTitle}</strong></button>
  </div>)}</div>;
}

function DependencyTable({ links, onSelect, onEdit, onDelete, busy }: { links: PlanningDependencyLink[]; onSelect: (id: string) => void; onEdit: (link: PlanningDependencyLink) => void; onDelete: (id: string) => Promise<void>; busy: boolean }) {
  return <div className="hei-dependency-table-wrap"><table className="hei-dependency-table"><thead><tr><th>Artifact</th><th>Dependency Type</th><th>Target</th><th>Status</th><th>Path</th><th>Actions</th></tr></thead><tbody>{links.map((link) => <tr key={link.dependencyId}>
    <td><button type="button" onClick={() => onSelect(link.sourceId)}>{link.sourceTitle}</button><small>{link.sourceType}</small></td>
    <td>{link.dependencyType}</td>
    <td><button type="button" onClick={() => link.targetId && onSelect(link.targetId)} disabled={!link.targetId}>{link.targetTitle}</button><small>{link.targetType}</small></td>
    <td><Status value={link.status} /></td><td>{link.criticalPath ? 'Critical' : 'Standard'}</td>
    <td>{link.editable ? <div className="hei-dependency-actions"><button type="button" onClick={() => onEdit(link)} disabled={busy}>Edit</button><button type="button" onClick={() => void onDelete(link.dependencyId)} disabled={busy}>Delete</button></div> : <span>Imported</span>}</td>
  </tr>)}</tbody></table></div>;
}

function DependencyRow({ link, onSelect, onEdit, onDelete, busy }: { link: PlanningDependencyLink; onSelect: (id: string) => void; onEdit: (link: PlanningDependencyLink) => void; onDelete: (id: string) => Promise<void>; busy: boolean }) {
  return <div className="hei-dependency-row"><div><span>{link.dependencyType}</span><button type="button" onClick={() => link.targetId && onSelect(link.targetId)} disabled={!link.targetId}>{link.targetTitle}</button><small>{link.reason || link.warning || `${link.targetType} must be ready first.`}</small></div><Status value={link.status} />{link.criticalPath ? <span className="hei-critical-chip">Critical Path</span> : null}{link.editable ? <div className="hei-dependency-actions"><button type="button" onClick={() => onEdit(link)} disabled={busy}>Edit</button><button type="button" onClick={() => void onDelete(link.dependencyId)} disabled={busy}>Delete</button></div> : null}</div>;
}

function Summary({ label, value, attention = false }: { label: string; value: string | number; attention?: boolean }) { return <div className={attention ? 'attention' : ''}><span>{label}</span><strong>{value}</strong></div>; }
function Status({ value }: { value: string }) { return <span className={`hei-dependency-status status-${value.toLowerCase()}`}>{value}</span>; }
function State({ title, detail, action, onAction }: { title: string; detail: string; action?: string; onAction?: () => void }) { return <div className="hei-planning-overview-state"><strong>{title}</strong><span>{detail}</span>{action && onAction ? <button className="planner-button secondary" type="button" onClick={onAction}>{action}</button> : null}</div>; }
