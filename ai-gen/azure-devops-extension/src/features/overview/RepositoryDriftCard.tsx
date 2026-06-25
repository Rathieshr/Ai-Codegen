import * as React from 'react';
import { Card, SectionHeader, StatusBadge, SecondaryButton } from '../../components/common';
import { useRepositoryStore } from '../../store/repositoryStore';

export function RepositoryDriftCard() {
  const drift = useRepositoryStore(state => state.repositoryDrift);

  if (!drift) return null;

  const hasDrift = drift.newModules > 0 || drift.modifiedFlows > 0 || drift.architectureChanges > 0 || drift.documentationChanges > 0;

  return (
    <Card>
      <SectionHeader 
        title="Repository Drift" 
        action={hasDrift ? <StatusBadge label="Action Required" type="warning" /> : <StatusBadge label="No Drift" type="success" />} 
      />

      {hasDrift ? (
        <div className="hei-flex-col hei-gap-md">
          <div className="hei-grid hei-grid-2-col">
            <DriftMetric label="New Modules" value={drift.newModules} />
            <DriftMetric label="Modified Flows" value={drift.modifiedFlows} />
            <DriftMetric label="Architecture Changes" value={drift.architectureChanges} isCritical />
            <DriftMetric label="Documentation Changes" value={drift.documentationChanges} />
          </div>
          <SecondaryButton style={{ alignSelf: 'flex-start', marginTop: 'var(--hei-spacing-sm)' }}>
            Review Drift
          </SecondaryButton>
        </div>
      ) : (
        <div style={{ padding: 'var(--hei-spacing-md)', background: 'var(--hei-success-bg)', color: 'var(--hei-success)', borderRadius: 'var(--hei-radius)', fontWeight: 600 }}>
          ✓ Knowledge base is fully synchronized.
        </div>
      )}
    </Card>
  );
}

function DriftMetric({ label, value, isCritical = false }: { label: string; value: number; isCritical?: boolean }) {
  if (value === 0) return null;
  
  return (
    <div style={{ 
      padding: 'var(--hei-spacing-md)', 
      background: 'var(--hei-bg)', 
      borderRadius: 'var(--hei-radius)',
      borderLeft: `4px solid ${isCritical ? 'var(--hei-warning)' : 'var(--hei-info)'}`
    }}>
      <div style={{ fontSize: '24px', fontWeight: 600, color: isCritical ? 'var(--hei-warning)' : 'var(--hei-text-primary)' }}>
        {value}
      </div>
      <div style={{ fontSize: 'var(--hei-font-size-sm)', color: 'var(--hei-text-secondary)', fontWeight: 600 }}>
        {label}
      </div>
    </div>
  );
}
