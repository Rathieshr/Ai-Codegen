import React from 'react';
import { OutputList, TemplateWorkspaceShell, WorkspaceRendererProps } from './workspaceRenderer';

export default function TaskExecutionRenderer(props: WorkspaceRendererProps) {
  const output = props.currentStage?.output || {};
  return (
    <TemplateWorkspaceShell
      props={props}
      title="Task Execution Workspace"
      summary={props.currentSummary}
      extra={
        <div className="ai-gen-stage-panel">
          <OutputList title="Task Analysis" items={[String(output.summary || output.task_summary || props.currentSummary)]} />
          <OutputList title="Execution Packet" items={output.execution_packet ? ['Execution packet is available for your preferred executor.'] : []} />
          <OutputList title="Constraints" items={(output.constraints as string[]) || []} />
          <OutputList title="Validation Checklist" items={(output.test_cases as Array<{ title?: string }>)?.map((item) => String(item.title || '')).filter(Boolean) || []} />
        </div>
      }
    />
  );
}
