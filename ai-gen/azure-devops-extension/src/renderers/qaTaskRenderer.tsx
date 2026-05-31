import React from 'react';
import { OutputList, TemplateWorkspaceShell, WorkspaceRendererProps } from './workspaceRenderer';

export default function QaTaskRenderer(props: WorkspaceRendererProps) {
  const output = props.currentStage?.output || {};
  return (
    <TemplateWorkspaceShell
      props={props}
      title="QA Task Workspace"
      summary={props.currentSummary}
      extra={
        <div className="ai-gen-stage-panel">
          <OutputList title="Test Design" items={(output.test_cases as Array<{ title?: string }>)?.map((item) => String(item.title || '')).filter(Boolean) || []} />
          <OutputList title="Automation Candidates" items={(output.automation_candidates as string[]) || []} />
          <OutputList title="Data / Environment Needs" items={(output.coverage_notes as string[]) || []} />
        </div>
      }
    />
  );
}
