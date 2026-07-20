import React, { ReactNode } from 'react';

export const PLANNING_TABS = ['Overview', 'Hierarchy', 'Traceability', 'Dependencies', 'Estimate', 'Review', 'Approval'] as const;
export type PlanningTab = typeof PLANNING_TABS[number];

export function PlanningWorkspace({ header, tabs, children, actionPanel, footer }: {
  header: ReactNode; tabs: ReactNode; children: ReactNode; actionPanel: ReactNode; footer: ReactNode;
}) {
  return <section className="hei-planning-workspace-shell" aria-label="Planning Workspace">
    {header}
    {tabs}
    <div className="hei-planning-workspace-body">
      <main className="hei-planning-workspace-content">{children}</main>
      <aside className="hei-planning-action-panel" aria-label="Planning actions">{actionPanel}</aside>
    </div>
    <footer className="hei-planning-workspace-footer">{footer}</footer>
  </section>;
}

export function PlanningTabs({ active, onChange }: { active: PlanningTab; onChange: (tab: PlanningTab) => void }) {
  return <nav className="hei-planning-tabs" aria-label="Planning workspace sections">
    {PLANNING_TABS.map((tab) => <button key={tab} type="button" role="tab" aria-selected={active === tab} className={active === tab ? 'active' : ''} onClick={() => onChange(tab)}>{tab}</button>)}
  </nav>;
}

export function PlanningHeader({ name, status, confidence, repository, version, updated }: {
  name: string; status: string; confidence: number; repository: string; version: number; updated: string;
}) {
  return <header className="hei-planning-workspace-header">
    <div><span>Planning Pack</span><h2>{name}</h2><p>Review, refine, estimate, and approve engineering planning in one workspace.</p></div>
    <div className="hei-planning-header-facts">
      <PlanningStatusBadge status={status} />
      <span><small>Confidence</small><strong>{confidence}%</strong></span>
      <span><small>Repository</small><strong>{repository || 'Repository Pending'}</strong></span>
      <PlanningVersion version={version} />
      <span><small>Last Updated</small><strong>{updated || 'Not recorded'}</strong></span>
    </div>
  </header>;
}

export function PlanningContent({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  return <section className="hei-planning-tab-content"><header><h3>{title}</h3><p>{description}</p></header>{children}</section>;
}

export function PlanningActions({ status, canGenerate, canSave, canApprove, busy, onGenerate, onSave, onApprove, onExport, primaryLabel = 'Approve', compact = false }: {
  status: string; canGenerate: boolean; canSave: boolean; canApprove: boolean; busy: boolean;
  onGenerate: () => void; onSave: () => void; onApprove: () => void; onExport: () => void; primaryLabel?: string; compact?: boolean;
}) {
  return <div className={`hei-planning-workspace-actions ${compact ? 'compact' : ''}`}>
    {!compact ? <><span>Current Status</span><PlanningStatusBadge status={status} /><p>{canApprove ? 'Review is ready for approval.' : canSave ? 'Save the draft before requesting approval.' : 'This planning artifact is read only.'}</p></> : null}
    <button className="planner-button secondary" type="button" onClick={onGenerate} disabled={!canGenerate || busy}>Generate</button>
    <button className="planner-button secondary" type="button" onClick={onSave} disabled={!canSave || busy}>Save Draft</button>
    <button className="planner-button primary" type="button" onClick={onApprove} disabled={!canApprove || busy}>{primaryLabel}</button>
    <button className="planner-button secondary" type="button" onClick={onExport}>Export</button>
  </div>;
}

export function PlanningStatusBadge({ status }: { status: string }) {
  const normalized = (status || 'Draft').toLowerCase().replace(/[^a-z0-9]+/g, '-');
  return <span className={`hei-planning-status status-${normalized}`}>{status || 'Draft'}</span>;
}

export function PlanningVersion({ version }: { version: number }) {
  return <span><small>Version</small><strong>v{version || 1}</strong></span>;
}
