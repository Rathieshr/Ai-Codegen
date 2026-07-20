import React from 'react';

export type PlanningOverviewData = {
  schemaVersion: string;
  planningId: string;
  requirement: {
    name: string; status: string; repository: string; repositoryId: string; branch: string;
    confidence: number; quality: number; planningReadiness: string;
  };
  metrics: {
    engineeringDays: number; sprintCount: number; features: number; stories: number; tasks: number;
    dependencies: number; openQuestions: number; repositoryReuse: number;
  };
  cards: {
    planningMetrics: { features: number; stories: number; tasks: number; dependencies: number };
    repositorySummary: { name: string; branch: string; mode: string; reuse: number };
    engineeringEstimate: { days: number; sprints: number; storyPoints: number; risk: string };
    requirementQuality: { score: number; openQuestions: string[]; acceptanceCriteria: number };
    aiConfidence: { score: number; status: string; warnings: string[] };
    recentChanges: Array<{ status: string; version: number; actor: string; changedAt: string }>;
  };
  charts: {
    storyDistribution: DistributionValue[];
    taskDistribution: DistributionValue[];
    estimateBreakdown: DistributionValue[];
  };
  engineeringEstimate?: Record<string, unknown> | null;
  dependencies: string[];
  openQuestions: string[];
  planningReadiness: { status: string; score: number; blockers: string[]; warnings: string[] };
  updatedAt: string;
  version: number;
};

type DistributionValue = { label: string; value: number; unit?: string };

export function PlanningOverview({ data, loading, error, canApprove, onHierarchy, onEstimate, onDependencies, onApprove }: {
  data?: PlanningOverviewData;
  loading: boolean;
  error: string;
  canApprove: boolean;
  onHierarchy: () => void;
  onEstimate: () => void;
  onDependencies: () => void;
  onApprove: () => void;
}) {
  if (loading) return <div className="hei-planning-overview-state"><strong>Loading Planning Overview...</strong><span>Reading the current Planning Pack and persisted estimate.</span></div>;
  if (!data) return <div className="hei-planning-overview-state"><strong>Planning Overview is not available.</strong><span>{error || 'Generate a Planning Pack to review executive planning scope.'}</span></div>;
  const { requirement, metrics, cards } = data;
  return <div className="hei-planning-executive-overview">
    <section className="hei-planning-executive-summary">
      <div><span>Requirement</span><strong>{requirement.name}</strong><small>{requirement.status} | {requirement.repository}</small></div>
      <OverviewMetric label="Confidence" value={`${requirement.confidence}%`} />
      <OverviewMetric label="Engineering Days" value={formatNumber(metrics.engineeringDays)} />
      <OverviewMetric label="Sprint Count" value={formatNumber(metrics.sprintCount)} />
      <OverviewMetric label="Features" value={metrics.features} />
      <OverviewMetric label="Stories" value={metrics.stories} />
      <OverviewMetric label="Tasks" value={metrics.tasks} />
      <OverviewMetric label="Dependencies" value={metrics.dependencies} />
      <OverviewMetric label="Open Questions" value={metrics.openQuestions} attention={metrics.openQuestions > 0} />
      <OverviewMetric label="Repository Reuse" value={`${metrics.repositoryReuse}%`} />
      <OverviewMetric label="Planning Readiness" value={requirement.planningReadiness || 'Pending'} />
    </section>

    <section className="hei-planning-overview-cards" aria-label="Planning overview cards">
      <OverviewCard title="Planning Metrics"><Fact label="Features" value={cards.planningMetrics.features} /><Fact label="Stories" value={cards.planningMetrics.stories} /><Fact label="Tasks" value={cards.planningMetrics.tasks} /><Fact label="Dependencies" value={cards.planningMetrics.dependencies} /></OverviewCard>
      <OverviewCard title="Repository Summary"><Fact label="Repository" value={cards.repositorySummary.name} /><Fact label="Branch" value={cards.repositorySummary.branch || 'Branch Pending'} /><Fact label="Context" value={cards.repositorySummary.mode} /><Fact label="Reuse" value={`${cards.repositorySummary.reuse}%`} /></OverviewCard>
      <OverviewCard title="Engineering Estimate"><Fact label="Engineering Days" value={formatNumber(cards.engineeringEstimate.days)} /><Fact label="Sprint Count" value={formatNumber(cards.engineeringEstimate.sprints)} /><Fact label="Story Points" value={cards.engineeringEstimate.storyPoints} /><Fact label="Risk" value={cards.engineeringEstimate.risk} /></OverviewCard>
      <OverviewCard title="Requirement Quality"><Score value={cards.requirementQuality.score} /><Fact label="Acceptance Criteria" value={cards.requirementQuality.acceptanceCriteria} /><Fact label="Open Questions" value={cards.requirementQuality.openQuestions.length} /></OverviewCard>
      <OverviewCard title="AI Confidence"><Score value={cards.aiConfidence.score} /><Fact label="Assessment" value={cards.aiConfidence.status} /><Fact label="Warnings" value={cards.aiConfidence.warnings.length} /></OverviewCard>
      <OverviewCard title="Recent Changes">{cards.recentChanges.length ? <ol className="hei-planning-change-list">{cards.recentChanges.slice(0, 4).map((change, index) => <li key={`${change.version}-${change.changedAt}-${index}`}><strong>v{change.version} | {change.status}</strong><span>{change.actor} | {formatDate(change.changedAt)}</span></li>)}</ol> : <p className="hei-planning-card-empty">No version changes recorded yet.</p>}</OverviewCard>
    </section>

    <section className="hei-planning-overview-charts" aria-label="Planning distribution charts">
      <DistributionChart title="Story Distribution" values={data.charts.storyDistribution} empty="Stories will be grouped by Feature after hierarchy generation." />
      <DistributionChart title="Task Distribution" values={data.charts.taskDistribution} empty="Tasks will be grouped by Story after task planning." />
      <DistributionChart title="Estimate Breakdown" values={data.charts.estimateBreakdown} empty="Generate the engineering estimate to view effort distribution." />
    </section>

    <section className="hei-planning-overview-readiness">
      <div><span>Planning Readiness</span><strong>{data.planningReadiness.status || 'Pending'}</strong><small>{data.planningReadiness.score}% readiness score</small></div>
      <div>{data.planningReadiness.blockers.length ? <p>{data.planningReadiness.blockers.length} blocker{data.planningReadiness.blockers.length === 1 ? '' : 's'} must be resolved.</p> : <p>No blocking planning issues detected.</p>}{data.planningReadiness.warnings.length ? <p>{data.planningReadiness.warnings.length} warning{data.planningReadiness.warnings.length === 1 ? '' : 's'} should be reviewed.</p> : null}</div>
    </section>

    <nav className="hei-planning-overview-actions" aria-label="Planning overview actions">
      <button className="planner-button secondary" type="button" onClick={onHierarchy}>Review Hierarchy</button>
      <button className="planner-button secondary" type="button" onClick={onEstimate}>Review Estimate</button>
      <button className="planner-button secondary" type="button" onClick={onDependencies}>Review Dependencies</button>
      <button className="planner-button primary" type="button" onClick={onApprove} disabled={!canApprove}>Approve Planning</button>
    </nav>
  </div>;
}

function OverviewMetric({ label, value, attention = false }: { label: string; value: string | number; attention?: boolean }) {
  return <div className={attention ? 'attention' : ''}><span>{label}</span><strong>{value}</strong></div>;
}

function OverviewCard({ title, children }: { title: string; children: React.ReactNode }) {
  return <article><h4>{title}</h4><div className="hei-planning-card-content">{children}</div></article>;
}

function Fact({ label, value }: { label: string; value: string | number }) {
  return <div className="hei-planning-overview-fact"><span>{label}</span><strong>{value}</strong></div>;
}

function Score({ value }: { value: number }) {
  return <div className="hei-planning-score"><strong>{value}%</strong><div><span style={{ width: `${Math.max(0, Math.min(100, value))}%` }} /></div></div>;
}

function DistributionChart({ title, values, empty }: { title: string; values: DistributionValue[]; empty: string }) {
  const maximum = Math.max(1, ...values.map((item) => item.value));
  return <article className="hei-planning-distribution"><h4>{title}</h4>{values.length ? <div>{values.map((item) => <div className="hei-planning-distribution-row" key={item.label}><span title={item.label}>{item.label}</span><div><i style={{ width: `${Math.max(3, item.value / maximum * 100)}%` }} /></div><strong>{formatNumber(item.value)}{item.unit ? ` ${item.unit}` : ''}</strong></div>)}</div> : <p>{empty}</p>}</article>;
}

function formatNumber(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

function formatDate(value: string): string {
  if (!value) return 'Time not recorded';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}
