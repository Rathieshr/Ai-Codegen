import React from 'react';
import { OutputList, TemplateWorkspaceShell, WorkspaceRendererProps } from './workspaceRenderer';

type DraftItem = {
  draft_id?: string;
  title?: string;
  description?: string;
  draft_type?: string;
  type?: string;
  status?: string;
  azure_work_item_id?: number | null;
  acceptance_criteria?: string[];
  children?: DraftItem[];
  child_drafts?: DraftItem[];
};

export default function FeaturePlanningRenderer(props: WorkspaceRendererProps) {
  const output = props.currentStage?.output || {};
  const sourceLabel = String(output.provider_used || '');
  const workItems = props.planningDrafts?.length
    ? props.planningDrafts as DraftItem[]
    : Array.isArray(output.generated_work_items) ? output.generated_work_items as DraftItem[] : [];
  return (
    <TemplateWorkspaceShell
      props={props}
      title="Feature Planning Workspace"
      summary={props.currentSummary}
      extra={
        <div className="ai-gen-stage-panel">
          <OutputList title="Feature Summary" items={[String(output.summary || props.currentSummary)]} />
          {sourceLabel ? <OutputList title="Generation Source" items={[sourceLabel]} /> : null}
          <StoryTaskTree items={workItems} />
          <OutputList title="Acceptance Criteria" items={(output.acceptance_criteria as string[]) || []} />
          <OutputList title="Dependencies" items={(output.dependencies as string[]) || []} />
          {workItems.length ? (
            <div className="ai-gen-actions ai-gen-actions-compact">
              <button className="ai-gen-button" onClick={props.onCreateSelectedDrafts} disabled={props.loading}>
                Create All Work Items
              </button>
            </div>
          ) : null}
        </div>
      }
    />
  );
}

function StoryTaskTree({ items }: { items: DraftItem[] }) {
  if (!items.length) {
    return null;
  }
  return (
    <div className="ai-gen-subsection">
      <div className="ai-gen-key">Proposed Work Items</div>
      <div className="ai-gen-planning-tree">
        {items.map((story, index) => {
          const tasks = mergeDraftChildren(story);
          return (
            <div className="ai-gen-plan-card" key={`${story.title || 'story'}-${index}`}>
              <div className="ai-gen-plan-card-header">
                <span className="ai-gen-plan-type">Story</span>
                <strong>{story.title || 'Untitled story'}</strong>
              </div>
              {story.description ? <div className="ai-gen-muted">{story.description}</div> : null}
              <div className="ai-gen-muted">{(story.acceptance_criteria || []).length} acceptance criteria</div>
              {tasks.length ? (
                <div className="ai-gen-plan-children">
                  {tasks.map((task, taskIndex) => (
                    <div className="ai-gen-plan-child" key={`${task.title || 'task'}-${taskIndex}`}>
                      <div>
                        <span className="ai-gen-plan-type">Task</span>
                        <strong>{task.title || 'Untitled task'}</strong>
                      </div>
                      {task.description ? <div className="ai-gen-muted">{task.description}</div> : null}
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function mergeDraftChildren(item: DraftItem): DraftItem[] {
  const merged: DraftItem[] = [];
  const seen = new Set<string>();
  for (const child of [...(item.children || []), ...(item.child_drafts || [])]) {
    const key = String(child.draft_id || child.title || '').trim().toLowerCase();
    if (!key || seen.has(key)) {
      continue;
    }
    seen.add(key);
    merged.push(child);
  }
  return merged;
}
