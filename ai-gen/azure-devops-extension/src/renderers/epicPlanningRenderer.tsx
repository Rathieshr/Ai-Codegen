import React from 'react';
import { OutputList, TemplateWorkspaceShell, WorkspaceRendererProps } from './workspaceRenderer';

type DraftItem = {
  title?: string;
  description?: string;
  draft_type?: string;
  type?: string;
  acceptance_criteria?: string[];
  children?: DraftItem[];
  child_drafts?: DraftItem[];
};

export default function EpicPlanningRenderer(props: WorkspaceRendererProps) {
  const output = props.currentStage?.output || {};
  const analysisOutput = props.pipeline?.stages?.epic_analysis?.output || {};
  const featureOutput = props.pipeline?.stages?.feature_generation?.output || {};
  const storyOutput = props.pipeline?.stages?.story_generation?.output || {};
  const reviewOutput = props.pipeline?.stages?.review?.output || {};
  const sourceLabel = String(output.provider_used || storyOutput.provider_used || featureOutput.provider_used || analysisOutput.provider_used || '');
  const generatedFeatures = Array.isArray(featureOutput.generated_features)
    ? (featureOutput.generated_features as Array<{ title?: string }>).map((item) => String(item.title || '')).filter(Boolean)
    : [];
  const storySource = Array.isArray(storyOutput.generated_work_items)
    ? storyOutput.generated_work_items
    : reviewOutput.generated_work_items;
  const planningTree = normalizePlanningTree(Array.isArray(storySource) ? storySource as DraftItem[] : [], generatedFeatures);
  const stageStatuses = [
    ['Epic Analysis', props.pipeline?.stages?.epic_analysis?.status || 'locked'],
    ['Feature Generation', props.pipeline?.stages?.feature_generation?.status || 'locked'],
    ['Story Generation', props.pipeline?.stages?.story_generation?.status || 'locked'],
    ['Review', props.pipeline?.stages?.review?.status || 'locked'],
  ];
  return (
    <TemplateWorkspaceShell
      props={props}
      title="Epic Planning Workspace"
      summary={props.currentSummary}
      extra={
        <div className="ai-gen-stage-panel">
          <OutputList title="Epic Goal" items={[String(analysisOutput.goal || analysisOutput.summary || output.summary || props.currentSummary)]} />
          <OutputList title="Expected Outputs" items={['Features', 'Stories', 'Dependencies', 'Risks']} />
          {sourceLabel ? <OutputList title="Generation Source" items={[sourceLabel]} /> : null}
          <OutputList title="Internal Progress" items={stageStatuses.map(([label, status]) => `${label}: ${status}`)} />
          <PlanningTree items={planningTree} />
          <OutputList title="Dependencies" items={(reviewOutput.dependencies as string[]) || (featureOutput.dependencies as string[]) || (analysisOutput.dependencies as string[]) || []} />
          <OutputList title="Risks" items={(reviewOutput.risks as string[]) || (featureOutput.risks as string[]) || (analysisOutput.risks as string[]) || []} />
        </div>
      }
    />
  );
}

function normalizePlanningTree(items: DraftItem[], fallbackFeatures: string[]): DraftItem[] {
  const features = items
    .filter((item) => String(item.draft_type || item.type || '').toLowerCase() === 'feature' || (item.children || item.child_drafts || []).length)
    .map((item) => ({ ...item, children: item.children || item.child_drafts || [] }));
  if (features.length) {
    return features;
  }
  if (items.length) {
    return [{
      title: 'Proposed Stories',
      description: 'Stories generated from the epic scope.',
      children: items,
    }];
  }
  return fallbackFeatures.map((title) => ({ title, children: [] }));
}

function PlanningTree({ items }: { items: DraftItem[] }) {
  if (!items.length) {
    return null;
  }
  return (
    <div className="ai-gen-subsection">
      <div className="ai-gen-key">Proposed Work Items</div>
      <div className="ai-gen-planning-tree">
        {items.map((feature, index) => {
          const stories = feature.children || feature.child_drafts || [];
          return (
            <div className="ai-gen-plan-card" key={`${feature.title || 'feature'}-${index}`}>
              <div className="ai-gen-plan-card-header">
                <span className="ai-gen-plan-type">Feature</span>
                <strong>{feature.title || 'Untitled feature'}</strong>
              </div>
              {feature.description ? <div className="ai-gen-muted">{feature.description}</div> : null}
              {stories.length ? (
                <div className="ai-gen-plan-children">
                  {stories.map((story, storyIndex) => (
                    <div className="ai-gen-plan-child" key={`${story.title || 'story'}-${storyIndex}`}>
                      <div>
                        <span className="ai-gen-plan-type">Story</span>
                        <strong>{story.title || 'Untitled story'}</strong>
                      </div>
                      {story.description ? <div className="ai-gen-muted">{story.description}</div> : null}
                      <div className="ai-gen-muted">{(story.acceptance_criteria || []).length} acceptance criteria</div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="ai-gen-muted">No stories generated yet.</div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
