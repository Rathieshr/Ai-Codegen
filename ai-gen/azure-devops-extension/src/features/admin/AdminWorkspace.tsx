import * as React from 'react';
import { PageHeader, Card } from '../../components/common';
import { useUIStore } from '../../store/uiStore';

export interface AdminWorkspaceProps {
  legacyComponent?: React.ReactNode;
}

export function AdminWorkspace({ legacyComponent }: AdminWorkspaceProps) {
  const isNewAdminEnabled = useUIStore(state => state.featureFlags.ENABLE_NEW_UI);

  return (
    <div>
      <PageHeader 
        title="Administration" 
        description="Platform configuration and intelligence registries."
      />
      <Card style={{ marginTop: 'var(--hei-spacing-xl)' }}>
        <h3 style={{ margin: '0 0 16px 0' }}>Future Implementation</h3>
        <p style={{ color: 'var(--hei-text-secondary)', margin: 0 }}>
          The new Admin categories (Knowledge Registry, Engineering Standards) will be implemented in a future phase.
        </p>
      </Card>
    </div>
  );
}
