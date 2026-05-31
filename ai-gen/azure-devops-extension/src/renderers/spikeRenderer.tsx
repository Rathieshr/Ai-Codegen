import React from 'react';
import { OutputList, TemplateWorkspaceShell, WorkspaceRendererProps } from './workspaceRenderer';

export default function SpikeRenderer(props: WorkspaceRendererProps) {
  const output = props.currentStage?.output || {};
  return (
    <TemplateWorkspaceShell
      props={props}
      title="Spike Workspace"
      summary={props.currentSummary}
      extra={
        <div className="ai-gen-stage-panel">
          <OutputList title="Research Questions" items={(output.research_questions as string[]) || []} />
          <OutputList title="Investigation Plan" items={(output.findings as string[]) || []} />
          <OutputList title="Recommendation" items={[String(output.recommendation || output.summary || props.currentSummary)]} />
        </div>
      }
    />
  );
}
