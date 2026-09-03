import React from 'react';

export type DashboardWidget = {
  id: string;
  title: string;
  status: string;
  value: string | number;
  summary: string;
  target: string;
};

export type DashboardOverview = {
  schemaVersion: string;
  status: string;
  currentProject: { projectId: string; name: string; domain: string; configured: boolean };
  repositoryStatus: Record<string, unknown> & { repositoryCount?: number; health?: string; filesIndexed?: number; pendingScanCount?: number; repositories?: Array<Record<string, unknown>> };
  repositorySync: Record<string, unknown> & { latestSync?: Record<string, unknown> | null; status?: string };
  currentSprint: Record<string, unknown> & { health?: string; status?: string; iteration?: Record<string, unknown>; forecast?: Record<string, unknown> };
  runningAgents: { count: number; waiting: number; items: Array<Record<string, unknown>> };
  executionQueue: { running: number; queued: number; failed: number; total: number; recent?: Array<Record<string, unknown>> };
  planning: { count: number; approved: number; pending: number; status: string; items: Array<Record<string, unknown>> };
  execution: { count: number; approved: number; pending: number; status: string; items: Array<Record<string, unknown>> };
  pendingApprovals: { count: number; items: Array<Record<string, unknown>> };
  validation: { count: number; approved: number; pending: number; status: string; items?: Array<Record<string, unknown>> };
  qa: { count: number; approved: number; pending: number; status: string };
  prIntelligence: { count: number; approved: number; pending: number; status: string; pullRequestCount: number; openCount: number };
  memoryCandidates: { count: number; pending: number; items: Array<Record<string, unknown>> };
  notifications: { count: number; unread: number; items: Array<Record<string, unknown>> };
  buildStatus: { status: string; count: number; failed: number; running: number };
  health: { status: string; services: Record<string, unknown> };
  recentActivity: { count: number; items: Array<Record<string, unknown>> };
  warnings: Array<{ source: string; code: string; message: string }>;
  widgets: DashboardWidget[];
  generatedAt: string;
};

export function OperationalOverviewDashboard({
  overview,
  loading,
  onRefresh,
  repositoryName = '',
  onOpenRepository,
  onConfigureRepository,
  onContinueLastWork,
  onCreateRequirement,
  onReviewPlanning,
  onOpenExecution,
  onOpenApprovals,
  onOpenPrIntelligence,
  onOpenAgents,
  onOpenActivity,
  onOpenSprint,
}: {
  overview?: DashboardOverview;
  loading: boolean;
  onRefresh: () => void;
  repositoryName?: string;
  onOpenRepository?: () => void;
  onConfigureRepository?: () => void;
  onContinueLastWork?: () => void;
  onCreateRequirement?: () => void;
  onReviewPlanning?: () => void;
  onOpenExecution?: () => void;
  onOpenApprovals?: () => void;
  onOpenPrIntelligence?: () => void;
  onOpenAgents?: () => void;
  onOpenActivity?: () => void;
  onOpenSprint?: () => void;
}) {
  if (!overview) {
    return (
      <section className="hei-overview-empty" aria-live="polite">
        <strong>{loading ? 'Loading engineering state...' : 'Operational state is not available yet.'}</strong>
        <span>{loading ? 'HEI is reading existing platform state.' : 'Refresh Overview after the project services are available.'}</span>
        <button className="planner-button secondary" type="button" onClick={onRefresh} disabled={loading}>Refresh Overview</button>
      </section>
    );
  }

  const latestSync = overview.repositorySync.latestSync;
  const repositoryCount = numberValue(overview.repositoryStatus.repositoryCount);
  const repositoryHealth = stringValue(overview.repositoryStatus.health) || 'Not configured';
  const repositoryGuidance = repositoryCount
    ? `${repositoryName || (repositoryCount === 1 ? 'The selected repository' : `${repositoryCount} repositories`)} is registered. ${repositoryHealth === 'Healthy' ? 'Repository Intelligence is ready.' : 'Open Repository Intelligence to complete or review synchronization.'}`
    : 'Configure a repository in Administration to load repository intelligence.';
  const validationNeedsAttention = overview.validation.pending + (tone(overview.validation.status) === 'error' ? overview.validation.count : 0);
  const recentExecution = overview.executionQueue.recent?.[0] || overview.execution?.items?.[0];
  const recentPlanning = overview.planning?.items?.[0];
  const recentAdo = overview.recentActivity.items.find((item) => /azure|ado|work item|pull request/i.test(`${stringValue(item.source)} ${stringValue(item.category)} ${stringValue(item.title)}`));

  return (
    <section className="hei-operational-overview" aria-label="HEI operational overview">
      <div className="hei-overview-titlebar hei-morning-hero">
        <div>
          <span>{greeting()}</span>
          <h2>HEI</h2>
          <p>Turn engineering requirements into approved implementation plans.</p>
        </div>
        <div className="hei-overview-title-actions">
          {onCreateRequirement ? <button className="planner-button primary" type="button" onClick={onCreateRequirement}>New Requirement</button> : null}
          {onContinueLastWork ? <button className="planner-button secondary" type="button" onClick={onContinueLastWork}>Continue Recent Work</button> : null}
        </div>
      </div>

      <div className="hei-home-grid">
        <section className="hei-home-panel needs-attention">
          <div className="hei-morning-section-heading"><div><span>Needs Attention</span><h3>Decisions waiting for you</h3></div></div>
          <HomeAction label="Planning approvals" value={overview.pendingApprovals.count} detail={overview.pendingApprovals.count ? 'Review and approve prepared work.' : 'Nothing is waiting for approval.'} onAction={onOpenApprovals} />
          <HomeAction label="Validation findings" value={validationNeedsAttention} detail={validationNeedsAttention ? 'Implementation checks need review.' : 'No validation findings need attention.'} onAction={onOpenExecution} />
          <HomeAction label="Pull requests" value={overview.prIntelligence.openCount} detail={overview.prIntelligence.openCount ? 'Engineering review is available.' : 'No pull request needs review.'} onAction={onOpenPrIntelligence} />
        </section>

        <section className="hei-home-panel hei-recent-work">
          <div className="hei-morning-section-heading"><div><span>Recent Work</span><h3>Continue where you left off</h3></div></div>
          <RecentWork label="Last Execution" item={recentExecution} fallback="No implementation package or runtime session yet." />
          <RecentWork label="Last Repository Scan" item={(overview.repositoryStatus.repositories as Array<Record<string, unknown>> | undefined)?.[0] || latestSync} fallback="Repository synchronization has not run." />
          <RecentWork label="Recent Plan" item={recentPlanning} fallback="No implementation plan has been created." />
          <RecentWork label="Recent Azure DevOps Update" item={recentAdo} fallback="No recent Azure DevOps activity." />
        </section>

        <section className="hei-home-panel project-intelligence">
          <div className="hei-morning-section-heading"><div><span>Project Intelligence</span><h3>{repositoryName || overview.currentProject.name || 'Current project'}</h3></div><StatusChip status={repositoryCount ? repositoryHealth : 'Not Connected'} /></div>
          <p>{repositoryGuidance}</p>
          <div className="hei-project-knowledge-summary"><span>{numberValue(overview.repositoryStatus.filesIndexed)} files understood</span><span>{overview.memoryCandidates.count} reusable memories</span><span>{overview.planning.count} plans</span></div>
          <button type="button" onClick={repositoryCount ? onOpenRepository : onConfigureRepository} disabled={repositoryCount ? !onOpenRepository : !onConfigureRepository}>{repositoryCount ? 'Open Project Knowledge' : 'Set Up Project Knowledge'}</button>
        </section>
      </div>

      {overview.warnings.length ? (
        <details className="hei-overview-warnings">
          <summary>{overview.warnings.length} operational notice{overview.warnings.length === 1 ? '' : 's'}</summary>
          {overview.warnings.map((warning, index) => <p key={`${warning.source}-${index}`}><strong>{displaySource(warning.source)}</strong> {warning.message}</p>)}
        </details>
      ) : null}
    </section>
  );
}

function RecentWork({ label, item, fallback }: { label: string; item?: Record<string, unknown> | null; fallback: string }) {
  return <div className="hei-recent-work-row"><span>{label}</span><strong>{item ? itemTitle(item, fallback) : fallback}</strong><small>{item ? formatTimestamp(stringValue(item.updatedAt) || stringValue(item.createdAt) || stringValue(item.timestamp) || stringValue(item.lastScanAt)) : ''}</small></div>;
}

function HomeAction({ label, value, detail, onAction }: { label: string; value: number; detail: string; onAction?: () => void }) {
  return <button type="button" className={value ? 'attention' : ''} onClick={onAction} disabled={!onAction}><span><strong>{label}</strong><small>{detail}</small></span><b>{value}</b></button>;
}

function StatusChip({ status }: { status: string }) {
  return <span className={`hei-operation-chip ${tone(status)}`}>{status || 'Unknown'}</span>;
}

function tone(status: string): string {
  const value = status.toLowerCase();
  if (/(ready|healthy|success|clear|approved|available|connected|current)/.test(value)) return 'success';
  if (/(failed|offline|unhealthy|blocked|error)/.test(value)) return 'error';
  if (/(attention|pending|progress|running|degraded|review)/.test(value)) return 'warning';
  return 'neutral';
}

function stringValue(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

function numberValue(value: unknown): number {
  return typeof value === 'number' ? value : Number(value || 0);
}

function itemTitle(item: Record<string, unknown>, fallback: string): string {
  return stringValue(item.title) || stringValue(item.name) || stringValue(item.summary) || stringValue(item.message) || stringValue(item.status) || fallback;
}

function greeting(): string {
  const hour = new Date().getHours();
  return hour < 12 ? 'Good Morning' : hour < 18 ? 'Good Afternoon' : 'Good Evening';
}

function displaySource(value: string): string {
  return value.replace(/([a-z])([A-Z])/g, '$1 $2').replace(/^./, (letter) => letter.toUpperCase());
}

function formatTimestamp(value: string): string {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleString();
}
