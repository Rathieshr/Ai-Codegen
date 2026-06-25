import * as React from 'react';
import { Card, SectionHeader, StatusBadge, MetricTile } from '../../components/common';
import { useRepositoryStore } from '../../store/repositoryStore';

export function RepositoryIntelligenceCard() {
  const drift = useRepositoryStore(state => state.repositoryDrift);

  if (!drift) return null;

  return (
    <Card>
      <SectionHeader 
        title="Repository Intelligence" 
        action={<StatusBadge label="Analyzed" type="success" />} 
      />
      
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--hei-spacing-md)' }}>
        <MetricTile label="Version" value={`v${drift.knowledgeVersion || '1.0'}`} />
        <MetricTile label="Modules" value="12" />
        <MetricTile label="Flows" value="48" />
        <MetricTile label="Documents" value="156" />
      </div>
    </Card>
  );
}
