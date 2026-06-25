import * as React from 'react';
import { Card, SectionHeader, StatusBadge, InfoRow } from '../../components/common';
import { useProjectStore, ReadinessStatus } from '../../store/projectStore';

export function ReadinessDashboard() {
  const readiness = useProjectStore(state => state.engineeringReadiness);

  const renderStatus = (status: ReadinessStatus) => {
    switch (status) {
      case 'Ready': return <StatusBadge label={status} type="success" />;
      case 'Needs Refresh': return <StatusBadge label={status} type="warning" />;
      case 'Blocked': return <StatusBadge label={status} type="error" />;
      case 'Pending': return <StatusBadge label={status} type="default" />;
      default: return <StatusBadge label={status} />;
    }
  };

  return (
    <Card>
      <SectionHeader title="Engineering Readiness" />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--hei-spacing-sm)' }}>
        <InfoRow 
          label="Repository" 
          value={renderStatus(readiness.repository as ReadinessStatus)} 
        />
        <InfoRow 
          label="Planning Pipeline" 
          value={renderStatus(readiness.planning)} 
        />
        <InfoRow 
          label="Execution Package" 
          value={renderStatus(readiness.execution)} 
        />
        <InfoRow 
          label="QA Validation" 
          value={renderStatus(readiness.qa)} 
        />
      </div>
    </Card>
  );
}
