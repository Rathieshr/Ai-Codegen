import React from 'react';

export type PlanningDiffChange = {
  changeId: string;
  action: 'Create' | 'Modify' | 'Keep' | 'Replace' | 'Merge' | 'Split' | 'Ignore' | 'Link' | string;
  artifactType: string;
  title: string;
  parentTitle: string;
  confidence: number;
  reason: string;
  selected: boolean;
  existingWorkItem?: { id: string; type: string; title: string; state: string; revision: number };
  fieldChanges: Array<{ field: string; before: string; after: string }>;
};

export type PlanningDiffData = {
  planningPackId: string;
  recommendation: {
    mode: string; confidence: number; reason: string[];
    recommendedStrategy: { description: string; allowedActions: string[] };
    repositoryMatch: { mode: string; confidence: number; reason: string; modules: string[] };
  };
  proposal: { impact: { writeOperations: number; existingItemsAffected: number; newItems: number; risk: string } };
  diff: {
    diffId: string; status: string; summary: Record<string, number>; changes: PlanningDiffChange[];
    approval: { status: string; approvedBy: string; approvedAt: string; comments?: string };
  };
};

const SIGILS: Record<string, string> = { Create: '+', Modify: '~', Keep: '=', Replace: '±', Merge: '⇉', Split: '⇥', Ignore: '−', Link: '↗' };

export function PlanningDiff({ data, loading, error, busy, canApprove, onApprove, onRetry }: {
  data?: PlanningDiffData; loading: boolean; error: string; busy: boolean; canApprove: boolean;
  onApprove: () => void; onRetry: () => void;
}) {
  if (loading) return <div className="hei-planning-diff-state"><strong>Building Planning Diff...</strong><span>Comparing the proposal with synchronized Azure DevOps work.</span></div>;
  if (error || !data) return <div className="hei-planning-diff-state"><strong>Planning Diff is unavailable.</strong><span>{error || 'Generate this Planning Pack again to add evidence-based change decisions.'}</span><button className="planner-button secondary" type="button" onClick={onRetry}>Retry</button></div>;
  const { recommendation, proposal, diff } = data;
  return <div className="hei-planning-diff">
    <section className="hei-planning-diff-summary">
      <div><span>Planning Mode</span><strong>{friendly(recommendation.mode)}</strong><small>{recommendation.recommendedStrategy?.description}</small></div>
      <div><span>Confidence</span><strong>{recommendation.confidence}%</strong><small>{recommendation.repositoryMatch?.mode || 'Repository evidence unavailable'}</small></div>
      <div><span>Proposed Writes</span><strong>{proposal.impact.writeOperations}</strong><small>{proposal.impact.newItems} create · {proposal.impact.existingItemsAffected} existing</small></div>
      <div><span>Change Risk</span><strong>{proposal.impact.risk}</strong><small>Human approval required</small></div>
    </section>
    <section className="hei-planning-diff-explanation">
      <div><span>HEI Recommendation</span><strong>{recommendation.recommendedStrategy?.description}</strong></div>
      <ul>{(recommendation.reason || []).map((reason) => <li key={reason}>{reason}</li>)}</ul>
    </section>
    <section className="hei-planning-diff-file" aria-label="HEI Planning Diff">
      <header><div><span>HEI Planning Diff</span><h4>Proposed Azure DevOps changes</h4></div><strong className={`hei-planning-status status-${diff.status.toLowerCase()}`}>{diff.status}</strong></header>
      {!diff.changes.length ? <p>No planning changes are proposed.</p> : diff.changes.map((change) => <article key={change.changeId} className={`action-${change.action.toLowerCase()}`}>
        <i aria-hidden="true">{SIGILS[change.action] || '·'}</i>
        <div>
          <span>{change.action} {change.artifactType}</span>
          <h5>{change.title}</h5>
          {change.existingWorkItem ? <small>ADO #{change.existingWorkItem.id} · revision {change.existingWorkItem.revision} · {change.existingWorkItem.state}</small> : change.parentTitle ? <small>Under {change.parentTitle}</small> : null}
          <p>{change.reason}</p>
          {change.fieldChanges?.length ? <div className="hei-planning-field-diff">{change.fieldChanges.map((field) => <section key={field.field}><strong>{friendly(field.field)}</strong><del>{field.before || 'Not set'}</del><ins>{field.after}</ins></section>)}</div> : null}
        </div>
        <b>{change.confidence}%</b>
      </article>)}
    </section>
    <section className="hei-planning-diff-approval">
      <div><span>Diff Approval</span><strong>{diff.approval?.status || diff.status}</strong><small>{diff.approval?.approvedBy ? `Approved by ${diff.approval.approvedBy}` : 'Required before Azure DevOps synchronization.'}</small></div>
      {diff.status !== 'Approved' ? <button className="planner-button primary" type="button" disabled={!canApprove || busy} onClick={onApprove}>{busy ? 'Approving...' : 'Approve Planning Diff'}</button> : <span className="hei-planning-diff-approved">Approved for synchronization</span>}
    </section>
  </div>;
}

function friendly(value: string): string {
  return String(value || '').replace(/_/g, ' ').replace(/([a-z])([A-Z])/g, '$1 $2').replace(/\b\w/g, (letter) => letter.toUpperCase());
}
