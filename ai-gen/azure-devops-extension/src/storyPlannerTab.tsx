import * as SDK from 'azure-devops-extension-sdk';
import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  approvePlannerStage,
  createAzureDevOpsItems,
  editPlannerStage,
  getCurrentWorkItemContext,
  loadCreationPreview,
  loadPlannerSession,
  regeneratePlannerStage,
  startPlannerSession,
  storeCreationResult,
} from './storyPlannerApi';
import { CreationPreview, PlannerSession, PlannerStage, PlannerViewState } from './storyPlannerTypes';
import './storyPlanner.css';

const SESSION_KEY = 'ai-story-planner:session-id';

function StoryPlannerTab() {
  const [view, setView] = useState<PlannerViewState>({
    loading: true,
    loadingMessage: 'Loading AI Story Planner...',
    error: '',
  });
  const [requirement, setRequirement] = useState('');
  const [activeInput, setActiveInput] = useState('');

  useEffect(() => {
    SDK.init({ loaded: false, applyTheme: true });
    SDK.ready().then(async () => {
      SDK.notifyLoadSucceeded();
      try {
        const workItem = await getCurrentWorkItemContext();
        const sessionId = window.sessionStorage.getItem(SESSION_KEY) || '';
        let session: PlannerSession | undefined;
        if (sessionId) {
          try {
            session = await loadPlannerSession(sessionId);
          } catch {
            window.sessionStorage.removeItem(SESSION_KEY);
          }
        }
        setRequirement(session?.requirement || buildSeedRequirement(workItem));
        setView({
          loading: false,
          loadingMessage: '',
          error: '',
          session,
          workItem,
        });
      } catch (error) {
        setView({
          loading: false,
          loadingMessage: '',
          error: error instanceof Error ? error.message : 'Unable to load AI Story Planner.',
        });
        void SDK.notifyLoadSucceeded();
      }
    }).catch((error) => {
      const message = error instanceof Error ? error.message : 'Unable to initialize Azure DevOps SDK.';
      setView({
        loading: false,
        loadingMessage: '',
        error: message,
      });
      void SDK.notifyLoadFailed(message);
    });
  }, []);

  const currentStage = view.session?.current_stage;
  const seedWarning = useMemo(() => {
    if (!view.workItem || view.session) {
      return '';
    }
    const hasDescription = Boolean(cleanText(view.workItem.description));
    const hasAcceptance = Boolean(cleanText(view.workItem.acceptanceCriteria));
    if (!hasDescription && !hasAcceptance) {
      return 'This work item has no description or acceptance criteria yet. Review and confirm the requirement below before starting planning.';
    }
    return '';
  }, [view.workItem, view.session]);
  const steps = useMemo(
    () => [
      { id: 'requirement', label: 'Requirement', done: Boolean(view.session) },
      { id: 'refined_story', label: 'Refined Story', done: Boolean(view.session?.story_approved) },
      { id: 'acceptance_criteria', label: 'Acceptance Criteria', done: Boolean(view.session?.acceptance_approved) },
      { id: 'tasks', label: 'Tasks', done: Boolean(view.session?.tasks_approved) },
      { id: 'azure_devops_creation', label: 'Azure DevOps', done: currentStage === 'success' || currentStage === 'azure_devops_creation' },
      { id: 'success', label: 'Success', done: currentStage === 'success' },
    ],
    [view.session, currentStage]
  );

  async function withLoading<T>(message: string, action: () => Promise<T>) {
    setView((current) => ({ ...current, loading: true, loadingMessage: message, error: '' }));
    try {
      const result = await action();
      setView((current) => ({ ...current, loading: false, loadingMessage: '', error: '' }));
      return result;
    } catch (error) {
      setView((current) => ({
        ...current,
        loading: false,
        loadingMessage: '',
        error: error instanceof Error ? error.message : String(error),
      }));
      return undefined;
    }
  }

  async function start() {
    const session = await withLoading('Generating refined story...', () => startPlannerSession(requirement));
    if (session) {
      window.sessionStorage.setItem(SESSION_KEY, session.session_id);
      setActiveInput('');
      setView((current) => ({ ...current, session }));
    }
  }

  async function saveCurrentStage() {
    if (!view.session) return;
    const stage = view.session.current_stage;
    let payload: Record<string, unknown> = {};
    if (stage === 'refined_story') {
      payload = {
        title: view.session.story.title,
        description: view.session.story.description,
        business_value: view.session.story.business_value,
      };
    } else if (stage === 'acceptance_criteria') {
      payload = { acceptance_criteria: view.session.acceptance_criteria };
    } else if (stage === 'tasks') {
      payload = { tasks: view.session.tasks };
    }
    const session = await withLoading('Saving edits...', () => editPlannerStage(view.session!.session_id, stage, payload));
    if (session) {
      setView((current) => ({ ...current, session }));
    }
  }

  async function regenerate() {
    if (!view.session) return;
    const session = await withLoading('Regenerating stage...', () =>
      regeneratePlannerStage(view.session!.session_id, view.session!.current_stage, activeInput)
    );
    if (session) {
      setActiveInput('');
      setView((current) => ({ ...current, session }));
    }
  }

  async function approve() {
    if (!view.session) return;
    const session = await withLoading('Approving stage...', () =>
      approvePlannerStage(view.session!.session_id, view.session!.current_stage)
    );
    if (session) {
      setActiveInput('');
      setView((current) => ({ ...current, session }));
    }
  }

  async function createItems() {
    if (!view.session || !view.workItem) return;
    const preview = await withLoading('Preparing Azure DevOps work items...', () => loadCreationPreview(view.session!.session_id));
    if (!preview) return;
    setView((current) => ({ ...current, preview }));
    const result = await withLoading('Creating Azure DevOps work items...', () => createAzureDevOpsItems(preview, view.workItem!));
    if (!result) return;
    const session = await withLoading('Saving creation results...', () =>
      storeCreationResult(view.session!.session_id, result)
    );
    if (session) {
      setView((current) => ({ ...current, session, preview }));
    }
  }

  function updateStory(field: 'title' | 'description' | 'business_value', value: string) {
    setView((current) => current.session ? ({
      ...current,
      session: {
        ...current.session,
        story: {
          ...current.session.story,
          [field]: value,
        },
      },
    }) : current);
  }

  function updateAcceptance(value: string) {
    setView((current) => current.session ? ({
      ...current,
      session: {
        ...current.session,
        acceptance_criteria: value.split('\n').map((line) => line.trim()).filter(Boolean),
      },
    }) : current);
  }

  function updateTask(index: number, field: 'title' | 'description' | 'estimated_effort', value: string) {
    setView((current) => {
      if (!current.session) return current;
      const tasks = current.session.tasks.map((task, taskIndex) => taskIndex === index ? { ...task, [field]: value } : task);
      return { ...current, session: { ...current.session, tasks } };
    });
  }

  function renderStageBody(session: PlannerSession) {
    if (session.current_stage === 'refined_story') {
      return (
        <>
          <div className="planner-label">Title</div>
          <input className="planner-input" value={session.story.title} onChange={(event) => updateStory('title', event.target.value)} />
          <div className="planner-label">Description</div>
          <textarea className="planner-textarea" value={session.story.description} onChange={(event) => updateStory('description', event.target.value)} />
          <div className="planner-label">Business Value</div>
          <textarea className="planner-textarea" value={session.story.business_value} onChange={(event) => updateStory('business_value', event.target.value)} />
        </>
      );
    }
    if (session.current_stage === 'acceptance_criteria') {
      return (
        <>
          <div className="planner-label">Acceptance Criteria</div>
          <textarea className="planner-textarea" value={session.acceptance_criteria.join('\n')} onChange={(event) => updateAcceptance(event.target.value)} />
        </>
      );
    }
    if (session.current_stage === 'tasks') {
      return (
        <div className="planner-status-grid">
          {session.tasks.map((task, index) => (
            <div key={task.id} className="planner-task">
              <div className="planner-label">Task Title</div>
              <input className="planner-input" value={task.title} onChange={(event) => updateTask(index, 'title', event.target.value)} />
              <div className="planner-label">Task Description</div>
              <textarea className="planner-textarea" value={task.description} onChange={(event) => updateTask(index, 'description', event.target.value)} />
              <div className="planner-label">Estimated Effort</div>
              <input className="planner-input" value={task.estimated_effort || ''} onChange={(event) => updateTask(index, 'estimated_effort', event.target.value)} />
            </div>
          ))}
        </div>
      );
    }
    if (session.current_stage === 'azure_devops_creation') {
      return renderCreationPreview(view.preview);
    }
    return renderSuccess(session);
  }

  function renderCreationPreview(preview?: CreationPreview) {
    if (!preview) {
      return <div className="planner-subtle">The approved story and tasks are ready to create in Azure DevOps.</div>;
    }
    return (
      <div className="planner-status-grid">
        <div className="planner-task">
          <div className="planner-label">User Story</div>
          <strong>{preview.preview.story.title}</strong>
          <div>{preview.preview.story.description}</div>
          <ul className="planner-list">
            {preview.preview.story.acceptance_criteria.map((item) => <li key={item}>{item}</li>)}
          </ul>
        </div>
        {preview.preview.tasks.map((task) => (
          <div key={task.id} className="planner-task">
            <div className="planner-label">Proposed Task</div>
            <strong>{task.title}</strong>
            <div>{task.description}</div>
            <div className="planner-subtle">Estimated effort: {task.estimated_effort || 'Not set'}</div>
          </div>
        ))}
      </div>
    );
  }

  function renderSuccess(session: PlannerSession) {
    return (
      <div className="planner-status-grid">
        <div className="planner-status-row">
          <span>User Story</span>
          <span>
            {session.created_summary?.story?.status === 'created'
              ? `Created #${session.created_summary?.story?.azure_work_item_id}`
              : `Failed${session.created_summary?.story?.error ? `: ${session.created_summary.story.error}` : ''}`}
          </span>
        </div>
        {(session.created_summary?.tasks || []).map((task) => (
          <div key={`${task.id || task.title}`} className="planner-status-row">
            <span>{task.title}</span>
            <span>{task.status === 'created' ? `Created #${task.azure_work_item_id}` : `Failed${task.error ? `: ${task.error}` : ''}`}</span>
          </div>
        ))}
      </div>
    );
  }

  function renderActions(session: PlannerSession) {
    if (session.current_stage === 'success') {
      return null;
    }
    if (session.current_stage === 'azure_devops_creation') {
      return (
        <div className="planner-actions">
          <button className="planner-button secondary" onClick={() => void copyPrompt()}>Copy Prompt</button>
          <button className="planner-button" onClick={createItems}>Create Azure DevOps Work Items</button>
        </div>
      );
    }
    return (
      <div className="planner-actions">
        <button className="planner-button secondary" onClick={saveCurrentStage}>Edit</button>
        <button className="planner-button secondary" onClick={regenerate}>Regenerate</button>
        <button className="planner-button" onClick={approve}>Approve</button>
      </div>
    );
  }

  return (
    <main className="planner-shell">
      <section className="planner-card">
        <div className="planner-title">AI Story Planner</div>
        <div className="planner-subtle">
          {view.workItem ? `Boards item: ${view.workItem.title || `#${view.workItem.id}`}` : 'Plan a requirement into an approved story and real Azure DevOps work items.'}
        </div>
        <div className="planner-steps">
          {steps.map((step) => (
            <div
              key={step.id}
              className={`planner-step ${currentStage === step.id ? 'active' : ''} ${step.done ? 'done' : ''}`}
            >
              <strong>{step.label}</strong>
            </div>
          ))}
        </div>
      </section>

      {view.error ? <div className="planner-error">{view.error}</div> : null}
      {view.loading ? <div className="planner-subtle">{view.loadingMessage}</div> : null}

      {!view.session ? (
      <section className="planner-card">
          {seedWarning ? <div className="planner-subtle">{seedWarning}</div> : null}
          <div className="planner-label">Requirement</div>
          <textarea
            className="planner-textarea"
            value={requirement}
            onChange={(event) => setRequirement(event.target.value)}
            placeholder="As a customer, I want OTP login so I can securely access my account."
          />
          <div className="planner-actions">
            <button className="planner-button" onClick={start} disabled={!requirement.trim() || view.loading}>Start Planning</button>
          </div>
        </section>
      ) : (
        <section className="planner-card">
          <div className="planner-label">Current Question</div>
          <div>{view.session.question}</div>
          {view.session.current_stage !== 'azure_devops_creation' && view.session.current_stage !== 'success' ? (
            <>
              <div className="planner-label">Your Input</div>
              <textarea
                className="planner-textarea"
                value={activeInput}
                onChange={(event) => setActiveInput(event.target.value)}
                placeholder={view.session.user_input_hint}
              />
            </>
          ) : null}
          {renderStageBody(view.session)}
          {renderActions(view.session)}
        </section>
      )}
    </main>
  );

  async function copyPrompt() {
    const prompt = (view.session?.code_generation_prompt || buildFallbackPrompt(view.session)).trim();
    if (!prompt) {
      setView((current) => ({ ...current, error: 'Code-generation prompt is not ready yet.' }));
      return;
    }
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(prompt);
        return;
      }
    } catch {
      // fall through to manual copy
    }
    const area = document.createElement('textarea');
    area.value = prompt;
    area.style.position = 'fixed';
    area.style.opacity = '0';
    document.body.appendChild(area);
    area.focus();
    area.select();
    try {
      const copied = document.execCommand('copy');
      document.body.removeChild(area);
      if (copied) {
        return;
      }
    } catch {
      document.body.removeChild(area);
    }
    window.prompt('Copy the code-generation prompt:', prompt);
  }
}

function buildSeedRequirement(workItem: PlannerViewState['workItem']): string {
  if (!workItem) {
    return '';
  }
  const parts: string[] = [];
  const title = cleanText(workItem.title);
  const description = htmlToText(workItem.description);
  const acceptance = htmlToText(workItem.acceptanceCriteria);
  const comments = (workItem.comments || []).map(htmlToText).map(cleanText).filter(Boolean);

  if (title) {
    parts.push(`Title: ${title}`);
  }
  if (description) {
    parts.push(`Description: ${description}`);
  }
  if (acceptance) {
    parts.push(`Acceptance Criteria: ${acceptance}`);
  }
  if (comments.length) {
    parts.push(`Discussion Notes: ${comments.join(' ')}`);
  }
  return parts.join('\n\n');
}

function htmlToText(value: string): string {
  return cleanText(
    String(value || '')
      .replace(/<br\s*\/?>/gi, '\n')
      .replace(/<\/p>/gi, '\n')
      .replace(/<li>/gi, '- ')
      .replace(/<\/li>/gi, '\n')
      .replace(/<[^>]+>/g, ' ')
      .replace(/&nbsp;/gi, ' ')
      .replace(/&amp;/gi, '&')
      .replace(/&lt;/gi, '<')
      .replace(/&gt;/gi, '>')
  );
}

function cleanText(value: string): string {
  return String(value || '').replace(/\s+/g, ' ').trim();
}

function buildFallbackPrompt(session?: PlannerSession): string {
  if (!session) {
    return '';
  }
  const sections = [
    '# Task',
    session.story.description || session.requirement,
    '',
    '# Business Value',
    `- ${session.story.business_value || 'Deliver the approved user story clearly and safely.'}`,
    '',
    '# Acceptance Criteria',
    ...session.acceptance_criteria.map((item) => `- ${item}`),
    '',
    '# Proposed Tasks',
    ...session.tasks.map((task) => `- ${task.title}: ${task.description}`),
  ];
  return sections.join('\n').trim();
}

const rootNode = document.getElementById('root');
if (rootNode) {
  createRoot(rootNode).render(<StoryPlannerTab />);
}
