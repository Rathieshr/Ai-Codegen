import React from 'react';
import { OutputList, TemplateWorkspaceShell, WorkspaceRendererProps } from './workspaceRenderer';

export default function FeaturePlanningRenderer(props: WorkspaceRendererProps) {
  const output = props.currentStage?.output || {};
  const stories = Array.isArray(output.generated_work_items)
    ? (output.generated_work_items as Array<{ title?: string }>).map((item) => String(item.title || '')).filter(Boolean)
    : [];
  return (
    <TemplateWorkspaceShell
      props={props}
      title="Feature Planning Workspace"
      summary={props.currentSummary}
      extra={
        <div className="ai-gen-stage-panel">
          <OutputList title="Feature Summary" items={[String(output.summary || props.currentSummary)]} />
          <OutputList title="Generated Stories" items={stories} />
          <OutputList title="Generated Tasks" items={Array.isArray(output.generated_work_items)
            ? (output.generated_work_items as Array<{ children?: Array<{ title?: string }> }>)
              .flatMap((item) => (item.children || []).map((child) => String(child.title || '')).filter(Boolean))
            : []} />
          <OutputList title="Acceptance Criteria" items={(output.acceptance_criteria as string[]) || []} />
          <OutputList title="Dependencies" items={(output.dependencies as string[]) || []} />
        </div>
      }
    />
  );
}
