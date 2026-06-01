import React from 'react';
import { OutputList, TemplateWorkspaceShell, WorkspaceRendererProps } from './workspaceRenderer';

export default function EpicPlanningRenderer(props: WorkspaceRendererProps) {
  const output = props.currentStage?.output || {};
  const analysisOutput = props.pipeline?.stages?.epic_analysis?.output || {};
  const featureOutput = props.pipeline?.stages?.feature_generation?.output || {};
  const storyOutput = props.pipeline?.stages?.story_generation?.output || {};
  const reviewOutput = props.pipeline?.stages?.review?.output || {};
  const generatedFeatures = Array.isArray(featureOutput.generated_features)
    ? (featureOutput.generated_features as Array<{ title?: string }>).map((item) => String(item.title || '')).filter(Boolean)
    : [];
  const storySource = Array.isArray(storyOutput.generated_work_items)
    ? storyOutput.generated_work_items
    : reviewOutput.generated_work_items;
  const generatedStories = Array.isArray(storySource)
    ? (storySource as Array<{ children?: Array<{ title?: string }>; title?: string }>)
      .flatMap((item) => (item.children || []).map((child) => String(child.title || '')).filter(Boolean))
    : [];
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
          <OutputList title="Internal Progress" items={stageStatuses.map(([label, status]) => `${label}: ${status}`)} />
          <OutputList title="Generated Features" items={generatedFeatures} />
          <OutputList title="Generated Stories" items={generatedStories} />
          <OutputList title="Dependencies" items={(reviewOutput.dependencies as string[]) || (featureOutput.dependencies as string[]) || (analysisOutput.dependencies as string[]) || []} />
          <OutputList title="Risks" items={(reviewOutput.risks as string[]) || (featureOutput.risks as string[]) || (analysisOutput.risks as string[]) || []} />
        </div>
      }
    />
  );
}
