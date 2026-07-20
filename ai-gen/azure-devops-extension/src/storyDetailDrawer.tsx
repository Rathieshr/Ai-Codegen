import React, { useEffect, useState } from 'react';

type TaskEstimate = { engineeringHours: number; engineeringDays: number; confidence: number };
type StoryChild = {
  id: string; title: string; description?: string; status: string; confidence?: number; version?: number; editable?: boolean;
  category?: string; estimate?: TaskEstimate; owner?: string; priority?: string; taskStatus?: string; dependencies?: string[];
  source?: string; artifactId?: string; artifactVersion?: number;
};
type RelatedStory = { id: string; title: string; status: string; confidence: number; selected?: boolean };
type StoryDetail = {
  id: string; title: string; description: string; status: string; approvalStatus: string; version: number; editable: boolean;
  acceptanceCriteria: string[]; businessRules: string[]; dependencies: string[];
  estimate: { engineeringDays: number; engineeringHours: number; storyPoints: number; confidence: number };
  storyPoints: number; risks: string[]; risk: string; repositoryModules: string[]; relatedStories: RelatedStory[];
  generatedTasks: StoryChild[]; generatedTests: StoryChild[]; engineeringNotes: string[]; updatedAt: string;
};

type Props = {
  baseUrl: string; projectId: string; storyId: string; actor: string; canEdit: boolean;
  onClose: () => void; onChanged: () => Promise<void>; onDeleted: () => void; onError: (message: string) => void;
};

export function StoryDetailDrawer({ baseUrl, projectId, storyId, actor, canEdit, onClose, onChanged, onDeleted, onError }: Props) {
  const [story, setStory] = useState<StoryDetail>();
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');
  const [draft, setDraft] = useState<StoryDetail>();
  const [taskBusy, setTaskBusy] = useState('');
  const [showManualTask, setShowManualTask] = useState(false);
  const [selectedTasks, setSelectedTasks] = useState<string[]>([]);
  const [manualTask, setManualTask] = useState<StoryChild>(() => emptyTask());

  useEffect(() => { void load(); }, [storyId, projectId]);

  async function load() {
    setLoading(true);
    try {
      const params = new URLSearchParams(); if (projectId) params.set('projectId', projectId);
      const response = await fetch(`${baseUrl}/story/${encodeURIComponent(storyId)}?${params.toString()}`);
      const result = await response.json() as StoryDetail & { error?: { message?: string } };
      if (!response.ok) throw new Error(result.error?.message || 'Unable to load Story details.');
      setStory(result); setDraft(cloneStory(result));
    } catch (error) { onError(error instanceof Error ? error.message : 'Unable to load Story details.'); }
    finally { setLoading(false); }
  }

  async function request(action: 'save' | 'regenerate' | 'tasks' | 'tests' | 'delete') {
    if (!draft) return;
    setBusy(action);
    try {
      const paths = { save: '', regenerate: '/regenerate', tasks: '/regenerate-tasks', tests: '/generate-tests', delete: '' };
      const method = action === 'save' ? 'PUT' : action === 'delete' ? 'DELETE' : 'POST';
      const params = new URLSearchParams({ actor }); if (projectId) params.set('projectId', projectId);
      const body = action === 'save' ? {
        title: draft.title, description: draft.description, expectedVersion: draft.version,
        acceptanceCriteria: draft.acceptanceCriteria, businessRules: draft.businessRules,
        dependencies: draft.dependencies, estimate: draft.estimate, storyPoints: draft.storyPoints, risks: draft.risks,
        repositoryModules: draft.repositoryModules, relatedStoryIds: draft.relatedStories.filter((item) => item.selected).map((item) => item.id),
        generatedTasks: draft.generatedTasks, generatedTests: draft.generatedTests, engineeringNotes: draft.engineeringNotes,
      } : {};
      const response = await fetch(`${baseUrl}/story/${encodeURIComponent(storyId)}${paths[action]}?${params.toString()}`, {
        method, headers: { 'Content-Type': 'application/json' }, body: action === 'delete' ? undefined : JSON.stringify(body),
      });
      const result = await response.json() as StoryDetail & { story?: StoryDetail; error?: { message?: string } };
      if (!response.ok) throw new Error(result.error?.message || `Unable to ${action} Story.`);
      if (action === 'delete') { onDeleted(); await onChanged(); return; }
      const next = result.story || result;
      setStory(next); setDraft(cloneStory(next)); await onChanged();
    } catch (error) { onError(error instanceof Error ? error.message : `Unable to ${action} Story.`); }
    finally { setBusy(''); }
  }

  async function createTasks(mode: 'manual' | 'ai') {
    setTaskBusy(mode);
    try {
      const params = new URLSearchParams({ actor });
      const body = mode === 'manual' ? { mode, ...manualTask } : { mode };
      const response = await fetch(`${baseUrl}/story/${encodeURIComponent(storyId)}/tasks?${params.toString()}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      });
      const result = await response.json() as { error?: { message?: string } };
      if (!response.ok) throw new Error(result.error?.message || `Unable to ${mode === 'ai' ? 'generate' : 'add'} Tasks.`);
      setManualTask(emptyTask()); setShowManualTask(false); await load(); await onChanged();
    } catch (error) { onError(error instanceof Error ? error.message : 'Unable to create Tasks.'); }
    finally { setTaskBusy(''); }
  }

  async function taskAction(taskId: string, action: 'edit' | 'regenerate' | 'split' | 'merge', payload: Record<string, unknown> = {}) {
    setTaskBusy(`${action}:${taskId}`);
    try {
      const params = new URLSearchParams({ actor });
      const response = await fetch(`${baseUrl}/task/${encodeURIComponent(taskId)}?${params.toString()}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action, ...payload }),
      });
      const result = await response.json() as { error?: { message?: string } };
      if (!response.ok) throw new Error(result.error?.message || `Unable to ${action} Task.`);
      setSelectedTasks([]); await load(); await onChanged();
    } catch (error) { onError(error instanceof Error ? error.message : `Unable to ${action} Task.`); }
    finally { setTaskBusy(''); }
  }

  async function deleteTask(task: StoryChild) {
    if (!window.confirm(`Delete ${task.title}?`)) return;
    setTaskBusy(`delete:${task.id}`);
    try {
      const params = new URLSearchParams({ actor });
      const response = await fetch(`${baseUrl}/task/${encodeURIComponent(task.id)}?${params.toString()}`, { method: 'DELETE' });
      const result = await response.json() as { error?: { message?: string } };
      if (!response.ok) throw new Error(result.error?.message || 'Unable to delete Task.');
      setSelectedTasks((current) => current.filter((id) => id !== task.id)); await load(); await onChanged();
    } catch (error) { onError(error instanceof Error ? error.message : 'Unable to delete Task.'); }
    finally { setTaskBusy(''); }
  }

  function splitTask(task: StoryChild) {
    const value = window.prompt('Enter two or more Task titles, one per line.', `${task.title} - Part 1\n${task.title} - Part 2`);
    if (!value) return;
    const titles = lines(value);
    if (titles.length < 2) { onError('Split requires at least two Task titles.'); return; }
    void taskAction(task.id, 'split', { titles });
  }

  function mergeTasks() {
    if (selectedTasks.length < 2) { onError('Select at least two sibling Tasks to merge.'); return; }
    const tasks = draft?.generatedTasks.filter((task) => selectedTasks.includes(task.id)) || [];
    const title = window.prompt('Merged Task title', tasks.map((task) => task.title).join(' / '));
    if (!title) return;
    void taskAction(selectedTasks[0], 'merge', { taskIds: selectedTasks, title });
  }

  const editable = Boolean(canEdit && story?.editable);
  return <aside className="hei-story-drawer" aria-label="Story Detail Drawer">
    <header><div><span>Story Detail</span><h3>{story?.title || 'Loading Story...'}</h3></div><button type="button" onClick={onClose} aria-label="Close Story details">Close</button></header>
    {loading || !draft ? <div className="hei-story-drawer-state"><strong>Loading Story details...</strong><span>Resolving planning, repository, task, and test lineage.</span></div> : <>
      <div className="hei-story-drawer-meta"><Badge value={draft.status} /><Badge value={draft.approvalStatus} /><span>v{draft.version}</span><span>{draft.estimate.confidence}% confidence</span></div>
      {!editable ? <div className="hei-story-drawer-notice">Approved Story content is read-only. Draft Tasks can still be planned and approved independently.</div> : null}
      <div className="hei-story-drawer-body">
        <Field label="Story Title"><input value={draft.title} disabled={!editable} onChange={(event) => patch(setDraft, { title: event.target.value })} /></Field>
        <Field label="Description"><textarea value={draft.description} disabled={!editable} onChange={(event) => patch(setDraft, { description: event.target.value })} /></Field>
        <ListEditor label="Acceptance Criteria" values={draft.acceptanceCriteria} disabled={!editable} onChange={(acceptanceCriteria) => patch(setDraft, { acceptanceCriteria })} />
        <ListEditor label="Business Rules" values={draft.businessRules} disabled={!editable} onChange={(businessRules) => patch(setDraft, { businessRules })} />
        <ListEditor label="Dependencies" values={draft.dependencies} disabled={!editable} onChange={(dependencies) => patch(setDraft, { dependencies })} />
        <section className="hei-story-drawer-grid"><Field label="Engineering Days"><input type="number" min="0" step="0.5" value={draft.estimate.engineeringDays} disabled={!editable} onChange={(event) => patch(setDraft, { estimate: { ...draft.estimate, engineeringDays: Number(event.target.value || 0) } })} /></Field><Field label="Engineering Hours"><input type="number" min="0" step="0.5" value={draft.estimate.engineeringHours} disabled={!editable} onChange={(event) => patch(setDraft, { estimate: { ...draft.estimate, engineeringHours: Number(event.target.value || 0) } })} /></Field><Field label="Story Points"><input type="number" min="0" value={draft.storyPoints} disabled={!editable} onChange={(event) => patch(setDraft, { storyPoints: Number(event.target.value || 0), estimate: { ...draft.estimate, storyPoints: Number(event.target.value || 0) } })} /></Field><Metric label="Risk" value={draft.risk} /></section>
        <ListEditor label="Risks" values={draft.risks} disabled={!editable} onChange={(risks) => patch(setDraft, { risks })} />
        <ListEditor label="Repository Modules" values={draft.repositoryModules} disabled={!editable} onChange={(repositoryModules) => patch(setDraft, { repositoryModules })} />
        <section className="hei-story-drawer-section"><h4>Related Stories</h4>{draft.relatedStories.length ? draft.relatedStories.map((item, index) => <label className="hei-story-related" key={item.id}><input type="checkbox" checked={Boolean(item.selected)} disabled={!editable} onChange={(event) => patch(setDraft, { relatedStories: draft.relatedStories.map((value, valueIndex) => valueIndex === index ? { ...value, selected: event.target.checked } : value) })} /><span>{item.title}</span><Badge value={item.status} /></label>) : <p>No related sibling Stories identified.</p>}</section>
        <TaskWorkspace
          tasks={draft.generatedTasks} disabled={!canEdit} busy={taskBusy} selected={selectedTasks}
          showManual={showManualTask} manualTask={manualTask}
          onToggleManual={() => setShowManualTask((value) => !value)} onManualChange={setManualTask}
          onCreateManual={() => void createTasks('manual')} onGenerate={() => void createTasks('ai')}
          onSelect={(id, checked) => setSelectedTasks((current) => checked ? [...new Set([...current, id])] : current.filter((value) => value !== id))}
          onChange={(generatedTasks) => patch(setDraft, { generatedTasks })}
          onSave={(task) => void taskAction(task.id, 'edit', { ...task, expectedVersion: task.version })}
          onRegenerate={(task) => void taskAction(task.id, 'regenerate')}
          onSplit={splitTask} onDelete={(task) => void deleteTask(task)} onMerge={mergeTasks}
        />
        <ChildEditor title="Generated Tests" values={draft.generatedTests} disabled={!editable} onChange={(generatedTests) => patch(setDraft, { generatedTests })} empty="No Tests generated yet." />
        <ListEditor label="Engineering Notes" values={draft.engineeringNotes} disabled={!editable} onChange={(engineeringNotes) => patch(setDraft, { engineeringNotes })} />
      </div>
      <footer>
        <button className="planner-button primary" type="button" disabled={!editable || Boolean(busy)} onClick={() => void request('save')}>{busy === 'save' ? 'Saving...' : 'Save'}</button>
        <button type="button" disabled={!editable || Boolean(busy)} onClick={() => void request('regenerate')}>Regenerate Story</button>
        <button type="button" disabled={!editable || Boolean(busy)} onClick={() => void request('tests')}>Generate Tests</button>
        <button className="danger" type="button" disabled={!editable || Boolean(busy)} onClick={() => { if (window.confirm(`Delete ${draft.title} and its generated children?`)) void request('delete'); }}>Delete</button>
      </footer>
    </>}
  </aside>;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) { return <label className="hei-story-field"><span>{label}</span>{children}</label>; }
function ListEditor({ label, values, disabled, onChange }: { label: string; values: string[]; disabled: boolean; onChange: (values: string[]) => void }) { return <Field label={label}><textarea value={values.join('\n')} disabled={disabled} onChange={(event) => onChange(lines(event.target.value))} placeholder="One item per line" /></Field>; }
function Metric({ label, value }: { label: string; value: string }) { return <div className="hei-story-metric"><span>{label}</span><strong>{value}</strong></div>; }
function TaskWorkspace({ tasks, disabled, busy, selected, showManual, manualTask, onToggleManual, onManualChange, onCreateManual, onGenerate, onSelect, onChange, onSave, onRegenerate, onSplit, onDelete, onMerge }: {
  tasks: StoryChild[]; disabled: boolean; busy: string; selected: string[]; showManual: boolean; manualTask: StoryChild;
  onToggleManual: () => void; onManualChange: (task: StoryChild) => void; onCreateManual: () => void; onGenerate: () => void;
  onSelect: (id: string, checked: boolean) => void; onChange: (tasks: StoryChild[]) => void; onSave: (task: StoryChild) => void;
  onRegenerate: (task: StoryChild) => void; onSplit: (task: StoryChild) => void; onDelete: (task: StoryChild) => void; onMerge: () => void;
}) {
  const update = (index: number, value: Partial<StoryChild>) => onChange(tasks.map((task, taskIndex) => taskIndex === index ? { ...task, ...value } : task));
  return <section className="hei-story-drawer-section hei-task-workspace">
    <header><div><h4>Implementation Tasks</h4><p>Draft Tasks stay editable until approval.</p></div><div><button type="button" disabled={disabled || Boolean(busy)} onClick={onToggleManual}>{showManual ? 'Cancel' : 'Add Manual Task'}</button><button className="planner-button primary" type="button" disabled={disabled || Boolean(busy)} onClick={onGenerate}>{busy === 'ai' ? 'Generating...' : tasks.length ? 'Regenerate Tasks' : 'Generate AI Tasks'}</button></div></header>
    {showManual ? <div className="hei-task-manual"><TaskFields task={manualTask} disabled={false} onChange={(value) => onManualChange({ ...manualTask, ...value })} /><button className="planner-button primary" type="button" disabled={!manualTask.title.trim() || Boolean(busy)} onClick={onCreateManual}>{busy === 'manual' ? 'Adding...' : 'Add Task'}</button></div> : null}
    {selected.length > 1 ? <div className="hei-task-selection"><span>{selected.length} Tasks selected</span><button type="button" disabled={Boolean(busy)} onClick={onMerge}>Merge Selected</button></div> : null}
    {tasks.length ? <div className="hei-task-grid">{tasks.map((task, index) => {
      const locked = disabled || task.editable === false || Boolean(busy);
      return <article className="hei-task-card" key={task.id}>
        <header><label><input type="checkbox" checked={selected.includes(task.id)} disabled={locked} onChange={(event) => onSelect(task.id, event.target.checked)} aria-label={`Select ${task.title}`} /><span>{task.category || 'Backend'}</span></label><Badge value={task.taskStatus || task.status} /></header>
        <TaskFields task={task} disabled={locked} onChange={(value) => update(index, value)} />
        <footer><button type="button" disabled={locked} onClick={() => onSave(task)}>Save</button><button type="button" disabled={locked} onClick={() => onRegenerate(task)}>Regenerate</button><button type="button" disabled={locked} onClick={() => onSplit(task)}>Split</button><button className="danger" type="button" disabled={locked} onClick={() => onDelete(task)}>Delete</button></footer>
      </article>;
    })}</div> : <div className="hei-task-empty"><strong>No Tasks generated yet.</strong><span>Add a manual Task or generate implementation Tasks from this Story.</span></div>}
  </section>;
}
function TaskFields({ task, disabled, onChange }: { task: StoryChild; disabled: boolean; onChange: (value: Partial<StoryChild>) => void }) {
  const estimate = task.estimate || { engineeringHours: 0, engineeringDays: 0, confidence: 0 };
  return <div className="hei-task-fields">
    <input aria-label="Task title" value={task.title} disabled={disabled} onChange={(event) => onChange({ title: event.target.value })} placeholder="Task title" />
    <textarea aria-label={`${task.title || 'Task'} description`} value={task.description || ''} disabled={disabled} onChange={(event) => onChange({ description: event.target.value })} placeholder="Implementation-ready description" />
    <select aria-label={`${task.title || 'Task'} category`} value={task.category || 'Backend'} disabled={disabled} onChange={(event) => onChange({ category: event.target.value })}>{TASK_CATEGORIES.map((value) => <option key={value}>{value}</option>)}</select>
    <input aria-label={`${task.title || 'Task'} estimate`} type="number" min="0" step="0.5" value={estimate.engineeringHours} disabled={disabled} onChange={(event) => { const hours = Number(event.target.value || 0); onChange({ estimate: { ...estimate, engineeringHours: hours, engineeringDays: hours / 8 } }); }} placeholder="Hours" />
    <input aria-label={`${task.title || 'Task'} owner`} value={task.owner || 'Unassigned'} disabled={disabled} onChange={(event) => onChange({ owner: event.target.value })} placeholder="Owner" />
    <select aria-label={`${task.title || 'Task'} priority`} value={task.priority || 'Medium'} disabled={disabled} onChange={(event) => onChange({ priority: event.target.value })}>{['Critical', 'High', 'Medium', 'Low'].map((value) => <option key={value}>{value}</option>)}</select>
    <select aria-label={`${task.title || 'Task'} status`} value={task.taskStatus || 'To Do'} disabled={disabled} onChange={(event) => onChange({ taskStatus: event.target.value })}>{['To Do', 'In Progress', 'Blocked', 'Done'].map((value) => <option key={value}>{value}</option>)}</select>
    <textarea aria-label={`${task.title || 'Task'} dependencies`} value={(task.dependencies || []).join('\n')} disabled={disabled} onChange={(event) => onChange({ dependencies: lines(event.target.value) })} placeholder="Dependencies, one per line" />
  </div>;
}
function ChildEditor({ title, values, disabled, onChange, empty }: { title: string; values: StoryChild[]; disabled: boolean; onChange: (values: StoryChild[]) => void; empty: string }) { return <section className="hei-story-drawer-section"><h4>{title}</h4>{values.length ? values.map((item, index) => <div className="hei-story-child" key={`${item.id}-${index}`}><input aria-label={`${title} title`} value={item.title} disabled={disabled || item.editable === false} onChange={(event) => onChange(values.map((value, valueIndex) => valueIndex === index ? { ...value, title: event.target.value } : value))} />{item.description !== undefined ? <textarea aria-label={`${item.title} description`} value={item.description} disabled={disabled || item.editable === false} onChange={(event) => onChange(values.map((value, valueIndex) => valueIndex === index ? { ...value, description: event.target.value } : value))} /> : null}{item.category !== undefined ? <input aria-label={`${item.title} category`} value={item.category} disabled={disabled || item.editable === false} onChange={(event) => onChange(values.map((value, valueIndex) => valueIndex === index ? { ...value, category: event.target.value } : value))} /> : null}<Badge value={item.status} /></div>) : <p>{empty}</p>}</section>; }
function Badge({ value }: { value: string }) { return <span className={`hei-status-badge status-${value.toLowerCase().replace(/[^a-z]+/g, '-')}`}>{value}</span>; }
function lines(value: string): string[] { return value.split('\n').map((item) => item.trim()).filter(Boolean); }
function patch(setter: React.Dispatch<React.SetStateAction<StoryDetail | undefined>>, value: Partial<StoryDetail>) { setter((current) => current ? { ...current, ...value } : current); }
function cloneStory(value: StoryDetail): StoryDetail { return JSON.parse(JSON.stringify(value)) as StoryDetail; }
const TASK_CATEGORIES = ['Frontend', 'Backend', 'Database', 'API', 'Testing', 'Documentation', 'Deployment', 'Infrastructure'];
function emptyTask(): StoryChild { return { id: '', title: '', description: '', status: 'Draft', category: 'Backend', estimate: { engineeringHours: 0, engineeringDays: 0, confidence: 0 }, owner: 'Unassigned', priority: 'Medium', taskStatus: 'To Do', dependencies: [], source: 'manual', editable: true }; }
