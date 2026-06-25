import * as React from 'react';
import { Card } from '../../components/common/Card';
import { useHostProvider } from '../../services/HostProvider';
import { StatusBadge } from '../../components/common/StatusBadge';

export function CurrentWorkBreadcrumb() {
  const hostContext = useHostProvider();

  return (
    <Card>
      <div className="hei-flex-col hei-gap-sm">
        <span className="hei-text-small hei-text-muted hei-font-semibold">CURRENT WORK</span>
        <div className="hei-flex-row hei-gap-sm" style={{ fontSize: 'var(--hei-font-size-lg)', flexWrap: 'wrap' }}>
          {hostContext.workItemId ? (
            <>
              <span style={{ color: 'var(--hei-text-primary)', fontWeight: 600 }}>{hostContext.projectName || 'Project'}</span>
              <span className="hei-text-muted">›</span>
              <span style={{ color: 'var(--hei-text-secondary)' }}>Epic</span>
              <span className="hei-text-muted">›</span>
              <span style={{ color: 'var(--hei-text-secondary)' }}>Feature</span>
              <span className="hei-text-muted">›</span>
              <span style={{ color: 'var(--hei-primary)', fontWeight: 600 }}>Story #{hostContext.workItemId}</span>
            </>
          ) : (
            <span style={{ color: 'var(--hei-text-secondary)' }}>Loading Work Item...</span>
          )}
        </div>
      </div>
    </Card>
  );
}
