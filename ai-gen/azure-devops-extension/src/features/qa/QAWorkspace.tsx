import * as React from 'react';
import { PageHeader, Card } from '../../components/common';
import { useUIStore } from '../../store/uiStore';

export interface QAWorkspaceProps {
  legacyComponent?: React.ReactNode;
}

export function QAWorkspace({ legacyComponent }: QAWorkspaceProps) {
  const isNewQAEnabled = useUIStore(state => state.featureFlags.ENABLE_NEW_UI);

  return (
    <div>
      <PageHeader 
        title="Quality Assurance" 
        description="Testing strategies and validation."
      />
      <Card style={{ marginTop: 'var(--hei-spacing-xl)' }}>
        <h3 style={{ margin: '0 0 16px 0' }}>Future Implementation</h3>
        <p style={{ color: 'var(--hei-text-secondary)', margin: 0 }}>
          The new QA workspace will be implemented in a future phase.
        </p>
      </Card>
    </div>
  );
}
