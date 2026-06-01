import React from 'react';
import { OutputList, TemplateWorkspaceShell, WorkspaceRendererProps } from './workspaceRenderer';

export default function EpicPlanningRenderer(props: WorkspaceRendererProps) {
  const output = props.currentStage?.output || {};
  const generatedFeatures = Array.isArray(output.generated_features)
    ? (output.generated_features as Array<{ title?: string }>).map((item) => String(item.title || '')).filter(Boolean)
    : [];
  const generatedStories = Array.isArray(output.generated_work_items)
    ? (output.generated_work_items as Array<{ children?: Array<{ title?: string }>; title?: string }>)
      .flatMap((item) => (item.children || []).map((child) => String(child.title || '')).filter(Boolean))
    : [];
  return (
    <TemplateWorkspaceShell
      props={props}
      title="Epic Planning Workspace"
      summary={props.currentSummary}
      extra={
        <div className="ai-gen-stage-panel">
          <OutputList title="Epic Goal" items={[String(output.summary || props.currentSummary)]} />
          <OutputList title="Expected Outputs" items={['Features', 'Stories', 'Dependencies', 'Risks']} />
          <OutputList title="Generated Features" items={generatedFeatures.length ? generatedFeatures : (output.proposed_features as Array<{ title?: string }>)?.map((item) => String(item.title || '')).filter(Boolean) || []} />
          <OutputList title="Generated Stories" items={generatedStories} />
          <OutputList title="Dependencies" items={(output.dependencies as string[]) || []} />
          <OutputList title="Risks" items={(output.risks as string[]) || []} />
        </div>
      }
    />
  );
}
