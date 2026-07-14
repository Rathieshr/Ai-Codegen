import React, { FormEvent, useState } from 'react';
import { HEIHostContext } from './host';

const INPUT_TYPES = ['Business Requirement', 'PRD', 'BRD', 'Meeting Notes', 'Bug Report', 'Azure DevOps Work Item', 'Customer Request'];

type IntakeResult = {
  requirementId: string;
  planningPackId: string;
  title: string;
  status: string;
  approvalRequired: boolean;
  context: { status?: string; confidence?: number; freshnessStatus?: string; sourceSummary?: Array<{ source?: string; available?: boolean; selected?: number }> };
  correlationId: string;
};

export function NewRequirementWorkspace({ baseUrl, context, onOpenApprovals, onError }: {
  baseUrl: string;
  context: HEIHostContext;
  onOpenApprovals: () => void;
  onError: (message: string) => void;
}) {
  const [inputType, setInputType] = useState(INPUT_TYPES[0]);
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<IntakeResult>();

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const response = await fetch(`${baseUrl}/requirements/intake`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-HEI-User': context.user.id },
        body: JSON.stringify({
          inputType, title, content,
          organization: context.organization.name,
          projectId: context.project.id || context.project.name,
          projectName: context.project.name,
          teamId: context.team.id,
          iterationId: context.sprint.id,
          iterationPath: context.sprint.path,
          repositoryId: context.repository.id,
          branch: context.repository.branch,
          workItemId: context.route.workItemId,
          actor: context.user.name,
          correlationId: context.correlationId,
        }),
      });
      const value = await response.json() as IntakeResult & { error?: { message?: string } };
      if (!response.ok) throw new Error(value.error?.message || `Requirement Intake returned HTTP ${response.status}.`);
      setResult(value);
    } catch (error) {
      onError(error instanceof Error ? error.message : 'Unable to create the Planning Pack.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="hei-requirement-workspace" aria-label="New Requirement">
      <header><div><span>Planning Intake</span><h2>New Requirement</h2><p>Start engineering work from a requirement, document, customer request, or bug report.</p></div>{result ? <Status value={result.status} /> : null}</header>
      {result ? (
        <div className="hei-requirement-result" aria-live="polite">
          <div><span>Planning Pack</span><h3>{result.title}</h3><p>HEI prepared a context-grounded Planning Pack. No Azure DevOps work item has been created or changed.</p></div>
          <div className="hei-requirement-signals">
            <Signal label="Context" value={result.context.status || 'Needs Review'} />
            <Signal label="Confidence" value={`${Math.round(Number(result.context.confidence || 0) * 100)}%`} />
            <Signal label="Freshness" value={result.context.freshnessStatus || 'Unknown'} />
            <Signal label="Approval" value={result.approvalRequired ? 'Required' : 'Not required'} />
          </div>
          <details><summary>Context sources</summary><ul>{(result.context.sourceSummary || []).map((source, index) => <li key={`${source.source}-${index}`}><strong>{source.source}</strong> {source.available ? `${source.selected || 0} selected` : 'Unavailable'}</li>)}</ul></details>
          <div className="hei-requirement-actions"><button className="planner-button primary" type="button" onClick={onOpenApprovals}>Review Planning Pack</button><button className="planner-button secondary" type="button" onClick={() => { setResult(undefined); setTitle(''); setContent(''); }}>Start Another</button></div>
          <small>Correlation: {result.correlationId}</small>
        </div>
      ) : (
        <form className="hei-requirement-form" onSubmit={submit}>
          <label><span>Input type</span><select value={inputType} onChange={(event) => setInputType(event.target.value)}>{INPUT_TYPES.map((value) => <option key={value}>{value}</option>)}</select></label>
          <label><span>Requirement title</span><input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="What engineering outcome is needed?" maxLength={180} required /></label>
          <label className="wide"><span>Requirement content</span><textarea value={content} onChange={(event) => setContent(event.target.value)} placeholder="Describe the business goal, users, expected outcome, constraints, and known acceptance criteria." rows={12} required /></label>
          <div className="hei-intake-context"><strong>Current Azure DevOps context</strong><span>{context.project.name || 'Project unavailable'}</span><span>{context.team.name || 'Team unavailable'}</span><span>{context.repository.name || 'Repository will be resolved by HEI'}</span></div>
          <button className="planner-button primary" type="submit" disabled={busy || !title.trim() || !content.trim()}>{busy ? 'Preparing Planning Pack...' : 'Analyze Requirement'}</button>
        </form>
      )}
    </section>
  );
}

function Signal({ label, value }: { label: string; value: string }) { return <div><span>{label}</span><strong>{value}</strong></div>; }
function Status({ value }: { value: string }) { return <span className="hei-operation-chip warning">{value}</span>; }
