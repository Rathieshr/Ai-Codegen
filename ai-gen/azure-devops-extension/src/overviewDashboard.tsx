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

  const sprintName = stringValue(overview.currentSprint.iteration?.name)
    || stringValue(overview.currentSprint.iteration?.path)
    || 'No current sprint';
  const latestSync = overview.repositorySync.latestSync;
  const syncStatus = stringValue(latestSync?.status) || overview.repositorySync.status || 'Not connected';
  const repositoryCount = numberValue(overview.repositoryStatus.repositoryCount);
  const repositoryHealth = stringValue(overview.repositoryStatus.health) || 'Not configured';
  const repositoryGuidance = repositoryCount
    ? `${repositoryName || (repositoryCount === 1 ? 'The selected repository' : `${repositoryCount} repositories`)} is registered. ${repositoryHealth === 'Healthy' ? 'Repository Intelligence is ready.' : 'Open Repository Intelligence to complete or review synchronization.'}`
    : 'Configure a repository in Administration to load repository intelligence.';
  const executionReady = numberValue(overview.execution?.approved);
  const validationNeedsAttention = overview.validation.pending + (tone(overview.validation.status) === 'error' ? overview.validation.count : 0);
  const latestValidation = overview.validation.items?.[0];
  const latestNotification = overview.notifications.items[0];
  const latestMemory = overview.memoryCandidates.items[0];
  const latestAgentActivity = overview.recentActivity.items.find((item) => /agent/i.test(`${stringValue(item.source)} ${stringValue(item.category)} ${stringValue(item.title)}`)) || overview.runningAgents.items[0];
  const recentExecution = overview.executionQueue.recent?.[0] || overview.execution?.items?.[0];
  const recentPlanning = overview.planning?.items?.[0];
  const recentAdo = overview.recentActivity.items.find((item) => /azure|ado|work item|pull request/i.test(`${stringValue(item.source)} ${stringValue(item.category)} ${stringValue(item.title)}`));
  const focus = [
    { label: 'Approvals Pending', value: overview.pendingApprovals.count, status: overview.pendingApprovals.count ? 'Needs attention' : 'Clear', action: onOpenApprovals },
    { label: 'Packages Ready', value: executionReady, status: executionReady ? 'Ready to implement' : 'None ready', action: onOpenExecution },
    { label: 'Repository', value: repositoryCount ? repositoryHealth : 'Not connected', status: repositoryCount ? syncStatus : 'Configure repository', action: repositoryCount ? onOpenRepository : onConfigureRepository },
    { label: 'Sprint', value: overview.currentSprint.health || overview.currentSprint.status || 'Not available', status: sprintName, action: onOpenSprint },
    { label: 'PR Review', value: overview.prIntelligence.openCount, status: overview.prIntelligence.openCount ? 'Requires review' : 'No open PRs', action: onOpenPrIntelligence },
    { label: 'Validation', value: validationNeedsAttention, status: validationNeedsAttention ? 'Requires attention' : overview.validation.status, action: onOpenExecution },
  ];

  return (
    <section className="hei-operational-overview" aria-label="HEI operational overview">
      <div className="hei-overview-titlebar hei-morning-hero">
        <div>
          <span>{greeting()}</span>
          <h2>Today in {overview.currentProject.name || 'HEI'}</h2>
          <p>{morningSummary(overview, executionReady, validationNeedsAttention)}</p>
        </div>
        <div className="hei-overview-title-actions">
          {onContinueLastWork ? <button className="planner-button primary" type="button" onClick={onContinueLastWork}>Continue Last Work</button> : null}
          <button className="planner-button secondary" type="button" onClick={onRefresh} disabled={loading}>Refresh</button>
        </div>
      </div>

      <section className="hei-todays-focus" aria-labelledby="todays-focus-title">
        <div className="hei-morning-section-heading"><div><span>Today's Work</span><h3 id="todays-focus-title">Today's Focus</h3></div><small>Prioritized from current engineering state</small></div>
        <div className="hei-focus-grid">
          {focus.map((item) => <FocusSignal key={item.label} {...item} />)}
        </div>
      </section>

      <div className="hei-morning-grid">
        <MorningCard title="Pending Approvals" status={overview.pendingApprovals.count ? 'Needs Review' : 'Clear'} value={overview.pendingApprovals.count} detail={overview.pendingApprovals.count ? `${overview.pendingApprovals.count} engineering decision${overview.pendingApprovals.count === 1 ? '' : 's'} waiting for review.` : 'No engineering decisions are waiting.'} actionLabel="Review Approvals" onAction={onOpenApprovals} />
        <MorningCard title="Execution Packages Ready" status={executionReady ? 'Ready' : 'No Packages'} value={executionReady} detail={recentExecution ? itemTitle(recentExecution, 'Latest implementation package is available.') : 'Approved planning work will appear here when ready for implementation.'} actionLabel="Open Execution" onAction={onOpenExecution} />
        <MorningCard title="Repository Status" status={repositoryCount ? repositoryHealth : 'Not Connected'} value={repositoryCount ? `${numberValue(overview.repositoryStatus.filesIndexed)} files` : 'Setup required'} detail={repositoryGuidance} actionLabel={repositoryCount ? 'Open Repository' : 'Configure Repository'} onAction={repositoryCount ? onOpenRepository : onConfigureRepository} />
        <MorningCard title="Sprint Status" status={overview.currentSprint.health || overview.currentSprint.status || 'Not Available'} value={sprintName} detail={sprintDetail(overview.currentSprint)} actionLabel="Open Current Sprint" onAction={onOpenSprint} />
        <MorningCard title="PR Intelligence" status={overview.prIntelligence.openCount ? 'Review Required' : 'Clear'} value={overview.prIntelligence.openCount} detail={overview.prIntelligence.openCount ? `${overview.prIntelligence.openCount} pull request${overview.prIntelligence.openCount === 1 ? '' : 's'} require engineering review.` : `${overview.prIntelligence.pullRequestCount} pull requests synchronized; none require attention.`} actionLabel="Open PR Intelligence" onAction={onOpenPrIntelligence} />
        <MorningCard title="Validation Status" status={validationNeedsAttention ? 'Needs Attention' : overview.validation.status} value={validationNeedsAttention || overview.validation.approved} detail={latestValidation ? `${itemTitle(latestValidation, 'Validation result')} ${validationNeedsAttention ? 'requires review.' : 'is ready.'}` : 'No implementation validation has been recorded yet.'} actionLabel="Open Validation" onAction={onOpenExecution} />
        <MorningCard title="Recent Agent Activity" status={overview.runningAgents.count ? 'Running' : 'Idle'} value={overview.runningAgents.count} detail={latestAgentActivity ? itemTitle(latestAgentActivity, 'Agent activity recorded.') : 'No recent agent work. Agent-prepared engineering activity will appear here.'} actionLabel="Open Agent Center" onAction={onOpenAgents} />
        <MorningCard title="Notifications" status={overview.notifications.unread ? 'Unread' : 'Clear'} value={overview.notifications.unread} detail={latestNotification ? itemTitle(latestNotification, 'Latest HEI notification') : 'You are caught up. No unread engineering notifications.'} actionLabel="Open Activity" onAction={onOpenActivity} />
        <MorningCard title="Memory Suggestions" status={overview.memoryCandidates.pending ? 'Suggestion Found' : 'No Suggestions'} value={overview.memoryCandidates.pending} detail={latestMemory ? itemTitle(latestMemory, 'Similar validated engineering knowledge is available.') : 'No relevant engineering memory suggestions are waiting.'} actionLabel="Review Memory Activity" onAction={onOpenActivity} />
      </div>

      <div className="hei-morning-lower-grid">
        <section className="hei-overview-list hei-recent-work">
          <div className="hei-morning-section-heading"><div><span>Recent Work</span><h3>Pick up where engineering left off</h3></div><button type="button" onClick={onOpenActivity} disabled={!onOpenActivity}>View Activity</button></div>
          <RecentWork label="Last Execution" item={recentExecution} fallback="No implementation package or runtime session yet." />
          <RecentWork label="Last Repository Scan" item={(overview.repositoryStatus.repositories as Array<Record<string, unknown>> | undefined)?.[0] || latestSync} fallback="Repository synchronization has not run." />
          <RecentWork label="Recent Planning Pack" item={recentPlanning} fallback="No planning pack has been created." />
          <RecentWork label="Recent Azure DevOps Update" item={recentAdo} fallback="No recent Azure DevOps activity." />
        </section>

        <section className="hei-overview-list hei-quick-actions">
          <div className="hei-morning-section-heading"><div><span>Quick Actions</span><h3>Move engineering forward</h3></div></div>
          {onContinueLastWork ? <button className="primary" type="button" onClick={onContinueLastWork}>Continue Last Work</button> : null}
          {onCreateRequirement ? <button type="button" onClick={onCreateRequirement}>Create Requirement</button> : null}
          <button type="button" onClick={onReviewPlanning} disabled={!onReviewPlanning}>Review Planning</button>
          <button type="button" onClick={repositoryCount ? onOpenRepository : onConfigureRepository} disabled={repositoryCount ? !onOpenRepository : !onConfigureRepository}>{repositoryCount ? 'Open Repository' : 'Configure Repository'}</button>
          <button type="button" onClick={onOpenExecution} disabled={!onOpenExecution}>Open Execution</button>
          <button type="button" onClick={onOpenPrIntelligence} disabled={!onOpenPrIntelligence}>Open PR Intelligence</button>
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

function FocusSignal({ label, value, status, action }: { label: string; value: string | number; status: string; action?: () => void }) {
  return <button type="button" onClick={action} disabled={!action}><span>{label}</span><strong>{value}</strong><small>{status}</small></button>;
}

function MorningCard({ title, status, value, detail, actionLabel, onAction }: { title: string; status: string; value: string | number; detail: string; actionLabel: string; onAction?: () => void }) {
  return <article className="hei-morning-card"><div className="hei-widget-heading"><span>{title}</span><StatusChip status={status} /></div><strong>{value}</strong><p>{detail}</p>{onAction ? <button type="button" onClick={onAction}>{actionLabel}</button> : null}</article>;
}

function RecentWork({ label, item, fallback }: { label: string; item?: Record<string, unknown> | null; fallback: string }) {
  return <div className="hei-recent-work-row"><span>{label}</span><strong>{item ? itemTitle(item, fallback) : fallback}</strong><small>{item ? formatTimestamp(stringValue(item.updatedAt) || stringValue(item.createdAt) || stringValue(item.timestamp) || stringValue(item.lastScanAt)) : ''}</small></div>;
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

function morningSummary(overview: DashboardOverview, packages: number, validationAttention: number): string {
  const priorities = [];
  if (overview.pendingApprovals.count) priorities.push(`${overview.pendingApprovals.count} approval${overview.pendingApprovals.count === 1 ? '' : 's'} pending`);
  if (packages) priorities.push(`${packages} implementation package${packages === 1 ? '' : 's'} ready`);
  if (overview.prIntelligence.openCount) priorities.push(`${overview.prIntelligence.openCount} PR${overview.prIntelligence.openCount === 1 ? '' : 's'} to review`);
  if (validationAttention) priorities.push(`${validationAttention} validation item${validationAttention === 1 ? '' : 's'} need attention`);
  return priorities.length ? priorities.slice(0, 3).join(' · ') : 'Engineering work is clear. Start a requirement or continue recent work.';
}

function sprintDetail(value: DashboardOverview['currentSprint']): string {
  const forecast = stringValue(value.forecast?.summary) || stringValue(value.forecast?.status);
  return forecast || (value.health === 'Ready' ? 'Sprint intelligence is current.' : 'Open Sprint Intelligence to review delivery health and forecast.');
}

function displaySource(value: string): string {
  return value.replace(/([a-z])([A-Z])/g, '$1 $2').replace(/^./, (letter) => letter.toUpperCase());
}

function formatTimestamp(value: string): string {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleString();
}
