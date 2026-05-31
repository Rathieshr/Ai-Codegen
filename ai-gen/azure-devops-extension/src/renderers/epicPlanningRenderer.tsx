import React from 'react';
import { OutputList, TemplateWorkspaceShell, WorkspaceRendererProps } from './workspaceRenderer';

export default function EpicPlanningRenderer(props: WorkspaceRendererProps) {
  const output = props.currentStage?.output || {};
  return (
    <TemplateWorkspaceShell
      props={props}
      title="Epic Planning Workspace"
      summary={props.currentSummary}
      extra={
        <div className="ai-gen-stage-panel">
          <OutputList title="Epic Goal" items={[String(output.summary || props.currentSummary)]} />
          <OutputList title="Proposed Features" items={(output.proposed_features as Array<{ title?: string }>)?.map((item) => String(item.title || '')).filter(Boolean) || []} />
          <OutputList title="Proposed Stories" items={(output.proposed_work_items as Array<{ title?: string }>)?.map((item) => String(item.title || '')).filter(Boolean) || []} />
          <OutputList title="Dependencies" items={(output.dependencies as string[]) || []} />
          <OutputList title="Risks" items={(output.risks as string[]) || []} />
        </div>
      }
    />
  );
}
