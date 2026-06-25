import * as React from 'react';
import { Card, SectionHeader, StatusBadge, InfoRow } from '../../components/common';

export function KnowledgeHealthCard() {
  return (
    <Card>
      <SectionHeader 
        title="Knowledge Health" 
        action={<StatusBadge label="Healthy" type="success" />} 
      />
      <div className="hei-flex-col hei-gap-sm">
        <InfoRow label="Knowledge Version" value="v1.4.2" />
        <InfoRow label="Freshness" value={<StatusBadge label="Up to Date" type="success" />} />
        <InfoRow label="Last Refreshed" value="2 hours ago" />
        <InfoRow label="Status" value="Synchronized" />
      </div>
    </Card>
  );
}
