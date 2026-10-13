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
        <strong>{loading ? 'Loading your project...' : 'Your project could not be loaded.'}</strong>
        <span>{loading ? 'Getting your plans and recent work.' : 'Try again to see the latest project activity.'}</span>
        <button className="planner-button secondary" type="button" onClick={onRefresh} disabled={loading}>Try again</button>
      </section>
    );
  }

  const latestSync = overview.repositorySync.latestSync;
  const repositoryCount = numberValue(overview.repositoryStatus.repositoryCount);
  const repositoryHealth = stringValue(overview.repositoryStatus.health) || 'Not configured';
  const validationNeedsAttention = overview.validation.pending + (tone(overview.validation.status) === 'error' ? overview.validation.count : 0);
  const recentExecution = overview.executionQueue.recent?.[0] || overview.execution?.items?.[0];
  const recentPlanning = overview.planning?.items?.[0];
  const recentAdo = overview.recentActivity.items.find((item) => /azure|ado|work item|pull request/i.test(`${stringValue(item.source)} ${stringValue(item.category)} ${stringValue(item.title)}`));
  const recentWork = [
    { label: 'Plan', item: recentPlanning, action: onReviewPlanning },
    { label: 'Execution', item: recentExecution, action: onOpenExecution },
    { label: 'Repository', item: latestSync, action: onOpenRepository },
    { label: 'Azure DevOps', item: recentAdo, action: onOpenPrIntelligence },
  ].filter((entry) => entry.item && entry.action);
  const attention = [
    { label: 'Plans awaiting approval', count: overview.pendingApprovals.count, detail: 'Review the proposed work and record your decision.', action: onOpenApprovals },
    { label: 'Validation findings', count: validationNeedsAttention, detail: 'Review checks that need a decision.', action: onOpenExecution },
    { label: 'Open pull requests', count: overview.prIntelligence.openCount, detail: 'Review the latest code changes.', action: onOpenPrIntelligence },
  ].filter((entry) => entry.count > 0 && entry.action);

  return (
    <section className="hei-home-refresh" aria-label="Project home">
      <div className="hei-home-heading">
        <div>
          <span className="hei-home-eyebrow">{greeting()}</span>
          <h1>What are you working on?</h1>
          <p>{attention.length ? 'A few things are ready for your review.' : 'Pick up recent work or start a new requirement.'}</p>
        </div>
        <div className="hei-overview-title-actions">
          {onCreateRequirement ? <button className="planner-button primary" type="button" onClick={onCreateRequirement}>New Requirement</button> : null}
          <button className="planner-button secondary" type="button" onClick={onRefresh} disabled={loading}>{loading ? 'Refreshing...' : 'Refresh'}</button>
        </div>
      </div>

      <div className="hei-home-work">
        <section className="hei-home-section">
          <div className="hei-home-section-heading"><h2>Needs your attention</h2><span>{attention.reduce((total, entry) => total + entry.count, 0)} open</span></div>
          {attention.length ? attention.map((entry) => <HomeAction key={entry.label} label={entry.label} value={entry.count} detail={entry.detail} onAction={entry.action} />) : <div className="hei-home-clear"><span className="hei-clear-mark" aria-hidden="true">OK</span><div><strong>You're all caught up</strong><p>No pending reviews for your available workspaces.</p></div></div>}
        </section>

        <section className="hei-home-section">
          <div className="hei-home-section-heading"><h2>Continue working</h2>{onOpenActivity ? <button type="button" className="hei-text-action" onClick={onOpenActivity}>View activity</button> : null}</div>
          {recentWork.length ? recentWork.map((entry) => <RecentWork key={entry.label} label={entry.label} item={entry.item!} onAction={entry.action!} />) : <div className="hei-home-clear"><div><strong>No recent work yet</strong><p>{onCreateRequirement ? 'Start with a requirement. Your saved work will appear here.' : 'Project activity will appear here as your team gets started.'}</p></div></div>}
        </section>
      </div>

      <section className="hei-home-knowledge" aria-label="Project knowledge">
        <div><span className="hei-home-eyebrow">Project knowledge</span><h2>{repositoryName || overview.currentProject.name || 'Connect your repository'}</h2><p>{repositoryCount ? `${numberValue(overview.repositoryStatus.filesIndexed).toLocaleString()} files indexed. ${overview.memoryCandidates.count} memory candidates available for review.` : onConfigureRepository ? 'Connect a repository to use your code and documentation during planning.' : 'Ask a project administrator to connect a repository.'}</p></div>
        <div className="hei-knowledge-actions"><StatusChip status={repositoryCount ? repositoryHealth : 'Not connected'} />{(repositoryCount ? onOpenRepository : onConfigureRepository) ? <button className="planner-button secondary" type="button" onClick={repositoryCount ? onOpenRepository : onConfigureRepository}>{repositoryCount ? 'Explore knowledge' : 'Connect repository'}</button> : null}</div>
      </section>

      {overview.warnings.length ? (
        <details className="hei-overview-warnings">
          <summary>{overview.warnings.length} operational notice{overview.warnings.length === 1 ? '' : 's'}</summary>
          {overview.warnings.map((warning, index) => <p key={`${warning.source}-${index}`}><strong>{displaySource(warning.source)}</strong> {warning.message}</p>)}
        </details>
      ) : null}
    </section>
  );
}

function RecentWork({ label, item, onAction }: { label: string; item: Record<string, unknown>; onAction: () => void }) {
  return <button type="button" className="hei-home-work-row" onClick={onAction}><span className="hei-work-kind">{label}</span><span><strong>{itemTitle(item, label)}</strong><small>{formatTimestamp(stringValue(item.updatedAt) || stringValue(item.createdAt) || stringValue(item.timestamp) || stringValue(item.lastScanAt))}</small></span><span aria-hidden="true">&rarr;</span></button>;
}

function HomeAction({ label, value, detail, onAction }: { label: string; value: number; detail: string; onAction?: () => void }) {
  return <button type="button" className="hei-home-action-row" onClick={onAction} disabled={!onAction}><b>{value}</b><span><strong>{label}</strong><small>{detail}</small></span><span aria-hidden="true">&rarr;</span></button>;
}

function StatusChip({ status }: { status: string }) {
  return <span className={`hei-operation-chip ${tone(status)}`}>{status || 'Unknown'}</span>;
}

function tone(status: string): string {
  const value = status.toLowerCase();
  if (/(not |unavailable|unknown)/.test(value)) return 'neutral';
  if (/(failed|offline|unhealthy|blocked|error)/.test(value)) return 'error';
  if (/(ready|healthy|success|clear|approved|available|connected|current)/.test(value)) return 'success';
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
