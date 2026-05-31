import React from 'react';
import { OutputList, TemplateWorkspaceShell, WorkspaceRendererProps } from './workspaceRenderer';

export default function StoryDeliveryRenderer(props: WorkspaceRendererProps) {
  const output = props.currentStage?.output || {};
  return (
    <TemplateWorkspaceShell
      props={props}
      title="Story Delivery Workspace"
      summary={props.currentSummary}
      extra={
        <div className="ai-gen-stage-panel">
          <OutputList title="Requirement Clarification" items={[String(output.refined_requirement || output.summary || props.currentSummary)]} />
          <OutputList title="UI Needed" items={[String(props.pipeline?.stage_metadata?.ui_optional?.optional ? 'Optional' : 'Yes')]} />
          <OutputList title="Generated Tasks" items={(output.proposed_work_items as Array<{ title?: string }>)?.map((item) => String(item.title || '')).filter(Boolean) || []} />
          <OutputList title="Test Plan" items={(output.test_cases as Array<{ title?: string }>)?.map((item) => String(item.title || '')).filter(Boolean) || []} />
        </div>
      }
    />
  );
}
