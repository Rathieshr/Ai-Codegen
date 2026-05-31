import React from 'react';
import { OutputList, TemplateWorkspaceShell, WorkspaceRendererProps } from './workspaceRenderer';

export default function BugFixRenderer(props: WorkspaceRendererProps) {
  const output = props.currentStage?.output || {};
  return (
    <TemplateWorkspaceShell
      props={props}
      title="Bug Fix Workspace"
      summary={props.currentSummary}
      extra={
        <div className="ai-gen-stage-panel">
          <OutputList title="Bug Summary" items={[String(output.summary || output.task_summary || props.currentSummary)]} />
          <OutputList title="Suspected Root Cause" items={(output.impacted_areas as string[]) || []} />
          <OutputList title="Impacted Areas" items={(output.regression_risks as string[]) || []} />
          <OutputList title="Regression Checklist" items={(output.test_cases as Array<{ title?: string }>)?.map((item) => String(item.title || '')).filter(Boolean) || []} />
        </div>
      }
    />
  );
}
