import * as React from 'react';
import { TopNavigation } from './TopNavigation';
import { StickyContextBar } from './StickyContextBar';
import { WorkspaceContainer } from './WorkspaceContainer';
import { useUIStore } from '../../store/uiStore';

// We will import placeholders and legacy renderers in the next step
import { OverviewWorkspace } from '../../features/overview/OverviewWorkspace';
import { PlanningWorkspace } from '../../features/planning/PlanningWorkspace';
import { ExecutionWorkspace } from '../../features/execution/ExecutionWorkspace';
import { QAWorkspace } from '../../features/qa/QAWorkspace';
import { AdminWorkspace } from '../../features/admin/AdminWorkspace';

export interface WorkspaceShellProps {
  legacyPlanningComponent?: React.ReactNode;
  legacyExecutionComponent?: React.ReactNode;
  planningProps?: any; // To pass legacy state down to new PlanningWorkspace without lifting 40 states to zustand yet
}

export function WorkspaceShell({ legacyPlanningComponent, legacyExecutionComponent, planningProps }: WorkspaceShellProps) {
  const activeWorkspace = useUIStore(state => state.activeWorkspace);

  const renderActiveWorkspace = () => {
    switch (activeWorkspace) {
      case 'Overview':
        return <OverviewWorkspace />;
      case 'Planning':
        return <PlanningWorkspace legacyComponent={legacyPlanningComponent} planningProps={planningProps} />;
      case 'Execution':
        return <ExecutionWorkspace legacyComponent={legacyExecutionComponent} />;
      case 'QA':
        return <QAWorkspace />;
      case 'Admin':
        return <AdminWorkspace />;
      default:
        return <div>Workspace Not Found</div>;
    }
  };

  return (
    <div className="hei-shell">
      <TopNavigation />
      <StickyContextBar />
      <WorkspaceContainer>
        {renderActiveWorkspace()}
      </WorkspaceContainer>
    </div>
  );
}
