import React, { useEffect, useMemo, useState } from 'react';

type Warning = { code: string; message: string };
type WorkItem = { workItemId: string; title: string; type: string; state: string; assignedTo: string; iterationPath: string; storyPoints?: number; blocked: boolean; recommendationCount: number; webUrl: string };
type PullRequest = { pullRequestId: string; title: string; status: string; createdBy: string; sourceBranch: string; targetBranch: string; webUrl: string; intelligenceStatus: string; missingTests: number; acceptanceCoverage?: number };
type Recommendation = { recommendationId: string; workItemId: string; type: string; status: string; title: string; confidence?: number; actionable: boolean };
type ActionPack = { packId: string; trigger: string; status: string; actionable: boolean; expiresAt: string };
type Sprint = {
  status?: string; health?: string; message?: string; iteration?: Record<string, unknown>;
  metrics?: Record<string, any>; burndownSeries?: Array<Record<string, any>>;
  deliveryRisks?: Array<Record<string, any>>; currentBlockers?: Array<Record<string, any>>;
  completionConfidence?: { score?: number; level?: string }; forecast?: Record<string, any>;
};
type Dashboard = {
  connected: boolean; projectId: string; connection: Record<string, any>; sync: Record<string, any>;
  sprint: Sprint; summary: Record<string, number>; burndown: Array<Record<string, any>>;
  velocity: Record<string, any>; blockedWork: WorkItem[]; deliveryRisk: Array<Record<string, any>>;
  builds: Array<Record<string, any>>; releases: Array<Record<string, any>>;
  recommendations: Recommendation[]; actionPacks: ActionPack[]; warnings: Warning[]; generatedAt: string;
};
type Page<T> = { items: T[]; pagination: { total: number; returned: number; hasMore: boolean }; warnings: Warning[] };

export function AzureDevOpsCenter({
  baseUrl, projectId, canApprove, onOpenApprovals, onError,
}: {
  baseUrl: string;
  projectId: string;
  canApprove: boolean;
  onOpenApprovals: () => void;
  onError?: (message: string) => void;
}) {
  const [dashboard, setDashboard] = useState<Dashboard>();
  const [workItems, setWorkItems] = useState<WorkItem[]>([]);
  const [pullRequests, setPullRequests] = useState<PullRequest[]>([]);
  const [activeView, setActiveView] = useState<'sprint' | 'work' | 'prs' | 'recommendations' | 'delivery'>('sprint');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => { void load(); }, [baseUrl, projectId]);

  async function load() {
    setLoading(true);
    try {
      const query = projectId ? `?projectId=${encodeURIComponent(projectId)}` : '';
      const [summary, work, prs] = await Promise.all([
        request<Dashboard>(`${baseUrl}/ado/dashboard${query}`),
        request<Page<WorkItem>>(`${baseUrl}/ado/work-items${query}${query ? '&' : '?'}limit=250`),
        request<Page<PullRequest>>(`${baseUrl}/ado/prs${query}${query ? '&' : '?'}limit=250`),
      ]);
      setDashboard(summary); setWorkItems(work.items || []); setPullRequests(prs.items || []);
    } catch (error) { onError?.(error instanceof Error ? error.message : String(error)); }
    finally { setLoading(false); }
  }

  const visibleWorkItems = useMemo(() => filter(workItems, search, (item) => `${item.workItemId} ${item.title} ${item.type} ${item.state}`), [workItems, search]);
  const visiblePullRequests = useMemo(() => filter(pullRequests, search, (item) => `${item.pullRequestId} ${item.title} ${item.sourceBranch} ${item.status}`), [pullRequests, search]);
  const sprint = dashboard?.sprint || {};
  const summary = dashboard?.summary || {};
  const disconnected = dashboard && !dashboard.connected;
  const hasCachedData = Boolean((summary.workItems || 0) + (summary.pullRequests || 0) + (summary.builds || 0));

  return (
    <section className="ado-center" aria-label="Azure DevOps Center">
      <header className="ado-center-header">
        <div><span className="hei-eyebrow">Azure DevOps Intelligence</span><h2>Azure DevOps Center</h2><p>Sprint flow, delivery risk, work, pull requests, and approved actions in one operational view.</p></div>
        <div><AdoStatus value={dashboard?.connected ? 'Connected' : 'Disconnected'} /><button type="button" onClick={() => void load()} disabled={loading}>{loading ? 'Refreshing...' : 'Refresh'}</button></div>
      </header>

      {dashboard?.warnings?.length ? <div className="ado-center-warnings">{dashboard.warnings.map((item) => <span key={item.code}>{item.message}</span>)}</div> : null}

      <div className="ado-center-summary">
        <Metric label="Sprint" value={sprintName(sprint)} detail={sprint.health || sprint.status || 'Not available'} />
        <Metric label="Velocity" value={metricValue(dashboard?.velocity?.currentCompletedStoryPoints)} detail={velocityDetail(dashboard?.velocity)} />
        <Metric label="Work Items" value={summary.workItems || 0} detail={`${summary.blockedWork || 0} blocked`} />
        <Metric label="Pull Requests" value={summary.openPullRequests || 0} detail={`${summary.pullRequests || 0} synchronized`} />
        <Metric label="Builds" value={summary.builds || 0} detail={`${summary.failedBuilds || 0} failed`} />
        <Metric label="Delivery Risk" value={summary.deliveryRisks || 0} detail={riskLabel(dashboard?.deliveryRisk)} />
      </div>

      <nav className="ado-center-tabs" aria-label="Azure DevOps intelligence views">
        {(['sprint', 'work', 'prs', 'recommendations', 'delivery'] as const).map((view) => <button key={view} type="button" className={activeView === view ? 'active' : ''} onClick={() => setActiveView(view)}>{tabLabel(view)}</button>)}
      </nav>

      {disconnected && !hasCachedData ? <Empty title="Azure DevOps is disconnected" detail="Connect and synchronize a test or project organization to view current engineering intelligence." /> : null}
      {(!disconnected || hasCachedData) && activeView === 'sprint' ? <SprintView sprint={sprint} burndown={dashboard?.burndown || []} /> : null}
      {(!disconnected || hasCachedData) && activeView === 'work' ? <ListView title="Work Items" search={search} setSearch={setSearch} count={visibleWorkItems.length}>{visibleWorkItems.length ? visibleWorkItems.map((item) => <WorkItemCard key={item.workItemId} item={item} />) : <Empty title="No work items found" detail="Synchronized Azure DevOps work items will appear here." />}</ListView> : null}
      {(!disconnected || hasCachedData) && activeView === 'prs' ? <ListView title="Pull Requests" search={search} setSearch={setSearch} count={visiblePullRequests.length}>{visiblePullRequests.length ? visiblePullRequests.map((item) => <PullRequestCard key={item.pullRequestId} item={item} />) : <Empty title="No pull requests found" detail="Synchronized pull requests will appear here." />}</ListView> : null}
      {(!disconnected || hasCachedData) && activeView === 'recommendations' ? <RecommendationView items={dashboard?.recommendations || []} onReview={onOpenApprovals} /> : null}
      {(!disconnected || hasCachedData) && activeView === 'delivery' ? <DeliveryView dashboard={dashboard} canApprove={canApprove} onOpenApprovals={onOpenApprovals} /> : null}
    </section>
  );
}

function SprintView({ sprint, burndown }: { sprint: Sprint; burndown: Array<Record<string, any>> }) {
  if (sprint.status === 'NoSprint' || !Object.keys(sprint.iteration || {}).length) return <Empty title="No current sprint" detail={sprint.message || 'No current sprint is synchronized for this project.'} />;
  const metrics = sprint.metrics || {};
  const planned = metrics.plannedScope || {}; const completed = metrics.completedScope || {}; const remaining = metrics.remainingScope || {};
  const maxRemaining = Math.max(1, ...burndown.map((point) => Number(point.remainingItems ?? point.remaining ?? 0)));
  return <div className="ado-sprint-view">
    <section className="ado-sprint-overview"><div><span>Current Sprint</span><h3>{sprintName(sprint)}</h3><p>{String(sprint.forecast?.status || 'Forecast unavailable')}</p></div><AdoStatus value={String(sprint.health || 'Unknown')} /></section>
    <div className="ado-sprint-metrics"><Metric label="Planned" value={planned.itemCount || 0} detail={`${planned.storyPoints || 0} points`} /><Metric label="Completed" value={completed.itemCount || 0} detail={`${completed.storyPoints || 0} points`} /><Metric label="Remaining" value={remaining.itemCount || 0} detail={`${remaining.storyPoints || 0} points`} /><Metric label="Confidence" value={`${sprint.completionConfidence?.score || 0}%`} detail={sprint.completionConfidence?.level || 'Low'} /></div>
    <section className="ado-burndown"><div><h3>Burndown</h3><span>{burndown.length ? `${burndown.length} synchronized points` : 'No burndown data'}</span></div>{burndown.length ? <div className="ado-burndown-bars" aria-label="Sprint burndown">{burndown.map((point, index) => { const value = Number(point.remainingItems ?? point.remaining ?? 0); return <div key={String(point.date || index)} title={`${point.date || `Point ${index + 1}`}: ${value}`}><span style={{ height: `${Math.max(4, (value / maxRemaining) * 100)}%` }} /><small>{shortDate(String(point.date || index + 1))}</small></div>; })}</div> : <Empty title="Burndown unavailable" detail="Synchronize iteration history to calculate sprint burndown." />}</section>
  </div>;
}

function ListView({ title, search, setSearch, count, children }: { title: string; search: string; setSearch: (value: string) => void; count: number; children: React.ReactNode }) { return <section className="ado-list-view"><header><div><h3>{title}</h3><span>{count} visible</span></div><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={`Search ${title.toLowerCase()}`} aria-label={`Search ${title}`} /></header><div className="ado-card-grid">{children}</div></section>; }
function WorkItemCard({ item }: { item: WorkItem }) { return <article className="ado-item-card"><div><span>{item.type} #{item.workItemId}</span><AdoStatus value={item.blocked ? 'Blocked' : item.state} /></div><h4>{item.title}</h4><dl><div><dt>Owner</dt><dd>{item.assignedTo || 'Unassigned'}</dd></div><div><dt>Iteration</dt><dd>{item.iterationPath || 'Not assigned'}</dd></div><div><dt>Points</dt><dd>{item.storyPoints ?? 'Not estimated'}</dd></div><div><dt>Recommendations</dt><dd>{item.recommendationCount}</dd></div></dl><ExternalButton label="Open Work Item" url={item.webUrl} /></article>; }
function PullRequestCard({ item }: { item: PullRequest }) { return <article className="ado-item-card"><div><span>PR #{item.pullRequestId}</span><AdoStatus value={item.intelligenceStatus || item.status} /></div><h4>{item.title}</h4><dl><div><dt>Author</dt><dd>{item.createdBy || 'Not recorded'}</dd></div><div><dt>Branch</dt><dd>{cleanBranch(item.sourceBranch)} → {cleanBranch(item.targetBranch)}</dd></div><div><dt>Acceptance</dt><dd>{item.acceptanceCoverage == null ? 'Not analyzed' : `${item.acceptanceCoverage}%`}</dd></div><div><dt>Missing tests</dt><dd>{item.missingTests}</dd></div></dl><ExternalButton label="Open PR" url={item.webUrl} /></article>; }

function RecommendationView({ items, onReview }: { items: Recommendation[]; onReview: () => void }) { return <section className="ado-list-view"><header><div><h3>Recommendations</h3><span>{items.length} available</span></div>{items.length ? <button type="button" onClick={onReview}>Review Recommendation</button> : null}</header><div className="ado-card-grid">{items.length ? items.map((item) => <article className="ado-item-card" key={item.recommendationId}><div><span>{item.type}</span><AdoStatus value={item.status} /></div><h4>{item.title || `Recommendation for #${item.workItemId}`}</h4><p>Work Item #{item.workItemId} · {item.confidence == null ? 'Confidence not scored' : `${item.confidence}% confidence`}</p><button type="button" onClick={onReview}>Review Recommendation</button></article>) : <Empty title="No recommendations" detail="Work item analysis recommendations will appear here for review." />}</div></section>; }

function DeliveryView({ dashboard, canApprove, onOpenApprovals }: { dashboard?: Dashboard; canApprove: boolean; onOpenApprovals: () => void }) {
  return <div className="ado-delivery-grid">
    <DeliverySection title="Blocked Work" empty="No blocked work detected.">{dashboard?.blockedWork?.map((item) => <WorkItemCard key={item.workItemId} item={item} />)}</DeliverySection>
    <DeliverySection title="Delivery Risk" empty="No delivery risks detected.">{dashboard?.deliveryRisk?.map((item, index) => <article className="ado-compact-row" key={String(item.id || item.code || index)}><AdoStatus value={String(item.severity || item.level || 'Risk')} /><div><strong>{String(item.title || item.type || 'Delivery risk')}</strong><span>{String(item.reason || item.message || item.evidence || 'Review sprint evidence.')}</span></div></article>)}</DeliverySection>
    <DeliverySection title="Builds" empty="No synchronized builds.">{dashboard?.builds?.map((item, index) => <article className="ado-compact-row" key={String(item.buildId || index)}><AdoStatus value={String(item.result || item.status || 'Unknown')} /><div><strong>{String(item.definitionName || item.buildNumber || 'Build')}</strong><span>{String(item.finishedAt || 'Completion time not recorded')}</span></div></article>)}</DeliverySection>
    <DeliverySection title="Releases" empty="Release data is not synchronized for this project.">{dashboard?.releases?.map((item, index) => <article className="ado-compact-row" key={String(item.releaseId || index)}><AdoStatus value={String(item.status || 'Unknown')} /><div><strong>{String(item.name || 'Release')}</strong></div></article>)}</DeliverySection>
    <DeliverySection title="Approved Actions" empty="No Azure DevOps action packs are waiting for approval.">{dashboard?.actionPacks?.map((item) => <article className="ado-compact-row" key={item.packId}><AdoStatus value={item.status} /><div><strong>{item.trigger || 'Azure DevOps action'}</strong><span>{item.expiresAt ? `Expires ${formatDate(item.expiresAt)}` : 'No expiry recorded'}</span></div>{item.actionable ? <button type="button" onClick={onOpenApprovals} disabled={!canApprove}>Approve Action</button> : null}</article>)}</DeliverySection>
  </div>;
}

function DeliverySection({ title, empty, children }: { title: string; empty: string; children?: React.ReactNode }) { const hasChildren = React.Children.count(children) > 0; return <section className="ado-delivery-section"><h3>{title}</h3><div>{hasChildren ? children : <p className="ado-inline-empty">{empty}</p>}</div></section>; }
function Metric({ label, value, detail }: { label: string; value: React.ReactNode; detail: string }) { return <div className="ado-metric"><span>{label}</span><strong>{value}</strong><small>{detail}</small></div>; }
function Empty({ title, detail }: { title: string; detail: string }) { return <div className="ado-empty"><strong>{title}</strong><span>{detail}</span></div>; }
function AdoStatus({ value }: { value: string }) { return <span className={`ado-status status-${value.toLowerCase().replace(/[^a-z]+/g, '-')}`}>{value}</span>; }
function ExternalButton({ label, url }: { label: string; url: string }) { return <button type="button" onClick={() => url && window.open(url, '_blank', 'noopener,noreferrer')} disabled={!url}>{url ? label : `${label} unavailable`}</button>; }
function tabLabel(value: string) { return ({ sprint: 'Sprint', work: 'Work Items', prs: 'Pull Requests', recommendations: 'Recommendations', delivery: 'Delivery' } as Record<string, string>)[value] || value; }
function filter<T>(items: T[], query: string, text: (item: T) => string) { const normalized = query.trim().toLowerCase(); return items.filter((item) => !normalized || text(item).toLowerCase().includes(normalized)); }
function sprintName(sprint: Sprint) { return String(sprint.iteration?.name || sprint.iteration?.iterationName || (sprint.status === 'NoSprint' ? 'No current sprint' : 'Not synchronized')); }
function metricValue(value: unknown) { return value == null ? '—' : String(value); }
function velocityDetail(value?: Record<string, any>) { return value?.historicalAverageStoryPoints == null ? 'History unavailable' : `${value.historicalAverageStoryPoints} historical average`; }
function riskLabel(items?: Array<Record<string, any>>) { const first = items?.[0]; return first ? String(first.severity || first.level || 'Needs attention') : 'No active risks'; }
function cleanBranch(value: string) { return value.replace(/^refs\/heads\//, '') || 'Not recorded'; }
function shortDate(value: string) { const date = new Date(value); return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }); }
function formatDate(value: string) { const date = new Date(value); return Number.isNaN(date.getTime()) ? value : date.toLocaleString(); }
async function request<T>(url: string): Promise<T> { const response = await fetch(url); const data = await response.json().catch(() => ({})); if (!response.ok) throw new Error(data?.detail || data?.error?.message || `Azure DevOps Center returned HTTP ${response.status}.`); return data as T; }
