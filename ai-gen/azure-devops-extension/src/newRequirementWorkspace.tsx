import React, { ChangeEvent, FormEvent, useState } from 'react';
import { HEIHostContext } from './host';

type SourceType = 'PasteRequirement' | 'UploadDocument' | 'AzureDevOpsWorkItem' | 'MeetingTranscript';

const SOURCES: Array<{ id: SourceType; label: string; description: string }> = [
  { id: 'PasteRequirement', label: 'Paste Requirement', description: 'Enter a business need or engineering outcome.' },
  { id: 'UploadDocument', label: 'Upload Document', description: 'Use a text, Markdown, BRD, or PRD document.' },
  { id: 'AzureDevOpsWorkItem', label: 'Azure DevOps Work Item', description: 'Use a synchronized Epic, Feature, Story, Task, or Bug.' },
  { id: 'MeetingTranscript', label: 'Meeting Transcript', description: 'Turn recorded decisions and needs into planning context.' },
];

const FUTURE_SOURCES = ['Confluence', 'SharePoint', 'Notion', 'Email', 'REST API'];

type IntakeResult = {
  requirementId: string;
  planningPackId: string;
  title: string;
  status: string;
  approvalRequired: boolean;
  context: { status?: string; confidence?: number; freshnessStatus?: string; sourceSummary?: Array<{ source?: string; available?: boolean; selected?: number }> };
  correlationId: string;
  requirementAnalysis?: RequirementAnalysisResult;
};

type AnalysisFinding = { text: string; reason: string; evidence?: string; confidence: number };
type RepositoryCandidate = {
  repositoryId: string; name: string; url: string; defaultBranch: string; repositoryType: string;
  confidence: number; reason: string; evidence: string[]; matchedModules: string[];
  matchedTechnologies: string[]; snapshotVersion: string; manualOverride?: boolean;
};
type RepositorySuggestion = {
  detectionId: string; requirementId: string; suggestedRepository?: RepositoryCandidate;
  confidence: number; reason: string; alternativeRepositories: RepositoryCandidate[];
  availableRepositories: RepositoryCandidate[]; source: 'Detection' | 'ManualOverride'; detectedAt: string;
};
type RequirementAnalysisResult = {
  analysisId: string;
  requirementId: string;
  contextVersion: string;
  contentHash: string;
  requirementSummary: string;
  planningRequirement: string;
  reviewStatus: 'Pending' | 'Approved' | 'Cancelled';
  reviewContext: {
    source: string;
    repository: { id: string; name: string; status: string };
    documentType: string;
    engineeringMemory: { status: string; message: string };
    repositoryReuse: { status: string; message: string };
  };
  planningReadiness: { status: 'Ready' | 'NeedsReview' | 'Blocked'; readyForPlanning: boolean; score: number; blockers: string[]; warnings: string[] };
  requirementQualityScore: number;
  confidence: number;
  businessGoals: string[];
  functionalRequirements: string[];
  nonFunctionalRequirements: string[];
  acceptanceCriteria: string[];
  actors: string[];
  businessRules: string[];
  constraints: string[];
  dependencies: string[];
  risks: string[];
  openQuestions: string[];
  assumptions: string[];
  missingAcceptanceCriteria: AnalysisFinding[];
  ambiguousRequirements: AnalysisFinding[];
  conflictingRequirements: AnalysisFinding[];
  duplicateRequirements: AnalysisFinding[];
  repositorySuggestion?: RepositorySuggestion;
};

type IngestionResult = {
  requirementId: string;
  sourceType: SourceType;
  status: string;
  title: string;
  planningReady: boolean;
  contextVersion: string;
  contentHash: string;
  correlationId: string;
};

type DocumentResult = {
  documentId: string;
  fileName: string;
  mediaType: string;
  status: string;
  sizeBytes: number;
  readyForAnalysis: boolean;
  parsed?: { title?: string; detectedType?: string; pages?: number; language?: string };
};

type TranscriptFinding = { findingId: string; text: string; speaker?: string; timestamp?: string; confidence: number; evidence: string };
type TranscriptResult = {
  transcriptId: string;
  sourceType: string;
  status: string;
  requirementContextId: string;
  readyForPlanning: boolean;
  analysis: {
    meetingTitle: string;
    participants: string[];
    date: string;
    meetingSummary: string;
    requirements: TranscriptFinding[];
    actionItems: TranscriptFinding[];
    decisions: TranscriptFinding[];
    risks: TranscriptFinding[];
    openQuestions: TranscriptFinding[];
    dependencies: TranscriptFinding[];
    warnings: string[];
  };
};

type AdoWorkItemImportResult = {
  workItemId: string;
  workItemRevision: number;
  status: string;
  requirementContextId: string;
  currentWorkItem: {
    workItemType: string;
    title: string;
    description: string;
    state: string;
    area: string;
    iteration: string;
    tags: string[];
    comments: Array<{ commentId: string; text: string; createdBy: string }>;
    attachments: Array<{ name: string; url: string }>;
    linkedWorkItems: Array<{ workItemId: string; relationship: string; isDependency: boolean }>;
  };
  requirementSummary: {
    title: string;
    summary: string;
    acceptanceCriteria: string[];
    dependencies: Array<{ workItemId: string; relationship: string }>;
    missingInformation: string[];
    readyForPlanning: boolean;
  };
};

export function NewRequirementWorkspace({ baseUrl, context, onOpenApprovals, onError }: {
  baseUrl: string;
  context: HEIHostContext;
  onOpenApprovals: () => void;
  onError: (message: string) => void;
}) {
  const [sourceType, setSourceType] = useState<SourceType>('PasteRequirement');
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [workItemId, setWorkItemId] = useState(context.route.workItemId || '');
  const [documentName, setDocumentName] = useState('');
  const [documentMediaType, setDocumentMediaType] = useState('text/plain');
  const [documentContentBase64, setDocumentContentBase64] = useState('');
  const [documentResult, setDocumentResult] = useState<DocumentResult>();
  const [transcriptFormat, setTranscriptFormat] = useState<'TeamsTranscript' | 'ZoomTranscript' | 'TextTranscript'>('TeamsTranscript');
  const [transcriptResult, setTranscriptResult] = useState<TranscriptResult>();
  const [adoImportResult, setAdoImportResult] = useState<AdoWorkItemImportResult>();
  const [busyStage, setBusyStage] = useState<'uploading' | 'parsing' | 'analyzing' | 'ingesting' | 'planning' | ''>('');
  const [ingestion, setIngestion] = useState<IngestionResult>();
  const [requirementAnalysis, setRequirementAnalysis] = useState<RequirementAnalysisResult>();
  const [editingReview, setEditingReview] = useState(false);
  const [reviewTitle, setReviewTitle] = useState('');
  const [reviewContent, setReviewContent] = useState('');
  const [result, setResult] = useState<IntakeResult>();

  async function readDocument(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    if (file.size > 25 * 1024 * 1024) {
      onError('Requirement documents must be 25 MB or smaller.');
      return;
    }
    try {
      setDocumentName(file.name);
      setDocumentMediaType(file.type || 'text/plain');
      setDocumentContentBase64(await fileToBase64(file));
      if (!title.trim()) setTitle(file.name.replace(/\.[^.]+$/, '').replace(/[-_]+/g, ' '));
    } catch {
      onError('The selected document could not be read as text.');
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusyStage('ingesting');
    try {
      let documentId = '';
      if (sourceType === 'UploadDocument') {
        setBusyStage('uploading');
        const uploadResponse = await fetch(`${baseUrl}/documents/upload`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-HEI-User': context.user.id },
          body: JSON.stringify({ fileName: documentName, mediaType: documentMediaType, contentBase64: documentContentBase64, projectId: context.project.id || context.project.name, actor: context.user.name }),
        });
        const uploaded = await uploadResponse.json() as DocumentResult & { error?: { message?: string } };
        if (!uploadResponse.ok) throw new Error(uploaded.error?.message || `Document Upload returned HTTP ${uploadResponse.status}.`);
        setBusyStage('parsing');
        const parseResponse = await fetch(`${baseUrl}/documents/${encodeURIComponent(uploaded.documentId)}/parse`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-HEI-User': context.user.id }, body: '{}' });
        const parsed = await parseResponse.json() as DocumentResult & { error?: { message?: string } };
        if (!parseResponse.ok) throw new Error(parsed.error?.message || `Document Parsing returned HTTP ${parseResponse.status}.`);
        setDocumentResult(parsed);
        documentId = parsed.documentId;
      }
      let ingested: IngestionResult & { error?: { message?: string } };
      if (sourceType === 'AzureDevOpsWorkItem') {
        setBusyStage('analyzing');
        const projectId = context.project.id || context.project.name;
        const currentResponse = await fetch(`${baseUrl}/ado/workitem/${encodeURIComponent(workItemId)}?projectId=${encodeURIComponent(projectId)}`, {
          headers: { 'X-HEI-User': context.user.id, 'X-Correlation-ID': context.correlationId },
        });
        const current = await currentResponse.json() as AdoWorkItemImportResult['currentWorkItem'] & { error?: { message?: string } };
        if (!currentResponse.ok) throw new Error(current.error?.message || `Azure DevOps Work Item Import returned HTTP ${currentResponse.status}.`);
        const analysisResponse = await fetch(`${baseUrl}/ado/workitem/${encodeURIComponent(workItemId)}/analyze`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-HEI-User': context.user.id, 'X-Correlation-ID': context.correlationId },
          body: JSON.stringify({ projectId, repositoryId: context.repository.id, repositoryName: context.repository.name, branch: context.repository.branch, actor: context.user.name }),
        });
        const analyzed = await analysisResponse.json() as AdoWorkItemImportResult & { error?: { message?: string } };
        if (!analysisResponse.ok) throw new Error(analyzed.error?.message || `Azure DevOps Work Item Analysis returned HTTP ${analysisResponse.status}.`);
        setAdoImportResult(analyzed);
        if (!analyzed.requirementSummary.readyForPlanning || !analyzed.requirementContextId) {
          throw new Error(analyzed.requirementSummary.missingInformation[0] || 'The work item requires more information before Planning.');
        }
        ingested = {
          requirementId: analyzed.requirementContextId,
          sourceType: 'AzureDevOpsWorkItem',
          status: analyzed.status,
          title: analyzed.requirementSummary.title,
          planningReady: true,
          contextVersion: '1.0',
          contentHash: '',
          correlationId: context.correlationId,
        };
      } else if (sourceType === 'MeetingTranscript') {
        setBusyStage('uploading');
        const fileFormat = documentName.toLowerCase().endsWith('.docx') ? 'DOCX' : documentName.toLowerCase().endsWith('.txt') ? 'TXT' : transcriptFormat;
        const uploadResponse = await fetch(`${baseUrl}/transcripts/upload`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-HEI-User': context.user.id },
          body: JSON.stringify({
            sourceType: fileFormat,
            title,
            transcript: content,
            fileName: documentName,
            mediaType: documentMediaType,
            contentBase64: documentContentBase64,
            organization: context.organization.name,
            projectId: context.project.id || context.project.name,
            projectName: context.project.name,
            teamId: context.team.id,
            repositoryId: context.repository.id,
            repositoryName: context.repository.name,
            branch: context.repository.branch,
            actor: context.user.name,
            correlationId: context.correlationId,
          }),
        });
        const uploaded = await uploadResponse.json() as TranscriptResult & { error?: { message?: string } };
        if (!uploadResponse.ok) throw new Error(uploaded.error?.message || `Transcript Upload returned HTTP ${uploadResponse.status}.`);
        setBusyStage('analyzing');
        const analysisResponse = await fetch(`${baseUrl}/transcripts/analyze`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-HEI-User': context.user.id },
          body: JSON.stringify({ transcriptId: uploaded.transcriptId }),
        });
        const analyzed = await analysisResponse.json() as TranscriptResult & { error?: { message?: string } };
        if (!analysisResponse.ok) throw new Error(analyzed.error?.message || `Transcript Analysis returned HTTP ${analysisResponse.status}.`);
        setTranscriptResult(analyzed);
        if (!analyzed.readyForPlanning || !analyzed.requirementContextId) {
          throw new Error(analyzed.analysis?.warnings?.[0] || 'No explicit engineering requirements were found. Review the transcript before Planning.');
        }
        ingested = {
          requirementId: analyzed.requirementContextId,
          sourceType: 'MeetingTranscript',
          status: analyzed.status,
          title: analyzed.analysis.meetingTitle,
          planningReady: analyzed.readyForPlanning,
          contextVersion: '1.0',
          contentHash: '',
          correlationId: context.correlationId,
        };
      } else {
        setBusyStage('ingesting');
      const sourcePayload = sourceType === 'UploadDocument' ? { title, documentId } : { title, content };
      const common = {
        sourceType,
        ...sourcePayload,
        organization: context.organization.name,
        projectId: context.project.id || context.project.name,
        projectName: context.project.name,
        teamId: context.team.id,
        iterationId: context.sprint.id,
        iterationPath: context.sprint.path,
        repositoryId: context.repository.id,
        repositoryName: context.repository.name,
        branch: context.repository.branch,
        actor: context.user.name,
        correlationId: context.correlationId,
      };
      const ingestResponse = await fetch(`${baseUrl}/requirements/ingest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-HEI-User': context.user.id },
        body: JSON.stringify(common),
      });
      ingested = await ingestResponse.json() as IngestionResult & { error?: { message?: string } };
      if (!ingestResponse.ok) throw new Error(ingested.error?.message || `Requirement Ingestion returned HTTP ${ingestResponse.status}.`);
      }
      setIngestion(ingested);

      setBusyStage('analyzing');
      const requirementAnalysisResponse = await fetch(`${baseUrl}/requirements/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-HEI-User': context.user.id, 'X-Correlation-ID': context.correlationId },
        body: JSON.stringify({ requirementId: ingested.requirementId }),
      });
      const analyzedRequirement = await requirementAnalysisResponse.json() as RequirementAnalysisResult & { error?: { message?: string } };
      if (!requirementAnalysisResponse.ok) throw new Error(analyzedRequirement.error?.message || `Requirement Analysis returned HTTP ${requirementAnalysisResponse.status}.`);
      setRequirementAnalysis(analyzedRequirement);
      setReviewTitle(ingested.title);
      setReviewContent(analyzedRequirement.planningRequirement);
      if (analyzedRequirement.planningReadiness.status === 'Blocked') {
        throw new Error(analyzedRequirement.planningReadiness.blockers[0] || 'Resolve the requirement conflicts before Planning.');
      }
    } catch (error) {
      onError(error instanceof Error ? error.message : 'Unable to ingest the requirement.');
    } finally {
      setBusyStage('');
    }
  }

  async function continueToPlanning() {
    if (!ingestion || !requirementAnalysis) return;
    setBusyStage('planning');
    try {
      const approvalResponse = await fetch(`${baseUrl}/requirements/${encodeURIComponent(ingestion.requirementId)}/analysis/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-HEI-User': context.user.id },
        body: JSON.stringify({ actor: context.user.name }),
      });
      const approved = await approvalResponse.json() as RequirementAnalysisResult & { error?: { message?: string } };
      if (!approvalResponse.ok) throw new Error(approved.error?.message || `Requirement Approval returned HTTP ${approvalResponse.status}.`);
      setRequirementAnalysis(approved);
      const planningResponse = await fetch(`${baseUrl}/planning/from-requirement`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-HEI-User': context.user.id },
        body: JSON.stringify({ requirementId: ingestion.requirementId, actor: context.user.name }),
      });
      const planning = await planningResponse.json() as IntakeResult & { error?: { message?: string } };
      if (!planningResponse.ok) throw new Error(planning.error?.message || `Planning Intake returned HTTP ${planningResponse.status}.`);
      setResult(planning);
    } catch (error) {
      onError(error instanceof Error ? error.message : 'Unable to continue to Planning.');
    } finally {
      setBusyStage('');
    }
  }

  async function reanalyze() {
    if (!ingestion) return;
    setBusyStage('analyzing');
    try {
      const response = await fetch(`${baseUrl}/requirements/${encodeURIComponent(ingestion.requirementId)}/analysis/reanalyze`, { method: 'POST', headers: { 'X-HEI-User': context.user.id } });
      const analyzed = await response.json() as RequirementAnalysisResult & { error?: { message?: string } };
      if (!response.ok) throw new Error(analyzed.error?.message || `Requirement Re-analysis returned HTTP ${response.status}.`);
      setRequirementAnalysis(analyzed);
      setIngestion({ ...ingestion, contextVersion: analyzed.contextVersion || ingestion.contextVersion, contentHash: analyzed.contentHash || ingestion.contentHash });
      setReviewContent(analyzed.planningRequirement);
      setEditingReview(false);
    } catch (error) {
      onError(error instanceof Error ? error.message : 'Unable to re-analyze the requirement.');
    } finally {
      setBusyStage('');
    }
  }

  async function overrideRepository(repositoryId: string) {
    if (!ingestion || !repositoryId) return;
    setBusyStage('analyzing');
    try {
      const response = await fetch(`${baseUrl}/repositories/suggestions/${encodeURIComponent(ingestion.requirementId)}/override`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-HEI-User': context.user.id },
        body: JSON.stringify({ repositoryId, actor: context.user.name, reason: 'Requirement Summary manual override' }),
      });
      const overridden = await response.json() as { error?: string };
      if (!response.ok) throw new Error(overridden.error || `Repository override returned HTTP ${response.status}.`);
      const analysisResponse = await fetch(`${baseUrl}/requirements/${encodeURIComponent(ingestion.requirementId)}/analysis/reanalyze`, {
        method: 'POST', headers: { 'X-HEI-User': context.user.id },
      });
      const analyzed = await analysisResponse.json() as RequirementAnalysisResult & { error?: { message?: string } };
      if (!analysisResponse.ok) throw new Error(analyzed.error?.message || `Requirement Re-analysis returned HTTP ${analysisResponse.status}.`);
      setRequirementAnalysis(analyzed);
      setIngestion({ ...ingestion, contextVersion: analyzed.contextVersion || ingestion.contextVersion, contentHash: analyzed.contentHash || ingestion.contentHash });
      setReviewContent(analyzed.planningRequirement);
    } catch (error) {
      onError(error instanceof Error ? error.message : 'Unable to override the repository recommendation.');
    } finally {
      setBusyStage('');
    }
  }

  async function saveReviewEdit() {
    if (!ingestion || !reviewTitle.trim() || !reviewContent.trim()) return;
    setBusyStage('analyzing');
    try {
      const response = await fetch(`${baseUrl}/requirements/${encodeURIComponent(ingestion.requirementId)}/analysis/edit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-HEI-User': context.user.id },
        body: JSON.stringify({ title: reviewTitle, content: reviewContent, actor: context.user.name }),
      });
      const analyzed = await response.json() as RequirementAnalysisResult & { error?: { message?: string } };
      if (!response.ok) throw new Error(analyzed.error?.message || `Requirement Edit returned HTTP ${response.status}.`);
      setRequirementAnalysis(analyzed);
      setIngestion({ ...ingestion, title: reviewTitle, contextVersion: analyzed.contextVersion || ingestion.contextVersion, contentHash: analyzed.contentHash || ingestion.contentHash });
      setReviewContent(analyzed.planningRequirement);
      setEditingReview(false);
    } catch (error) {
      onError(error instanceof Error ? error.message : 'Unable to save the requirement edit.');
    } finally {
      setBusyStage('');
    }
  }

  async function cancelReview() {
    if (ingestion) {
      await fetch(`${baseUrl}/requirements/${encodeURIComponent(ingestion.requirementId)}/analysis/cancel`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-HEI-User': context.user.id }, body: JSON.stringify({ actor: context.user.name }),
      }).catch(() => undefined);
    }
    reset();
  }

  function reset() {
    setResult(undefined);
    setIngestion(undefined);
    setRequirementAnalysis(undefined);
    setEditingReview(false);
    setReviewTitle('');
    setReviewContent('');
    setTitle('');
    setContent('');
    setWorkItemId(context.route.workItemId || '');
    setDocumentName('');
    setDocumentMediaType('text/plain');
    setDocumentContentBase64('');
    setDocumentResult(undefined);
    setTranscriptResult(undefined);
    setAdoImportResult(undefined);
  }

  const requiresText = sourceType !== 'AzureDevOpsWorkItem';
  const canSubmit = Boolean(context.project.id || context.project.name)
    && (sourceType === 'AzureDevOpsWorkItem'
      ? Boolean(workItemId.trim())
      : sourceType === 'UploadDocument'
        ? Boolean(title.trim() && documentContentBase64)
        : sourceType === 'MeetingTranscript'
          ? Boolean(title.trim() && (content.trim() || documentContentBase64))
          : Boolean(title.trim() && content.trim()));

  return (
    <section className="hei-requirement-workspace" aria-label="New Requirement">
      <header>
        <div><span>Requirement Intelligence</span><h2>New Requirement</h2><p>Choose a source. HEI will create a normalized Requirement Context before Planning begins.</p></div>
        {result ? <Status value={result.status} /> : requirementAnalysis ? <Status value={`${requirementAnalysis.reviewStatus} Review`} /> : ingestion ? <Status value={ingestion.status} /> : null}
      </header>
      {result ? (
        <div className="hei-requirement-result" aria-live="polite">
          <div><span>Planning Pack</span><h3>{result.title}</h3><p>HEI ingested the source and prepared a context-grounded Planning Pack. No Azure DevOps work item has been changed.</p></div>
          <div className="hei-requirement-signals">
            <Signal label="Source" value={ingestion?.sourceType || sourceType} />
            <Signal label="Context" value={result.context.status || 'Needs Review'} />
            <Signal label="Confidence" value={`${Math.round(Number(result.context.confidence || 0) * 100)}%`} />
            <Signal label="Approval" value={result.approvalRequired ? 'Required' : 'Not required'} />
          </div>
          {documentResult ? <div className="hei-uploaded-document-summary"><Signal label="Uploaded File" value={documentResult.fileName} /><Signal label="Detected Type" value={documentResult.parsed?.detectedType || 'Unknown'} /><Signal label="Pages" value={String(documentResult.parsed?.pages || 0)} /><Signal label="Analysis" value={documentResult.readyForAnalysis ? 'Ready for Analysis' : documentResult.status} /></div> : null}
          {transcriptResult ? <TranscriptSummary result={transcriptResult} /> : null}
          {adoImportResult ? <AdoWorkItemSummary result={adoImportResult} /> : null}
          {requirementAnalysis ? <RequirementAnalysisSummary result={requirementAnalysis} /> : null}
          <details><summary>Context sources</summary><ul>{(result.context.sourceSummary || []).map((source, index) => <li key={`${source.source}-${index}`}><strong>{source.source}</strong> {source.available ? `${source.selected || 0} selected` : 'Unavailable'}</li>)}</ul></details>
          <div className="hei-requirement-actions"><button className="planner-button primary" type="button" onClick={onOpenApprovals}>Review Planning Pack</button><button className="planner-button secondary" type="button" onClick={reset}>Start Another</button></div>
          <small>Requirement Context {ingestion?.contextVersion || '1.0'} · Correlation: {result.correlationId}</small>
        </div>
      ) : requirementAnalysis && ingestion ? (
        <RequirementReviewScreen
          analysis={requirementAnalysis}
          ingestion={ingestion}
          editing={editingReview}
          title={reviewTitle}
          content={reviewContent}
          busy={Boolean(busyStage)}
          onTitleChange={setReviewTitle}
          onContentChange={setReviewContent}
          onEdit={() => setEditingReview(true)}
          onDiscardEdit={() => { setEditingReview(false); setReviewTitle(ingestion.title); setReviewContent(requirementAnalysis.planningRequirement); }}
          onSaveEdit={saveReviewEdit}
          onContinue={continueToPlanning}
          onCancel={cancelReview}
          onReanalyze={reanalyze}
          onOverrideRepository={overrideRepository}
        />
      ) : (
        <form className="hei-requirement-form" onSubmit={submit}>
          <fieldset className="hei-requirement-source-picker">
            <legend>Choose Source</legend>
            {SOURCES.map((source) => (
              <label key={source.id} className={sourceType === source.id ? 'selected' : ''}>
                <input type="radio" name="requirement-source" value={source.id} checked={sourceType === source.id} onChange={() => { setSourceType(source.id); setContent(''); setDocumentName(''); setDocumentMediaType('text/plain'); setDocumentContentBase64(''); setDocumentResult(undefined); setTranscriptResult(undefined); setAdoImportResult(undefined); }} />
                <span><strong>{source.label}</strong><small>{source.description}</small></span>
              </label>
            ))}
          </fieldset>

          <div className="hei-requirement-source-workflow">
            {sourceType === 'AzureDevOpsWorkItem' ? (
              <label><span>Work item ID</span><input inputMode="numeric" value={workItemId} onChange={(event) => setWorkItemId(event.target.value)} placeholder="245" required /></label>
            ) : (
              <label><span>{sourceType === 'MeetingTranscript' ? 'Meeting title' : 'Requirement title'}</span><input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="What engineering outcome is needed?" maxLength={180} required /></label>
            )}
            {sourceType === 'UploadDocument' ? (
              <label className="wide hei-document-upload"><span>Requirement document</span><input type="file" accept=".pdf,.docx,.txt,.md,.markdown,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain,text/markdown" onChange={readDocument} required={!documentContentBase64} /><small>{documentName ? `${documentName} ready to upload` : 'PDF, DOCX, TXT, and Markdown documents up to 25 MB.'}</small></label>
            ) : null}
            {sourceType === 'MeetingTranscript' ? (
              <>
                <label><span>Transcript source</span><select value={transcriptFormat} onChange={(event) => setTranscriptFormat(event.target.value as typeof transcriptFormat)}><option value="TeamsTranscript">Teams Transcript</option><option value="ZoomTranscript">Zoom Transcript</option><option value="TextTranscript">Text Transcript</option></select></label>
                <label className="wide hei-document-upload"><span>Transcript document (optional)</span><input type="file" accept=".docx,.txt,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain" onChange={readDocument} /><small>{documentName ? `${documentName} ready to analyze` : 'Upload DOCX or TXT, or paste the transcript below.'}</small></label>
              </>
            ) : null}
            {requiresText && sourceType !== 'UploadDocument' ? (
              <label className="wide"><span>{sourceType === 'MeetingTranscript' ? 'Transcript' : 'Requirement content'}</span><textarea value={content} onChange={(event) => setContent(event.target.value)} placeholder={sourceType === 'MeetingTranscript' ? 'Paste the meeting transcript. HEI will remove greetings, repetition, and conversational noise.' : 'Describe the business goal, users, expected outcome, constraints, and known acceptance criteria.'} rows={10} required={sourceType !== 'MeetingTranscript' || !documentContentBase64} /></label>
            ) : null}
          </div>

          {documentResult ? <div className="hei-uploaded-document-summary"><Signal label="Uploaded File" value={documentResult.fileName} /><Signal label="Detected Type" value={documentResult.parsed?.detectedType || 'Unknown'} /><Signal label="Pages" value={String(documentResult.parsed?.pages || 0)} /><Signal label="Analysis" value={documentResult.readyForAnalysis ? 'Ready for Analysis' : documentResult.status} /></div> : null}
          {transcriptResult ? <TranscriptSummary result={transcriptResult} /> : null}
          {adoImportResult ? <AdoWorkItemSummary result={adoImportResult} /> : null}
          <div className="hei-intake-context"><strong>Planning context</strong><span>{context.project.name || 'Project required'}</span><span>{context.team.name || 'Team unavailable'}</span><span>{context.repository.name || 'Repository will be resolved by HEI'}</span></div>
          <details className="hei-future-sources"><summary>Future sources</summary><div>{FUTURE_SOURCES.map((source) => <span key={source}>{source} · Coming later</span>)}</div></details>
          <button className="planner-button primary" type="submit" disabled={Boolean(busyStage) || !canSubmit}>{busyStage === 'uploading' ? `Uploading ${sourceType === 'MeetingTranscript' ? 'Transcript' : 'Document'}...` : busyStage === 'parsing' ? 'Parsing Document...' : busyStage === 'analyzing' ? 'Analyzing Requirement...' : busyStage === 'ingesting' ? 'Ingesting Requirement...' : busyStage === 'planning' ? 'Preparing Planning Pack...' : 'Ingest & Analyze'}</button>
        </form>
      )}
    </section>
  );
}

function Signal({ label, value }: { label: string; value: string }) { return <div><span>{label}</span><strong>{value}</strong></div>; }
function Status({ value }: { value: string }) { return <span className="hei-operation-chip warning">{value}</span>; }

function TranscriptSummary({ result }: { result: TranscriptResult }) {
  const analysis = result.analysis;
  return <section className="hei-transcript-summary" aria-label="Meeting transcript analysis">
    <header><div><span>Meeting Summary</span><h3>{analysis.meetingTitle}</h3><p>{analysis.meetingSummary}</p></div><Status value={result.readyForPlanning ? 'Ready for Planning' : 'Needs Review'} /></header>
    <div className="hei-requirement-signals"><Signal label="Requirements Found" value={String(analysis.requirements.length)} /><Signal label="Action Items" value={String(analysis.actionItems.length)} /><Signal label="Decisions" value={String(analysis.decisions.length)} /><Signal label="Participants" value={String(analysis.participants.length)} /></div>
    <details open><summary>Requirements Found</summary><FindingList items={analysis.requirements} empty="No explicit requirements found." /></details>
    <details><summary>Action Items</summary><FindingList items={analysis.actionItems} empty="No action items found." /></details>
    <details><summary>Decisions</summary><FindingList items={analysis.decisions} empty="No business decisions found." /></details>
  </section>;
}

function FindingList({ items, empty }: { items: TranscriptFinding[]; empty: string }) {
  return items.length ? <ul>{items.map((item) => <li key={item.findingId}>{item.text}{item.speaker ? <small> {item.speaker}{item.timestamp ? ` · ${item.timestamp}` : ''}</small> : null}</li>)}</ul> : <p>{empty}</p>;
}

function AdoWorkItemSummary({ result }: { result: AdoWorkItemImportResult }) {
  const item = result.currentWorkItem;
  const summary = result.requirementSummary;
  return <section className="hei-transcript-summary" aria-label="Azure DevOps work item requirement summary">
    <header><div><span>Current Work Item</span><h3>{item.workItemType} #{result.workItemId} · {item.title}</h3><p>{summary.summary}</p></div><Status value={summary.readyForPlanning ? 'Ready for Planning' : 'Needs Review'} /></header>
    <div className="hei-requirement-signals"><Signal label="Acceptance Criteria" value={String(summary.acceptanceCriteria.length)} /><Signal label="Dependencies" value={String(summary.dependencies.length)} /><Signal label="Missing Information" value={String(summary.missingInformation.length)} /><Signal label="Revision" value={String(result.workItemRevision)} /></div>
    <details open><summary>Acceptance Criteria</summary>{summary.acceptanceCriteria.length ? <ul>{summary.acceptanceCriteria.map((criterion, index) => <li key={`${index}-${criterion}`}>{criterion}</li>)}</ul> : <p>No acceptance criteria captured.</p>}</details>
    <details><summary>Dependencies</summary>{summary.dependencies.length ? <ul>{summary.dependencies.map((dependency) => <li key={`${dependency.workItemId}-${dependency.relationship}`}>Work item #{dependency.workItemId} · {dependency.relationship}</li>)}</ul> : <p>No dependency links identified.</p>}</details>
    <details open={!summary.readyForPlanning}><summary>Missing Information</summary>{summary.missingInformation.length ? <ul>{summary.missingInformation.map((value) => <li key={value}>{value}</li>)}</ul> : <p>No blocking information gaps.</p>}</details>
  </section>;
}

function RequirementReviewScreen({ analysis, ingestion, editing, title, content, busy, onTitleChange, onContentChange, onEdit, onDiscardEdit, onSaveEdit, onContinue, onCancel, onReanalyze, onOverrideRepository }: {
  analysis: RequirementAnalysisResult;
  ingestion: IngestionResult;
  editing: boolean;
  title: string;
  content: string;
  busy: boolean;
  onTitleChange: (value: string) => void;
  onContentChange: (value: string) => void;
  onEdit: () => void;
  onDiscardEdit: () => void;
  onSaveEdit: () => void;
  onContinue: () => void;
  onCancel: () => void;
  onReanalyze: () => void;
  onOverrideRepository: (repositoryId: string) => void;
}) {
  const review = analysis.reviewContext;
  const blocked = analysis.planningReadiness.status === 'Blocked';
  const suggestion = analysis.repositorySuggestion;
  const recommendedRepository = suggestion?.suggestedRepository;
  const repositoryOptions = suggestion?.availableRepositories || [];
  const [overrideRepositoryId, setOverrideRepositoryId] = useState(recommendedRepository?.repositoryId || '');
  return <section className="hei-requirement-review" aria-label="Requirement Summary" aria-live="polite">
    <header><div><span>Mandatory Review</span><h2>Requirement Summary</h2><p>Validate HEI's understanding before Planning begins. No Planning Pack has been created.</p></div><Status value={analysis.planningReadiness.status === 'NeedsReview' ? 'Needs Review' : analysis.planningReadiness.status} /></header>
    {editing ? <div className="hei-requirement-review-editor">
      <label><span>Requirement title</span><input value={title} onChange={(event) => onTitleChange(event.target.value)} maxLength={180} /></label>
      <label><span>Analyzed requirement</span><textarea value={content} onChange={(event) => onContentChange(event.target.value)} rows={18} /></label>
      <div className="hei-requirement-actions"><button className="planner-button primary" type="button" disabled={busy || !title.trim() || !content.trim()} onClick={onSaveEdit}>Save & Re-analyze</button><button className="planner-button secondary" type="button" disabled={busy} onClick={onDiscardEdit}>Discard Edit</button></div>
    </div> : <>
      <div className="hei-requirement-review-meta">
        <Signal label="Source" value={review.source || ingestion.sourceType} />
        <Signal label="Repository" value={review.repository.name || review.repository.id || review.repository.status} />
        <Signal label="Document Type" value={review.documentType || 'Not Applicable'} />
        <Signal label="Confidence" value={`${Math.round(analysis.confidence * 100)}%`} />
      </div>
      <section className="hei-repository-recommendation" aria-label="Suggested Repository">
        <header>
          <div><span>Suggested Repository</span><h3>{recommendedRepository?.name || 'No repository detected'}</h3><p>{suggestion?.reason || 'Register a repository to enable engineering workspace detection.'}</p></div>
          <Status value={recommendedRepository ? `${Math.round((suggestion?.confidence || 0) * 100)}% confidence` : 'Not Available'} />
        </header>
        {recommendedRepository ? <>
          <div className="hei-repository-recommendation-evidence">
            <Signal label="Repository" value={recommendedRepository.name} />
            <Signal label="Branch" value={recommendedRepository.defaultBranch || 'Not configured'} />
            <Signal label="Snapshot" value={recommendedRepository.snapshotVersion || 'Unavailable'} />
            <Signal label="Selection" value={suggestion?.source === 'ManualOverride' ? 'Manual Override' : 'HEI Recommendation'} />
          </div>
          <details><summary>Engineering reason</summary><ul>{recommendedRepository.evidence.map((item) => <li key={item}>{item}</li>)}</ul></details>
          {repositoryOptions.length > 1 ? <div className="hei-repository-override">
            <label><span>Override repository</span><select value={overrideRepositoryId} disabled={busy} onChange={(event) => setOverrideRepositoryId(event.target.value)}>{repositoryOptions.map((repository) => <option key={repository.repositoryId} value={repository.repositoryId}>{repository.name} · {Math.round(repository.confidence * 100)}%</option>)}</select></label>
            <button className="planner-button secondary" type="button" disabled={busy || !overrideRepositoryId || overrideRepositoryId === recommendedRepository.repositoryId} onClick={() => onOverrideRepository(overrideRepositoryId)}>Apply Override</button>
          </div> : null}
          {suggestion?.alternativeRepositories.length ? <small>Alternatives: {suggestion.alternativeRepositories.map((repository) => `${repository.name} (${Math.round(repository.confidence * 100)}%)`).join(', ')}</small> : null}
        </> : null}
      </section>
      <div className="hei-requirement-review-grid">
        <RequirementList title="Business Goals" items={analysis.businessGoals} empty="No explicit business goals identified." />
        <RequirementList title="Functional Requirements" items={analysis.functionalRequirements} empty="No functional requirements identified." />
        <RequirementList title="Non Functional Requirements" items={analysis.nonFunctionalRequirements} empty="No non-functional requirements identified." />
        <RequirementList title="Acceptance Criteria" items={analysis.acceptanceCriteria} empty="Acceptance criteria require definition." />
        <RequirementList title="Dependencies" items={analysis.dependencies} empty="No dependencies identified." />
        <RequirementList title="Risks" items={analysis.risks} empty="No explicit risks identified." />
      </div>
      <div className="hei-requirement-review-context">
        <div><span>Engineering Memory</span><strong>{review.engineeringMemory.status}</strong><p>{review.engineeringMemory.message}</p></div>
        <div><span>Repository Reuse</span><strong>{review.repositoryReuse.status}</strong><p>{review.repositoryReuse.message}</p></div>
        <div><span>Planning Readiness</span><strong>{analysis.planningReadiness.status} · {analysis.requirementQualityScore}% quality</strong><p>{[...analysis.planningReadiness.blockers, ...analysis.planningReadiness.warnings].join(' ') || 'Requirement is ready for Planning approval.'}</p></div>
      </div>
      <RequirementAnalysisSummary result={analysis} />
      <div className="hei-requirement-actions">
        <button className="planner-button primary" type="button" disabled={busy || blocked} onClick={onContinue}>{busy ? 'Preparing Planning...' : 'Continue to Planning'}</button>
        <button className="planner-button secondary" type="button" disabled={busy} onClick={onEdit}>Edit</button>
        <button className="planner-button secondary" type="button" disabled={busy} onClick={onReanalyze}>Re-analyze</button>
        <button className="planner-button secondary" type="button" disabled={busy} onClick={onCancel}>Cancel</button>
      </div>
      {blocked ? <p className="hei-requirement-review-blocker">Resolve blocking findings with Edit before continuing to Planning.</p> : null}
      <small>Requirement Context {analysis.contextVersion} · Review {analysis.reviewStatus}</small>
    </>}
  </section>;
}

function RequirementList({ title, items, empty }: { title: string; items: string[]; empty: string }) {
  return <section><h3>{title}</h3>{items.length ? <ul>{items.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul> : <p>{empty}</p>}</section>;
}

function RequirementAnalysisSummary({ result }: { result: RequirementAnalysisResult }) {
  const readiness = result.planningReadiness;
  const issues = [
    ...result.missingAcceptanceCriteria,
    ...result.ambiguousRequirements,
    ...result.conflictingRequirements,
    ...result.duplicateRequirements,
  ];
  return <section className="hei-transcript-summary hei-requirement-analysis" aria-label="Requirement analysis">
    <header><div><span>Requirement Analysis</span><h3>{result.requirementSummary}</h3><p>Planning will receive the analyzed engineering requirement, not the raw source.</p></div><Status value={readiness.status === 'NeedsReview' ? 'Needs Review' : readiness.status} /></header>
    <div className="hei-requirement-signals"><Signal label="Quality" value={`${result.requirementQualityScore}%`} /><Signal label="Confidence" value={`${Math.round(result.confidence * 100)}%`} /><Signal label="Functional" value={String(result.functionalRequirements.length)} /><Signal label="Acceptance" value={String(result.acceptanceCriteria.length)} /></div>
    <details open={issues.length > 0}><summary>Planning Readiness</summary>
      {readiness.blockers.length || readiness.warnings.length ? <ul>{[...readiness.blockers, ...readiness.warnings].map((value) => <li key={value}>{value}</li>)}</ul> : <p>Requirement is ready for Planning.</p>}
    </details>
    <details open={issues.length > 0}><summary>Quality Findings ({issues.length})</summary>
      {issues.length ? <ul>{issues.map((finding, index) => <li key={`${index}-${finding.text}`}><strong>{finding.text}</strong><small> {finding.reason}</small></li>)}</ul> : <p>No ambiguity, conflict, duplicate, or acceptance gaps detected.</p>}
    </details>
    <details><summary>Extracted Engineering Context</summary><div className="hei-requirement-analysis-grid"><Signal label="Business Goals" value={String(result.businessGoals.length)} /><Signal label="Actors" value={String(result.actors.length)} /><Signal label="Dependencies" value={String(result.dependencies.length)} /><Signal label="Risks" value={String(result.risks.length)} /></div></details>
  </section>;
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error('The selected document could not be read.'));
    reader.onload = () => resolve(String(reader.result || '').split(',', 2)[1] || '');
    reader.readAsDataURL(file);
  });
}
