import * as React from 'react';
import { PageHeader, Card } from '../../components/common';
import { useUIStore } from '../../store/uiStore';

export interface ExecutionWorkspaceProps {
  legacyComponent?: React.ReactNode;
}

export function ExecutionWorkspace({ legacyComponent }: ExecutionWorkspaceProps) {
  const isNewExecutionEnabled = useUIStore(state => state.featureFlags.ENABLE_NEW_UI);

  if (!isNewExecutionEnabled && legacyComponent) {
    return <>{legacyComponent}</>;
  }

  return (
    <div>
      <PageHeader 
        title="Execution" 
        description="Context capsules and execution packages."
      />
      <Card style={{ marginTop: 'var(--hei-spacing-xl)' }}>
        <h3 style={{ margin: '0 0 16px 0' }}>Future Implementation</h3>
        <p style={{ color: 'var(--hei-text-secondary)', margin: 0 }}>
          The new Context Capsule and Execution Package UI will be implemented in a future phase.
        </p>
      </Card>
    </div>
  );
}
