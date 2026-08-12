import React, { useEffect, useMemo, useState } from 'react';

type Approval = {
  id: string;
  sourceId: string;
  category: string;
  title: string;
  summary: string;
  status: string;
  requestedAt: string;
  expiresAt?: string;
  requestedBy: string;
  confidence?: number;
  risk?: unknown;
  canApprove: boolean;
  canReject: boolean;
  retryable?: boolean;
  failureReason?: string;
  failedOperation?: string;
  sourceData?: Record<string, unknown>;
  audit?: Array<Record<string, unknown>>;
};

type ApprovalResponse = {
  summary: { total: number; byStatus: Record<string, number>; byCategory: Record<string, number> };
  approvals: Approval[];
  filters: { categories: string[]; statuses: string[] };
};

type Props = {
  baseUrl: string;
  actor: string;
  role: string;
  canApprove: boolean;
  onError?: (message: string) => void;
};

export function ApprovalCenter({ baseUrl, actor, role, canApprove, onError }: Props) {
  const [response, setResponse] = useState<ApprovalResponse>();
  const [selectedId, setSelectedId] = useState('');
  const [selected, setSelected] = useState<Approval>();
  const [compareId, setCompareId] = useState('');
  const [category, setCategory] = useState('');
  const [status, setStatus] = useState('');
  const [search, setSearch] = useState('');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [decisionMessage, setDecisionMessage] = useState('');
  const [view, setView] = useState<'preview' | 'details' | 'compare' | 'audit'>('preview');

  const approvals = response?.approvals || [];
  const comparison = useMemo(() => approvals.find((item) => item.id === compareId), [approvals, compareId]);

  useEffect(() => { void load(); }, [category, status]);
  useEffect(() => {
    if (!selectedId && approvals.length) setSelectedId(approvals[0].id);
  }, [approvals, selectedId]);
  useEffect(() => { if (selectedId) void loadDetails(selectedId); }, [selectedId]);

  async function load() {
    setBusy(true);
    try {
      const query = new URLSearchParams({ category, status, search, limit: '250' });
      const result = await request<ApprovalResponse>(`${baseUrl}/approvals?${query.toString()}`);
      setResponse(result);
      if (selectedId && !result.approvals.some((item) => item.id === selectedId)) setSelectedId(result.approvals[0]?.id || '');
    } catch (error) { onError?.(message(error)); } finally { setBusy(false); }
  }

  async function loadDetails(id: string) {
    try { setSelected(await request<Approval>(`${baseUrl}/approvals/${encodeURIComponent(id)}`)); }
    catch (error) { onError?.(message(error)); }
  }

  async function decide(decision: 'approve' | 'reject') {
    if (!selected) return;
    setBusy(true);
    try {
      const result = await request<{ sourceResult?: { application?: { approvalStatus?: string; applicationResults?: Array<{ result?: { externalIds?: Record<string, string> } }> } } }>(`${baseUrl}/approvals/${encodeURIComponent(selected.id)}/${decision}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ actor, role, reason }),
      });
      if (selected.category === 'ADO Action Packs' && decision === 'approve') {
        const application = result.sourceResult?.application;
        const created = Object.keys(application?.applicationResults?.[0]?.result?.externalIds || {}).length;
        setDecisionMessage(application?.approvalStatus === 'Applied'
          ? created > 0
            ? `${created} Azure DevOps work item${created === 1 ? '' : 's'} created successfully.`
            : 'Azure DevOps work item creation completed successfully.'
          : `Azure DevOps creation finished with status ${application?.approvalStatus || 'Unknown'}. Open Activity for the failure details.`);
      } else {
        setDecisionMessage(`${selected.title} was ${decision === 'approve' ? 'approved' : 'rejected'}.`);
      }
      setReason('');
      await load();
      await loadDetails(selected.id);
    } catch (error) { onError?.(message(error)); } finally { setBusy(false); }
  }

  return (
    <section className="approval-center" aria-label="Approval Center">
      <header className="approval-center-header">
        <div><span className="hei-eyebrow">Human Review</span><h2>Approval Center</h2><p>Review and decide every engineering approval from one queue.</p></div>
        <button type="button" onClick={() => void load()} disabled={busy}>Refresh</button>
      </header>
      {decisionMessage ? <div className="approval-outcome" role="status"><span>{decisionMessage}</span><button type="button" onClick={() => setDecisionMessage('')}>Dismiss</button></div> : null}

      <div className="approval-summary">
        <Summary label="Pending" value={(response?.summary.byStatus.Pending || 0) + (response?.summary.byStatus.NeedsReview || 0) + (response?.summary.byStatus.Draft || 0)} tone="attention" />
        <Summary label="Approved" value={response?.summary.byStatus.Approved || 0} tone="success" />
        <Summary label="Rejected" value={response?.summary.byStatus.Rejected || 0} />
        <Summary label="Expired" value={response?.summary.byStatus.Expired || 0} tone="danger" />
      </div>

      <div className="approval-toolbar">
        <input value={search} onChange={(event) => setSearch(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') void load(); }} placeholder="Search approvals" aria-label="Search approvals" />
        <select value={category} onChange={(event) => setCategory(event.target.value)} aria-label="Filter approval category"><option value="">All categories</option>{response?.filters.categories.map((item) => <option key={item}>{item}</option>)}</select>
        <select value={status} onChange={(event) => setStatus(event.target.value)} aria-label="Filter approval status"><option value="">All statuses</option>{response?.filters.statuses.map((item) => <option key={item}>{item}</option>)}</select>
        <button type="button" onClick={() => void load()}>Search</button>
      </div>

      <div className="approval-layout">
        <nav className="approval-queue" aria-label="Approval queue">
          {approvals.length ? approvals.map((item) => (
            <button key={item.id} type="button" className={item.id === selectedId ? 'selected' : ''} onClick={() => setSelectedId(item.id)}>
              <span><strong>{item.title}</strong><small>{item.category}</small></span><Status value={item.status} />
              <time>{formatDate(item.requestedAt)}</time>
            </button>
          )) : <div className="approval-empty"><strong>No approvals found</strong><span>New approval requests will appear here.</span></div>}
        </nav>

        <article className="approval-detail">
          {selected ? <>
            <div className="approval-detail-title"><div><span>{selected.category}</span><h3>{selected.title}</h3></div><Status value={selected.status} /></div>
            <dl className="approval-meta"><div><dt>Requested by</dt><dd>{selected.requestedBy || 'HEI'}</dd></div><div><dt>Requested</dt><dd>{formatDate(selected.requestedAt)}</dd></div><div><dt>Expires</dt><dd>{selected.expiresAt ? formatDate(selected.expiresAt) : 'No expiry'}</dd></div><div><dt>Confidence</dt><dd>{selected.confidence == null ? 'Not scored' : `${selected.confidence}%`}</dd></div></dl>
            <div className="approval-tabs">
              {(['preview', 'details', 'compare', 'audit'] as const).map((item) => <button key={item} type="button" className={view === item ? 'active' : ''} onClick={() => setView(item)}>{title(item)}</button>)}
            </div>
            {view === 'preview' ? <div className="approval-preview">
              <h4>{selected.retryable ? 'Azure DevOps creation failed' : 'Decision preview'}</h4>
              {selected.retryable ? <div className="approval-failure" role="alert">
                <strong>{selected.failedOperation ? `${selected.failedOperation} failed` : 'Work items were not fully created'}</strong>
                <p>{selected.failureReason || 'Azure DevOps returned a failure without additional details. Review diagnostics before retrying.'}</p>
                <small>The pack remains approved. Retry resumes safely using the same idempotency key.</small>
              </div> : <p>{selected.summary || 'Review the source artifact details before making a decision.'}</p>}
            </div> : null}
            {view === 'details' ? <pre className="approval-json">{JSON.stringify(selected.sourceData || {}, null, 2)}</pre> : null}
            {view === 'compare' ? <div className="approval-compare"><label>Compare with<select value={compareId} onChange={(event) => setCompareId(event.target.value)}><option value="">Select an approval</option>{approvals.filter((item) => item.id !== selected.id).map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label><div><CompareCard item={selected} /><CompareCard item={comparison} /></div></div> : null}
            {view === 'audit' ? <div className="approval-audit">{selected.audit?.length ? selected.audit.map((event, index) => <div key={String(event.id || index)}><strong>{String(event.what || event.eventType || 'Approval event')}</strong><span>{String(event.who || 'HEI')} · {formatDate(String(event.when || ''))}</span><p>{String(event.why || '')}</p></div>) : <p>No audit events recorded for this artifact.</p>}</div> : null}
            <div className="approval-decision">
              <label>Decision note<input value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Optional reason" /></label>
              <div><button type="button" className="secondary" onClick={() => void decide('reject')} disabled={!canApprove || !selected.canReject || busy}>{selected.retryable ? 'Close Failed Pack' : 'Reject'}</button><button type="button" className="primary" onClick={() => void decide('approve')} disabled={!canApprove || !selected.canApprove || busy}>{selected.retryable ? 'Retry Azure DevOps Creation' : selected.category === 'ADO Action Packs' ? 'Approve & Create in Azure DevOps' : 'Approve'}</button></div>
              {!canApprove ? <small>Your current role has read-only access.</small> : null}
            </div>
          </> : <div className="approval-empty"><strong>Select an approval</strong><span>Preview its evidence, comparison, and audit history.</span></div>}
        </article>
      </div>
    </section>
  );
}

function Summary({ label, value, tone = '' }: { label: string; value: number; tone?: string }) { return <div className={tone}><span>{label}</span><strong>{value}</strong></div>; }
function Status({ value }: { value: string }) { return <span className={`approval-status status-${value.toLowerCase()}`}>{value}</span>; }
function CompareCard({ item }: { item?: Approval }) { return <section>{item ? <><small>{item.category}</small><h4>{item.title}</h4><Status value={item.status} /><p>{item.summary || 'No summary available.'}</p></> : <p>Select another approval to compare.</p>}</section>; }
function title(value: string) { return value.charAt(0).toUpperCase() + value.slice(1); }
function formatDate(value: string) { if (!value) return 'Not recorded'; const date = new Date(value); return Number.isNaN(date.getTime()) ? value : date.toLocaleString(); }
function message(error: unknown) { return error instanceof Error ? error.message : String(error); }
async function request<T = unknown>(url: string, init?: RequestInit): Promise<T> { const response = await fetch(url, init); const data = await response.json().catch(() => ({})); if (!response.ok) throw new Error(data?.error?.message || `Request failed (${response.status}).`); return data as T; }
