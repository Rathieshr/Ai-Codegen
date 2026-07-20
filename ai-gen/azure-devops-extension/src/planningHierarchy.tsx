import React, { FormEvent, useEffect, useMemo, useState } from 'react';
import { PlanningCenterItem } from './planningCenter';
import { StoryDetailDrawer } from './storyDetailDrawer';

type TreeNode = PlanningCenterItem & { children: TreeNode[] };
type NodeAction = 'edit' | 'move' | 'reorder' | 'duplicate' | 'split' | 'merge' | 'regenerate' | 'delete';

const ORDER: Record<string, number> = { Requirement: 0, Epic: 1, Feature: 2, Story: 3, Task: 4 };

type Props = {
  baseUrl: string;
  projectId: string;
  actor: string;
  items: PlanningCenterItem[];
  selectedId: string;
  busy: boolean;
  canEdit: boolean;
  onSelect: (id: string) => void;
  onAction: (action: NodeAction, payload: Record<string, unknown>) => Promise<void>;
  onChanged: () => Promise<void>;
  onError: (message: string) => void;
};

export function PlanningHierarchy({ baseUrl, projectId, actor, items, selectedId, busy, canEdit, onSelect, onAction, onChanged, onError }: Props) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState('');
  const [type, setType] = useState('');
  const [status, setStatus] = useState('');
  const [menuId, setMenuId] = useState('');
  const [mode, setMode] = useState<'edit' | 'move' | 'split' | 'merge' | ''>('');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [storyPoints, setStoryPoints] = useState('');
  const [dependencies, setDependencies] = useState('');
  const [parentId, setParentId] = useState('');
  const [splitTitles, setSplitTitles] = useState('');
  const [draggedId, setDraggedId] = useState('');
  const [drawerStoryId, setDrawerStoryId] = useState('');
  const selected = items.find((item) => item.id === selectedId) || items[0];
  const tree = useMemo(() => buildTree(items), [items]);
  const visibleIds = useMemo(() => matchedIds(items, query, type, status), [items, query, type, status]);
  const rows = useMemo(() => flatten(tree, expanded, visibleIds), [tree, expanded, visibleIds]);
  const parents = useMemo(() => selected ? items.filter((item) => ORDER[item.type] === ORDER[selected.type] - 1) : [], [items, selected]);
  const mergeable = useMemo(() => {
    const values = items.filter((item) => checked.has(item.id));
    return values.length > 1 && new Set(values.map((item) => `${item.type}|${item.parentId}`)).size === 1;
  }, [checked, items]);

  useEffect(() => {
    if (!expanded.size && tree.length) setExpanded(new Set(tree.map((item) => item.id)));
  }, [tree]);
  useEffect(() => {
    if (!selected) return;
    setTitle(selected.title); setDescription(selected.description); setStoryPoints(String(selected.storyPoints || ''));
    setDependencies(selected.dependencies.join('\n')); setParentId(selected.parentId); setMode(''); setMenuId('');
  }, [selected?.id, selected?.version]);

  function toggleExpanded(id: string) {
    setExpanded((current) => { const next = new Set(current); if (next.has(id)) next.delete(id); else next.add(id); return next; });
  }
  function toggleChecked(id: string) {
    setChecked((current) => { const next = new Set(current); if (next.has(id)) next.delete(id); else next.add(id); return next; });
  }
  function openEditor(nextMode: typeof mode, item: PlanningCenterItem) {
    if (nextMode === 'edit' && item.type === 'Story') {
      onSelect(item.id); setDrawerStoryId(item.id); setMode(''); setMenuId(''); return;
    }
    onSelect(item.id); setMode(nextMode); setMenuId('');
  }
  function selectNode(item: PlanningCenterItem) {
    onSelect(item.id);
    setDrawerStoryId(item.type === 'Story' ? item.id : '');
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!selected || !mode) return;
    if (mode === 'edit') await onAction('edit', {
      nodeId: selected.id, expectedVersion: selected.version, title, description,
      storyPoints: Number(storyPoints || 0), dependencies: dependencies.split('\n').map((value) => value.trim()).filter(Boolean),
    });
    if (mode === 'move') await onAction('move', { nodeId: selected.id, expectedVersion: selected.version, parentId, order: nodeOrder(selected) });
    if (mode === 'split') await onAction('split', { nodeId: selected.id, titles: splitTitles.split('\n').map((value) => value.trim()).filter(Boolean), archiveOriginal: true });
    if (mode === 'merge') await onAction('merge', { nodeId: selected.id, nodeIds: Array.from(checked), title });
  }
  async function dropOn(target: PlanningCenterItem) {
    const dragged = items.find((item) => item.id === draggedId);
    setDraggedId('');
    if (!dragged || dragged.id === target.id) return;
    if (dragged.type === target.type) {
      await onAction('reorder', { nodeId: dragged.id, expectedVersion: dragged.version, parentId: target.parentId, order: nodeOrder(target) });
      return;
    }
    if (ORDER[dragged.type] === ORDER[target.type] + 1) {
      await onAction('move', { nodeId: dragged.id, expectedVersion: dragged.version, parentId: target.id, order: target.childCount });
      return;
    }
    await onAction('move', { nodeId: dragged.id, expectedVersion: dragged.version, parentId: target.id, order: 0 });
  }

  if (!selected) return <div className="hei-planning-empty"><strong>No hierarchy is available.</strong><span>Generate a Planning Pack to begin hierarchy review.</span></div>;
  return <div className="hei-hierarchy-editor">
    <section className="hei-hierarchy-main">
      <div className="hei-hierarchy-filters" role="search">
        <label><span>Search</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Find title, dependency, or description" /></label>
        <label><span>Type</span><select value={type} onChange={(event) => setType(event.target.value)}><option value="">All types</option>{Object.keys(ORDER).map((value) => <option key={value}>{value}</option>)}</select></label>
        <label><span>Status</span><select value={status} onChange={(event) => setStatus(event.target.value)}><option value="">All statuses</option>{Array.from(new Set(items.map((item) => item.status))).sort().map((value) => <option key={value}>{value}</option>)}</select></label>
      </div>
      <div className="hei-hierarchy-toolbar"><div><strong>Planning Hierarchy</strong><span>{rows.length} visible · {checked.size} selected</span></div><div>
        <button type="button" onClick={() => setExpanded(new Set(items.filter((item) => item.childCount).map((item) => item.id)))}>Expand All</button>
        <button type="button" onClick={() => setExpanded(new Set())}>Collapse All</button>
        <button type="button" disabled={!mergeable || busy || !canEdit} onClick={() => { setTitle(items.filter((item) => checked.has(item.id)).map((item) => item.title).join(' / ')); setMode('merge'); }}>Merge Selected</button>
      </div></div>
      <div className="hei-hierarchy-tree" role="tree" aria-multiselectable="true">
        {rows.map(({ item, level, hasChildren }) => { const editable = canEdit && item.source === 'planning_artifact' && ['Draft', 'Review'].includes(item.status); return <div
          key={item.id} role="treeitem" aria-level={level + 1} aria-expanded={hasChildren ? expanded.has(item.id) : undefined}
          aria-selected={selected.id === item.id} draggable={editable}
          onDragStart={() => setDraggedId(item.id)} onDragOver={(event) => event.preventDefault()} onDrop={() => void dropOn(item)}
          className={`hei-hierarchy-node ${selected.id === item.id ? 'selected' : ''} ${draggedId === item.id ? 'dragging' : ''}`}
          style={{ '--tree-level': level } as React.CSSProperties}
        >
          <button className="hei-hierarchy-toggle" type="button" disabled={!hasChildren} onClick={() => toggleExpanded(item.id)}>{hasChildren ? (expanded.has(item.id) ? '−' : '+') : '·'}</button>
          <input type="checkbox" checked={checked.has(item.id)} onChange={() => toggleChecked(item.id)} aria-label={`Select ${item.title}`} />
          <button className="hei-hierarchy-node-body" type="button" onClick={() => selectNode(item)}>
            <span className="hei-hierarchy-node-title"><span className="hei-type-badge">{item.type}</span><strong>{item.title}</strong></span>
            <span className="hei-hierarchy-node-status"><Status value={item.status} /><Status value={item.approvalStatus} /></span>
            <span className="hei-hierarchy-node-facts"><small>{item.storyPoints ? `${item.storyPoints} points` : 'Estimate pending'}</small><small>{item.dependencies.length} dependencies</small><small>{item.confidence}% AI confidence</small></span>
          </button>
          <div className="hei-hierarchy-menu-wrap"><button type="button" aria-label={`Actions for ${item.title}`} aria-expanded={menuId === item.id} onClick={() => setMenuId(menuId === item.id ? '' : item.id)}>...</button>{menuId === item.id ? <div className="hei-hierarchy-menu" role="menu">
            <button type="button" disabled={!editable} onClick={() => openEditor('edit', item)}>Edit</button>
            <button type="button" disabled={!editable} onClick={() => void onAction('regenerate', { nodeId: item.id })}>Regenerate</button>
            <button type="button" disabled={!editable} onClick={() => { setSplitTitles(`${item.title} - Part 1\n${item.title} - Part 2`); openEditor('split', item); }}>Split</button>
            <button type="button" disabled={!editable || !mergeable} onClick={() => openEditor('merge', item)}>Merge</button>
            <button type="button" disabled={!editable} onClick={() => void onAction('duplicate', { nodeId: item.id })}>Duplicate</button>
            <button type="button" disabled={!editable || item.type === 'Requirement'} onClick={() => openEditor('move', item)}>Move</button>
            <button className="danger" type="button" disabled={!editable} onClick={() => { if (window.confirm(`Archive ${item.title}${item.childCount ? ' and its children' : ''}?`)) void onAction('delete', { nodeId: item.id, cascade: true }); }}>Delete</button>
          </div> : null}</div>
        </div>; })}
      </div>
    </section>
    {drawerStoryId ? <StoryDetailDrawer
      baseUrl={baseUrl} projectId={projectId} storyId={drawerStoryId} actor={actor} canEdit={canEdit}
      onClose={() => setDrawerStoryId('')}
      onChanged={onChanged}
      onDeleted={() => { setDrawerStoryId(''); const parent = items.find((item) => item.id === selected?.parentId); if (parent) onSelect(parent.id); }}
      onError={onError}
    /> : <aside className="hei-hierarchy-inspector">
      <header><span>{selected.type}</span><h3>{selected.title}</h3><Status value={selected.status} /></header>
      {!mode ? <>
        <p>{selected.description}</p>
        <div className="hei-hierarchy-inspector-facts"><Fact label="Estimate" value={selected.storyPoints ? `${selected.storyPoints} points` : 'Pending'} /><Fact label="Dependencies" value={selected.dependencies.length} /><Fact label="AI Confidence" value={`${selected.confidence}%`} /><Fact label="Children" value={selected.childCount} /></div>
        <div className="hei-hierarchy-inspector-actions"><button type="button" onClick={() => setMode('edit')} disabled={!canEdit || selected.source !== 'planning_artifact' || !['Draft', 'Review'].includes(selected.status)}>Manual Edit</button><button type="button" onClick={() => void onAction('regenerate', { nodeId: selected.id })} disabled={!canEdit || busy || selected.source !== 'planning_artifact' || !['Draft', 'Review'].includes(selected.status)}>AI Regenerate</button><button type="button" onClick={() => setMode('move')} disabled={!canEdit || selected.type === 'Requirement' || selected.source !== 'planning_artifact' || !['Draft', 'Review'].includes(selected.status)}>Move</button><button type="button" onClick={() => void onAction('duplicate', { nodeId: selected.id })} disabled={!canEdit || selected.source !== 'planning_artifact' || !['Draft', 'Review'].includes(selected.status)}>Duplicate</button></div>
      </> : <form className="hei-hierarchy-form" onSubmit={(event) => void submit(event)}>
        {mode === 'edit' ? <><label><span>Title</span><input required value={title} onChange={(event) => setTitle(event.target.value)} /></label><label><span>Description</span><textarea required value={description} onChange={(event) => setDescription(event.target.value)} /></label><label><span>Story Points</span><input type="number" min="0" value={storyPoints} onChange={(event) => setStoryPoints(event.target.value)} /></label><label><span>Dependencies</span><textarea value={dependencies} onChange={(event) => setDependencies(event.target.value)} placeholder="One dependency per line" /></label></> : null}
        {mode === 'move' ? <label><span>New Parent</span><select required value={parentId} onChange={(event) => setParentId(event.target.value)}><option value="">Select {ORDER[selected.type] ? Object.keys(ORDER)[ORDER[selected.type] - 1] : 'parent'}</option>{parents.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label> : null}
        {mode === 'split' ? <label><span>New Node Titles</span><textarea required value={splitTitles} onChange={(event) => setSplitTitles(event.target.value)} /><small>Enter one title per line. The original node will be archived.</small></label> : null}
        {mode === 'merge' ? <><label><span>Merged Title</span><input required value={title} onChange={(event) => setTitle(event.target.value)} /></label><p>{checked.size} sibling nodes selected.</p></> : null}
        <div><button className="planner-button primary" type="submit" disabled={busy}>{busy ? 'Saving...' : mode === 'edit' ? 'Save Changes' : mode === 'move' ? 'Move Node' : mode === 'split' ? 'Split Node' : 'Merge Nodes'}</button><button className="planner-button secondary" type="button" onClick={() => setMode('')}>Cancel</button></div>
      </form>}
    </aside>}
  </div>;
}

function buildTree(items: PlanningCenterItem[]): TreeNode[] {
  const nodes = new Map(items.map((item) => [item.id, { ...item, children: [] } as TreeNode]));
  const sourceIds = new Map(items.filter((item) => item.sourceItemId).map((item) => [item.sourceItemId, item.id]));
  const roots: TreeNode[] = [];
  nodes.forEach((node) => {
    const parent = nodes.get(node.parentId) || nodes.get(sourceIds.get(node.parentId) || '');
    if (parent && parent.id !== node.id) parent.children.push(node); else roots.push(node);
  });
  const sort = (values: TreeNode[]) => values.sort((left, right) => nodeOrder(left) - nodeOrder(right) || left.title.localeCompare(right.title)).forEach((item) => sort(item.children));
  sort(roots); return roots;
}

function flatten(tree: TreeNode[], expanded: Set<string>, visible: Set<string>): Array<{ item: TreeNode; level: number; hasChildren: boolean }> {
  const output: Array<{ item: TreeNode; level: number; hasChildren: boolean }> = [];
  const visit = (values: TreeNode[], level: number) => values.forEach((item) => {
    if (!visible.has(item.id)) return;
    output.push({ item, level, hasChildren: item.children.some((child) => visible.has(child.id)) });
    if (expanded.has(item.id)) visit(item.children, level + 1);
  });
  visit(tree, 0); return output;
}

function matchedIds(items: PlanningCenterItem[], query: string, type: string, status: string): Set<string> {
  const text = query.trim().toLowerCase();
  const matches = items.filter((item) => (!type || item.type === type) && (!status || item.status === status) && (!text || `${item.title} ${item.description} ${item.dependencies.join(' ')}`.toLowerCase().includes(text)));
  const byId = new Map(items.map((item) => [item.id, item]));
  const sourceIds = new Map(items.filter((item) => item.sourceItemId).map((item) => [item.sourceItemId, item]));
  const visible = new Set(matches.map((item) => item.id));
  matches.forEach((item) => { let parent = byId.get(item.parentId) || sourceIds.get(item.parentId); while (parent && !visible.has(parent.id)) { visible.add(parent.id); parent = byId.get(parent.parentId) || sourceIds.get(parent.parentId); } });
  return visible;
}

function nodeOrder(item: PlanningCenterItem): number { return Number(item.details?.order || 0); }
function Status({ value }: { value: string }) { return <span className={`hei-status-badge status-${value.toLowerCase().replace(/[^a-z]+/g, '-')}`}>{value}</span>; }
function Fact({ label, value }: { label: string; value: string | number }) { return <div><span>{label}</span><strong>{value}</strong></div>; }
