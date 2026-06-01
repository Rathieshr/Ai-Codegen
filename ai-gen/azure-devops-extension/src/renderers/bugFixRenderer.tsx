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
          <OutputList title="Root Cause" items={output.likely_bug_surface ? [String(output.likely_bug_surface)] : []} />
          <OutputList title="Impact Analysis" items={(output.impacted_areas as string[]) || []} />
          <OutputList title="Fix Packet" items={output.execution_packet ? ['Fix packet is available.'] : []} />
          <OutputList title="Regression Plan" items={(output.test_cases as Array<{ title?: string }>)?.map((item) => String(item.title || '')).filter(Boolean) || []} />
        </div>
      }
    />
  );
}
