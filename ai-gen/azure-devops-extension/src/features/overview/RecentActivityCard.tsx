import * as React from 'react';
import { Card, SectionHeader } from '../../components/common';

const MOCK_ACTIVITIES = [
  { id: 1, action: 'Generated test cases for Story #241', actor: 'AI Gen', time: '10 mins ago' },
  { id: 2, action: 'Updated Repository Knowledge Base', actor: 'System', time: '1 hour ago' },
  { id: 3, action: 'Approved Planning Drafts', actor: 'Jane Doe', time: '3 hours ago' },
  { id: 4, action: 'Analyzed 3 new commits', actor: 'System', time: '5 hours ago' },
  { id: 5, action: 'Created Feature #240', actor: 'John Smith', time: '1 day ago' },
];

export function RecentActivityCard() {
  return (
    <Card>
      <SectionHeader title="Recent Activity" />
      <div className="hei-flex-col hei-gap-sm">
        {MOCK_ACTIVITIES.map(activity => (
          <div key={activity.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: 'var(--hei-spacing-sm) 0', borderBottom: '1px solid var(--hei-border)' }}>
            <div className="hei-flex-col">
              <span style={{ fontWeight: 500, color: 'var(--hei-text-primary)' }}>{activity.action}</span>
              <span className="hei-text-small hei-text-muted">{activity.actor}</span>
            </div>
            <span className="hei-text-small hei-text-muted">{activity.time}</span>
          </div>
        ))}
      </div>
    </Card>
  );
}
