import * as React from 'react';
import { PageHeader } from '../../components/common';
import { CurrentWorkBreadcrumb } from './CurrentWorkBreadcrumb';
import { RecommendationCard } from './RecommendationCard';
import { ReadinessDashboard } from './ReadinessDashboard';
import { RepositoryIntelligenceCard } from './RepositoryIntelligenceCard';
import { KnowledgeHealthCard } from './KnowledgeHealthCard';
import { RepositoryDriftCard } from './RepositoryDriftCard';
import { RecentActivityCard } from './RecentActivityCard';

export function OverviewWorkspace() {
  return (
    <div>
      <PageHeader 
        title="Engineering Command Center" 
        description="Overview of current work, repository state, and engineering readiness."
      />
      
      <div style={{ marginTop: 'var(--hei-spacing-xl)', display: 'flex', flexDirection: 'column', gap: 'var(--hei-spacing-xl)' }}>
        
        {/* Top Row: Current Work & Recommendation (Hero) */}
        <div className="hei-grid hei-grid-top-row">
          <CurrentWorkBreadcrumb />
          <RecommendationCard />
        </div>

        {/* Second Row: Eng Readiness & Repo Intel & Knowledge */}
        <div className="hei-grid hei-grid-3-col">
          <ReadinessDashboard />
          <RepositoryIntelligenceCard />
          <KnowledgeHealthCard />
        </div>

        {/* Third Row: Repo Drift & Recent Activity */}
        <div className="hei-grid hei-grid-2-col">
          <RepositoryDriftCard />
          <RecentActivityCard />
        </div>

      </div>
    </div>
  );
}
