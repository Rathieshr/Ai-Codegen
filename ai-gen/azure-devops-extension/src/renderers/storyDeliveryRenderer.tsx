import React from 'react';
import { TemplateWorkspaceShell, WorkspaceRendererProps } from './workspaceRenderer';

export default function StoryDeliveryRenderer(props: WorkspaceRendererProps) {
  return (
    <TemplateWorkspaceShell
      props={props}
      title="Story Delivery Workspace"
      summary={props.currentSummary}
      extra={props.storyWorkflowPanel || <div className="ai-gen-stage-panel">{props.feedbackPanel}</div>}
    />
  );
}
