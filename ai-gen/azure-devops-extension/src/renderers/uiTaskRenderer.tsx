import React from 'react';
import { OutputList, TemplateWorkspaceShell, WorkspaceRendererProps } from './workspaceRenderer';

export default function UiTaskRenderer(props: WorkspaceRendererProps) {
  const output = props.currentStage?.output || {};
  const fieldNames = Array.isArray(output.fields)
    ? (output.fields as Array<{ name?: string }>).map((item) => String(item.name || '')).filter(Boolean)
    : [];
  return (
    <TemplateWorkspaceShell
      props={props}
      title="UI Task Workspace"
      summary={props.currentSummary}
      extra={
        <div className="ai-gen-stage-panel">
          <OutputList title="Screen Plan" items={[String(output.screen_name || output.summary || props.currentSummary)]} />
          <OutputList title="Components" items={fieldNames} />
          <OutputList title="States" items={(output.states as string[]) || []} />
          <OutputList title="UX Notes" items={(output.ux_notes as string[]) || []} />
        </div>
      }
    />
  );
}
