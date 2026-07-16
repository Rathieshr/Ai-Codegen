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
  repositoryStatus: Record<string, unknown> & { repositoryCount?: number; health?: string; filesIndexed?: number; pendingScanCount?: number };
  repositorySync: Record<string, unknown> & { latestSync?: Record<string, unknown> | null; status?: string };
  currentSprint: Record<string, unknown> & { health?: string; status?: string; iteration?: Record<string, unknown>; forecast?: Record<string, unknown> };
  runningAgents: { count: number; waiting: number; items: Array<Record<string, unknown>> };
  executionQueue: { running: number; queued: number; failed: number; total: number };
  pendingApprovals: { count: number; items: Array<Record<string, unknown>> };
  validation: { count: number; approved: number; pending: number; status: string };
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
}: {
  overview?: DashboardOverview;
  loading: boolean;
  onRefresh: () => void;
  repositoryName?: string;
  onOpenRepository?: () => void;
  onConfigureRepository?: () => void;
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

  return (
    <section className="hei-operational-overview" aria-label="HEI operational overview">
      <div className="hei-overview-titlebar">
        <div>
          <span>Engineering State</span>
          <h2>{overview.currentProject.name || 'No project selected'}</h2>
          <p>{overview.currentProject.domain || (overview.currentProject.configured ? repositoryGuidance : 'Select an Azure DevOps project to load operational engineering state.')}</p>
        </div>
        <div className="hei-overview-title-actions">
          <StatusChip status={overview.status} />
          {repositoryCount && onOpenRepository ? <button className="planner-button primary" type="button" onClick={onOpenRepository}>Open Repository</button> : null}
          {!repositoryCount && onConfigureRepository ? <button className="planner-button primary" type="button" onClick={onConfigureRepository}>Configure Repository</button> : null}
          <button className="planner-button secondary" type="button" onClick={onRefresh} disabled={loading}>Refresh</button>
        </div>
      </div>

      <div className="hei-overview-strip">
        <OverviewSignal label="Repository Intelligence" value={`${repositoryCount} registered`} status={repositoryHealth} />
        <OverviewSignal label="Azure DevOps Sync" value={syncStatus} status={latestSync ? 'Work items and delivery data' : 'Synchronization has not run'} />
        <OverviewSignal label="Current Sprint" value={sprintName} status={overview.currentSprint.health || overview.currentSprint.status || 'Not available'} />
        <OverviewSignal label="Build Status" value={overview.buildStatus.status} status={`${overview.buildStatus.count} recent builds`} />
      </div>

      <div className="hei-widget-grid">
        {overview.widgets.map((widget) => (
          <article className="hei-operational-widget" key={widget.id}>
            <div className="hei-widget-heading"><span>{widget.title}</span><StatusChip status={widget.status} /></div>
            <strong>{widget.value}</strong>
            <p>{widget.summary}</p>
          </article>
        ))}
      </div>

      <div className="hei-overview-detail-grid">
        <section className="hei-overview-list">
          <div className="hei-widget-heading"><span>Operational Queue</span><small>Current</small></div>
          <OverviewRow label="Running Agents" value={overview.runningAgents.count} status={`${overview.runningAgents.waiting} waiting`} />
          <OverviewRow label="Execution Queue" value={overview.executionQueue.queued + overview.executionQueue.running} status={`${overview.executionQueue.failed} failed`} />
          <OverviewRow label="Pending Approvals" value={overview.pendingApprovals.count} status={overview.pendingApprovals.count ? 'Review required' : 'Clear'} />
          <OverviewRow label="Validation" value={overview.validation.count} status={overview.validation.status} />
          <OverviewRow label="QA" value={overview.qa.count} status={overview.qa.status} />
          <OverviewRow label="PR Intelligence" value={overview.prIntelligence.openCount} status={`${overview.prIntelligence.pullRequestCount} synchronized`} />
          <OverviewRow label="Memory Candidates" value={overview.memoryCandidates.pending} status={`${overview.memoryCandidates.count} total`} />
          <OverviewRow label="Notifications" value={overview.notifications.unread} status={`${overview.notifications.count} total`} />
        </section>

        <section className="hei-overview-list">
          <div className="hei-widget-heading"><span>Recent Activity</span><small>{overview.recentActivity.count} events</small></div>
          {overview.recentActivity.items.length ? overview.recentActivity.items.slice(0, 8).map((item, index) => (
            <div className="hei-activity-entry" key={stringValue(item.activityId) || stringValue(item.id) || index}>
              <strong>{stringValue(item.title) || stringValue(item.action) || stringValue(item.type) || 'Engineering activity'}</strong>
              <span>{stringValue(item.message) || stringValue(item.description) || stringValue(item.status) || 'Recorded by HEI'}</span>
              <small>{formatTimestamp(stringValue(item.createdAt) || stringValue(item.timestamp))}</small>
            </div>
          )) : <div className="hei-overview-guidance">No activity recorded yet. Engineering lifecycle events will appear here.</div>}
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

function OverviewSignal({ label, value, status }: { label: string; value: string; status: string }) {
  return <div><span>{label}</span><strong>{value}</strong><small>{status}</small></div>;
}

function OverviewRow({ label, value, status }: { label: string; value: number; status: string }) {
  return <div className="hei-overview-row"><span>{label}</span><strong>{value}</strong><small>{status}</small></div>;
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

function displaySource(value: string): string {
  return value.replace(/([a-z])([A-Z])/g, '$1 $2').replace(/^./, (letter) => letter.toUpperCase());
}

function formatTimestamp(value: string): string {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleString();
}
