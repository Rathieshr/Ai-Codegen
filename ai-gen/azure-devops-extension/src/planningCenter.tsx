import React, { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import './styles.css';
import {
  PlanningActions, PlanningContent, PlanningHeader, PlanningTab, PlanningTabs, PlanningWorkspace,
} from './planningWorkspace';
import { PlanningOverview, PlanningOverviewData } from './planningOverview';
import { PlanningHierarchy } from './planningHierarchy';
import { DependencyView, PlanningDependencies, PlanningDependenciesData } from './planningDependencies';
import { PlanningDiff, PlanningDiffData } from './planningDiff';

export type PlanningCenterItem = {
  id: string;
  type: 'Requirement' | 'Epic' | 'Feature' | 'Story' | 'Task' | 'Recommendation' | string;
  title: string;
  description: string;
  parentId: string;
  depth: number;
  childCount: number;
  status: string;
  approvalStatus: string;
  storyPoints: number;
  dependencies: string[];
  readiness: string;
  risks: string[];
  riskLevel: string;
  confidence: number;
  recommendationCount: number;
  source: string;
  sourceItemId: string;
  projectId: string;
  updatedAt: string;
  version: number;
  canApprove: boolean;
  canReject: boolean;
  canRequestChanges: boolean;
  canPublish: boolean;
  canRollback: boolean;
  approver: string;
  approvalComments: string;
  approvedAt: string;
  lifecycleState: string;
  azureDevOpsSyncReady: boolean;
  canGenerateExecutionPackage: boolean;
  details?: Record<string, unknown>;
};

type PlanningCenterResponse = {
  schemaVersion: string;
  summary: Record<string, number>;
  items: PlanningCenterItem[];
  recommendations: Array<Record<string, unknown>>;
  filters: { types: string[]; statuses: string[]; readiness: string[] };
  pagination: { total: number; offset: number; limit: number; returned: number; hasMore: boolean };
};

type PlanningHierarchyResponse = {
  schemaVersion: string;
  planningId: string;
  root: PlanningCenterItem;
  nodes: PlanningCenterItem[];
  editable: boolean;
};

type EngineeringEstimation = {
  estimateId: string; artifactId: string; artifactType: string; version: number; status: string; overrideReason?: string;
  aiEstimate?: EstimateValues;
  originalEstimate?: EstimateValues;
  userEstimate?: EstimateValues & { overriddenBy?: string; overriddenAt?: string };
  isOverridden?: boolean;
  override?: { reason: string; revision: number; history: Array<{ revision: number; reason: string; actor: string; createdAt: string }> };
  effectiveEstimate: {
    engineeringHours: number; engineeringDays: number; storyPoints: number; confidence: number; risk: string; complexity: string;
    suggestedTeamSize?: number; developersNeeded?: number;
    estimatedSprintCount: number; estimatedTestCases: number; estimatedPullRequests: number; repositoryReuse: number;
    topEstimationDrivers: string[]; warnings: string[]; taskEstimates: Array<{ taskId: string; taskName: string; estimatedDuration: string; storyPointContribution: number; complexity: string; confidence: number }>;
    report: { features: number; stories: number; tasks: number; engineeringDays: number; storyPoints: number; estimatedSprintCount: number; averageStorySize: number; confidence: number; risk: string; repositoryReuse: number; estimatedTestCases: number; estimatedPullRequests: number; highRiskStories: number; suggestedTeamSize: number };
  };
};

type EstimateValues = {
  engineeringHours?: number; engineeringDays?: number; storyPoints?: number; estimatedSprintCount?: number;
  suggestedTeamSize?: number; developersNeeded?: number; confidence?: number; risk?: string; complexity?: string;
};

type PlanningApprovalHistory = {
  schemaVersion: string; planningId: string; currentState: string; currentVersion: number; count: number;
  history: Array<{ version: number; status: string; action: string; actor: string; comments: string; timestamp: string; title: string; isCurrent: boolean; canRollback: boolean }>;
};

type Props = {
  baseUrl: string;
  projectId: string;
  actor: string;
  currentWorkItemId?: string;
  canContribute: boolean;
  onGenerateExecutionPackage: () => void;
  onError: (message: string) => void;
};

type PlanningTreeNode = PlanningCenterItem & { children: PlanningTreeNode[] };
const HIERARCHY_TYPES = new Set(['Requirement', 'Epic', 'Feature', 'Story', 'Task']);
const TYPE_ORDER: Record<string, number> = { Requirement: 0, Epic: 1, Feature: 2, Story: 3, Task: 4 };

export function PlanningCenter({
  baseUrl, projectId, actor, currentWorkItemId, canContribute, onGenerateExecutionPackage, onError,
}: Props) {
  const [data, setData] = useState<PlanningCenterResponse>();
  const [selectedId, setSelectedId] = useState('');
  const [search, setSearch] = useState('');
  const [type, setType] = useState('');
  const [status, setStatus] = useState('');
  const [readiness, setReadiness] = useState('');
  const [loading, setLoading] = useState(false);
  const [actionId, setActionId] = useState('');
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [checkedIds, setCheckedIds] = useState<Set<string>>(new Set());
  const [estimates, setEstimates] = useState<Record<string, EngineeringEstimation>>({});
  const [estimationBusy, setEstimationBusy] = useState('');
  const [overrideOpen, setOverrideOpen] = useState(false);
  const [overrideHours, setOverrideHours] = useState('');
  const [overrideDays, setOverrideDays] = useState('');
  const [overridePoints, setOverridePoints] = useState('');
  const [overrideSprints, setOverrideSprints] = useState('');
  const [overrideDevelopers, setOverrideDevelopers] = useState('');
  const [overrideConfidence, setOverrideConfidence] = useState('');
  const [overrideRisk, setOverrideRisk] = useState('Medium');
  const [overrideComplexity, setOverrideComplexity] = useState('Medium');
  const [overrideReason, setOverrideReason] = useState('');
  const [activeTab, setActiveTab] = useState<PlanningTab>('Overview');
  const [draftTitle, setDraftTitle] = useState('');
  const [draftDescription, setDraftDescription] = useState('');
  const [overviewData, setOverviewData] = useState<PlanningOverviewData>();
  const [overviewLoading, setOverviewLoading] = useState(false);
  const [overviewError, setOverviewError] = useState('');
  const [hierarchyData, setHierarchyData] = useState<PlanningHierarchyResponse>();
  const [hierarchyLoading, setHierarchyLoading] = useState(false);
  const [hierarchyError, setHierarchyError] = useState('');
  const [dependencyData, setDependencyData] = useState<PlanningDependenciesData>();
  const [dependencyLoading, setDependencyLoading] = useState(false);
  const [dependencyError, setDependencyError] = useState('');
  const [dependencyBusy, setDependencyBusy] = useState(false);
  const [dependencyView, setDependencyView] = useState<DependencyView>('Tree');
  const [approvalComments, setApprovalComments] = useState('');
  const [approvalHistory, setApprovalHistory] = useState<PlanningApprovalHistory>();
  const [approvalHistoryLoading, setApprovalHistoryLoading] = useState(false);
  const [planningDiff, setPlanningDiff] = useState<PlanningDiffData>();
  const [planningDiffLoading, setPlanningDiffLoading] = useState(false);
  const [planningDiffError, setPlanningDiffError] = useState('');
  const [planningDiffBusy, setPlanningDiffBusy] = useState(false);
  const overviewRequest = useRef(0);
  const hierarchyRequest = useRef(0);
  const dependencyRequest = useRef(0);

  useEffect(() => { void load(true); }, [projectId]);
  useEffect(() => {
    if (!currentWorkItemId || !data?.items.length) return;
    const match = data.items.find((item) => [item.id, item.sourceItemId].includes(currentWorkItemId));
    if (match) setSelectedId(match.id);
  }, [currentWorkItemId, data?.items]);

  const selected = useMemo(
    () => data?.items.find((item) => item.id === selectedId) || data?.items.find((item) => HIERARCHY_TYPES.has(item.type)) || data?.items[0],
    [data, selectedId],
  );
  const hierarchyItems = useMemo(() => (data?.items || []).filter((item) => HIERARCHY_TYPES.has(item.type)), [data]);
  const tree = useMemo(() => buildTree(hierarchyItems), [hierarchyItems]);
  const visibleNodes = useMemo(() => flattenVisible(tree, expandedIds), [tree, expandedIds]);
  const breadcrumbs = useMemo(() => selected ? buildBreadcrumbs(selected, hierarchyItems) : [], [selected, hierarchyItems]);
  const hierarchyRoot = breadcrumbs[0] || selected;
  const selectedForReview = useMemo(() => hierarchyItems.filter((item) => checkedIds.has(item.id)), [checkedIds, hierarchyItems]);
  const selectedEstimate = selected ? estimates[selected.id] : undefined;
  const packEstimate = hierarchyRoot ? estimates[hierarchyRoot.id] : undefined;

  useEffect(() => {
    setDraftTitle(selected?.title || '');
    setDraftDescription(selected?.description || '');
  }, [selected?.id, selected?.version]);
  useEffect(() => {
    if (!selected || selected.type === 'Recommendation') return;
    void loadOverview(selected.id);
  }, [selected?.id, selected?.version, projectId]);
  useEffect(() => {
    if (activeTab !== 'Hierarchy' || !hierarchyRoot || hierarchyRoot.type === 'Recommendation') return;
    void loadHierarchy(hierarchyRoot.id);
  }, [activeTab, hierarchyRoot?.id, data?.items]);
  useEffect(() => {
    if (activeTab !== 'Dependencies' || !hierarchyRoot || hierarchyRoot.type === 'Recommendation') return;
    void loadDependencies(hierarchyRoot.id);
  }, [activeTab, hierarchyRoot?.id, data?.items]);
  useEffect(() => {
    if (activeTab !== 'Estimate' || !hierarchyRoot || hierarchyRoot.type === 'Recommendation') return;
    void loadPackEstimate(hierarchyRoot.id);
  }, [activeTab, hierarchyRoot?.id, data?.items]);
  useEffect(() => {
    if (activeTab !== 'Approval' || !selected || selected.source !== 'planning_artifact') return;
    setApprovalComments('');
    void loadApprovalHistory(selected.id);
  }, [activeTab, selected?.id, selected?.version]);
  useEffect(() => {
    if (activeTab !== 'Diff' || !hierarchyRoot || hierarchyRoot.source !== 'planning_artifact') return;
    void loadPlanningDiff(hierarchyRoot.id);
  }, [activeTab, hierarchyRoot?.id, hierarchyRoot?.version]);

  useEffect(() => {
    if (!hierarchyItems.length) return;
    setExpandedIds((current) => {
      if (current.size) return current;
      return new Set(tree.map((item) => item.id));
    });
  }, [hierarchyItems, tree]);
  useEffect(() => {
    if (breadcrumbs.length < 2) return;
    setExpandedIds((current) => new Set([...current, ...breadcrumbs.slice(0, -1).map((item) => item.id)]));
  }, [breadcrumbs]);
  useEffect(() => {
    if (!selected || selected.type === 'Requirement' || selected.type === 'Recommendation' || estimates[selected.id] || estimationBusy === selected.id) return;
    void estimate(selected);
  }, [selected?.id, data?.items]);

  async function load(reset = true) {
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: '250' });
      if (projectId) params.set('projectId', projectId);
      if (search.trim()) params.set('search', search.trim());
      if (type) params.set('type', type);
      if (status) params.set('status', status);
      if (readiness) params.set('readiness', readiness);
      const response = await fetch(`${baseUrl}/planning?${params.toString()}`);
      const payload = await response.json() as PlanningCenterResponse & { error?: { message?: string } };
      if (!response.ok) throw new Error(payload.error?.message || `Planning Center returned HTTP ${response.status}`);
      setData(payload);
      if (reset) setCheckedIds(new Set());
      if (reset && payload.items.length && !payload.items.some((item) => item.id === selectedId)) {
        setSelectedId(payload.items.find((item) => HIERARCHY_TYPES.has(item.type))?.id || payload.items[0].id);
      }
    } catch (error) {
      onError(error instanceof Error ? error.message : 'Unable to load Planning Center.');
    } finally {
      setLoading(false);
    }
  }

  async function loadOverview(planningId: string) {
    const requestId = ++overviewRequest.current;
    setOverviewLoading(true);
    setOverviewError('');
    setOverviewData(undefined);
    try {
      const params = new URLSearchParams();
      if (projectId) params.set('projectId', projectId);
      const query = params.toString();
      const response = await fetch(`${baseUrl}/planning/${encodeURIComponent(planningId)}/overview${query ? `?${query}` : ''}`);
      const payload = await response.json() as PlanningOverviewData & { error?: { message?: string } };
      if (!response.ok) throw new Error(payload.error?.message || 'Unable to load the Planning Overview.');
      if (requestId !== overviewRequest.current) return;
      setOverviewData(payload);
      if (payload.engineeringEstimate && typeof payload.engineeringEstimate === 'object') {
        setEstimates((current) => ({ ...current, [planningId]: payload.engineeringEstimate as unknown as EngineeringEstimation }));
      }
    } catch (error) {
      if (requestId !== overviewRequest.current) return;
      setOverviewData(undefined);
      setOverviewError(error instanceof Error ? error.message : 'Unable to load the Planning Overview.');
    } finally {
      if (requestId === overviewRequest.current) setOverviewLoading(false);
    }
  }

  async function loadHierarchy(planningId: string) {
    const requestId = ++hierarchyRequest.current;
    setHierarchyLoading(true); setHierarchyError('');
    try {
      const params = new URLSearchParams();
      if (projectId) params.set('projectId', projectId);
      const query = params.toString();
      const response = await fetch(`${baseUrl}/planning/${encodeURIComponent(planningId)}/hierarchy${query ? `?${query}` : ''}`);
      const payload = await response.json() as PlanningHierarchyResponse & { error?: { message?: string } };
      if (!response.ok) throw new Error(payload.error?.message || 'Unable to load the Planning Hierarchy.');
      if (requestId === hierarchyRequest.current) setHierarchyData(payload);
    } catch (error) {
      if (requestId !== hierarchyRequest.current) return;
      setHierarchyData(undefined); setHierarchyError(error instanceof Error ? error.message : 'Unable to load the Planning Hierarchy.');
    } finally {
      if (requestId === hierarchyRequest.current) setHierarchyLoading(false);
    }
  }

  async function loadDependencies(planningId: string) {
    const requestId = ++dependencyRequest.current;
    setDependencyLoading(true); setDependencyError('');
    try {
      const params = new URLSearchParams();
      if (projectId) params.set('projectId', projectId);
      const query = params.toString();
      const response = await fetch(`${baseUrl}/planning/${encodeURIComponent(planningId)}/dependencies${query ? `?${query}` : ''}`);
      const payload = await response.json() as PlanningDependenciesData & { error?: { message?: string } };
      if (!response.ok) throw new Error(payload.error?.message || 'Unable to load Planning dependencies.');
      if (requestId === dependencyRequest.current) setDependencyData(payload);
    } catch (error) {
      if (requestId !== dependencyRequest.current) return;
      setDependencyData(undefined); setDependencyError(error instanceof Error ? error.message : 'Unable to load Planning dependencies.');
    } finally {
      if (requestId === dependencyRequest.current) setDependencyLoading(false);
    }
  }

  async function loadPackEstimate(planningId: string): Promise<EngineeringEstimation | undefined> {
    setEstimationBusy(planningId);
    try {
      const params = new URLSearchParams();
      if (projectId) params.set('projectId', projectId);
      const query = params.toString();
      const response = await fetch(`${baseUrl}/planning/${encodeURIComponent(planningId)}/estimate${query ? `?${query}` : ''}`);
      const result = await response.json() as EngineeringEstimation & { error?: { message?: string } };
      if (!response.ok) throw new Error(result.error?.message || 'Unable to load the Planning Pack estimate.');
      setEstimates((current) => ({ ...current, [planningId]: result }));
      populateOverride(result);
      return result;
    } catch (error) {
      onError(error instanceof Error ? error.message : 'Unable to load the Planning Pack estimate.');
      return undefined;
    } finally { setEstimationBusy(''); }
  }

  async function loadApprovalHistory(planningId: string) {
    setApprovalHistoryLoading(true);
    try {
      const response = await fetch(`${baseUrl}/planning/${encodeURIComponent(planningId)}/history`);
      const result = await response.json() as PlanningApprovalHistory & { error?: { message?: string } };
      if (!response.ok) throw new Error(result.error?.message || 'Unable to load Planning approval history.');
      setApprovalHistory(result);
    } catch (error) {
      setApprovalHistory(undefined);
      onError(error instanceof Error ? error.message : 'Unable to load Planning approval history.');
    } finally { setApprovalHistoryLoading(false); }
  }

  async function loadPlanningDiff(planningId: string) {
    setPlanningDiffLoading(true); setPlanningDiffError('');
    try {
      const response = await fetch(`${baseUrl}/planning/${encodeURIComponent(planningId)}/diff`);
      const payload = await response.json() as PlanningDiffData & { error?: { message?: string } };
      if (!response.ok) throw new Error(payload.error?.message || 'Unable to load the Planning Diff.');
      setPlanningDiff(payload);
    } catch (error) {
      setPlanningDiff(undefined);
      setPlanningDiffError(error instanceof Error ? error.message : 'Unable to load the Planning Diff.');
    } finally { setPlanningDiffLoading(false); }
  }

  async function approvePlanningDiff() {
    if (!hierarchyRoot) return;
    setPlanningDiffBusy(true);
    try {
      const response = await fetch(`${baseUrl}/planning/${encodeURIComponent(hierarchyRoot.id)}/diff/approve`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ actor, comments: approvalComments }),
      });
      const payload = await response.json() as PlanningDiffData & { error?: { message?: string } };
      if (!response.ok) throw new Error(payload.error?.message || 'Unable to approve the Planning Diff.');
      setPlanningDiff(payload);
    } catch (error) { onError(error instanceof Error ? error.message : 'Unable to approve the Planning Diff.'); }
    finally { setPlanningDiffBusy(false); }
  }

  async function saveDependency(request: Record<string, unknown>) {
    if (!hierarchyRoot) return;
    setDependencyBusy(true);
    try {
      const response = await fetch(`${baseUrl}/dependency?actor=${encodeURIComponent(actor)}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...request, planningId: hierarchyRoot.id }),
      });
      const payload = await response.json() as { error?: { message?: string } };
      if (!response.ok) throw new Error(payload.error?.message || 'Unable to save the dependency.');
      await Promise.all([loadDependencies(hierarchyRoot.id), load(false)]);
    } catch (error) {
      onError(error instanceof Error ? error.message : 'Unable to save the dependency.');
      throw error;
    } finally { setDependencyBusy(false); }
  }

  async function deleteDependency(dependencyId: string) {
    if (!hierarchyRoot) return;
    setDependencyBusy(true);
    try {
      const response = await fetch(`${baseUrl}/dependency?actor=${encodeURIComponent(actor)}`, {
        method: 'DELETE', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ dependencyId }),
      });
      const payload = await response.json() as { error?: { message?: string } };
      if (!response.ok) throw new Error(payload.error?.message || 'Unable to delete the dependency.');
      await Promise.all([loadDependencies(hierarchyRoot.id), load(false)]);
    } catch (error) { onError(error instanceof Error ? error.message : 'Unable to delete the dependency.'); }
    finally { setDependencyBusy(false); }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void load(true);
  }

  async function decide(item: PlanningCenterItem, decision: 'approve' | 'reject') {
    setActionId(item.id);
    try {
      await submitDecision(item, decision, undefined, approvalComments);
      await load(false);
      if (activeTab === 'Approval') await loadApprovalHistory(item.id);
      setApprovalComments('');
    } catch (error) {
      onError(error instanceof Error ? error.message : `Unable to ${decision} planning item.`);
    } finally {
      setActionId('');
    }
  }

  async function decideSelected(decision: 'approve' | 'reject') {
    const actionable = selectedForReview.filter((item) => decision === 'approve' ? item.canApprove : item.canReject);
    if (!actionable.length) {
      onError(`No selected items can be ${decision === 'approve' ? 'approved' : 'rejected'}.`);
      return;
    }
    setActionId('bulk');
    try {
      for (const item of actionable) {
        const itemEstimate = decision === 'approve' ? estimates[item.id] || await estimate(item) : undefined;
        if (decision === 'approve' && !itemEstimate) throw new Error(`Generate the Engineering Estimation Report before approving ${item.title}.`);
        await submitDecision(item, decision, itemEstimate);
      }
      setCheckedIds(new Set());
      await load(false);
    } catch (error) {
      onError(error instanceof Error ? error.message : `Unable to ${decision} selected planning items.`);
    } finally {
      setActionId('');
    }
  }

  async function submitDecision(item: PlanningCenterItem, decision: 'approve' | 'reject', suppliedEstimate?: EngineeringEstimation, comments = '') {
    const estimateValue = suppliedEstimate || estimates[item.id];
    if (decision === 'approve' && estimateValue && estimateValue.status !== 'Approved') {
      const estimateResponse = await fetch(`${baseUrl}/planning/estimate/${encodeURIComponent(estimateValue.estimateId)}/approve?actor=${encodeURIComponent(actor)}`, { method: 'POST' });
      if (!estimateResponse.ok) throw new Error('The Engineering Estimation Report could not be approved with this planning item.');
    }
    const response = await fetch(`${baseUrl}/planning/${encodeURIComponent(item.id)}/${decision}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ actor, comments, expectedVersion: item.version }),
    });
    const payload = await response.json() as { error?: { message?: string } };
    if (!response.ok) throw new Error(payload.error?.message || `Unable to ${decision} ${item.type} '${item.title}'.`);
  }

  async function transitionPlanning(action: 'request-changes' | 'publish' | 'rollback', targetVersion?: number) {
    if (!selected) return;
    if (action === 'request-changes' && !approvalComments.trim()) {
      onError('Explain the requested changes before returning this Planning Pack.');
      return;
    }
    setActionId(selected.id);
    try {
      const response = await fetch(`${baseUrl}/planning/${encodeURIComponent(selected.id)}/${action}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ actor, comments: approvalComments, expectedVersion: selected.version, ...(targetVersion ? { targetVersion } : {}) }),
      });
      const payload = await response.json() as { error?: { message?: string } };
      if (!response.ok) throw new Error(payload.error?.message || `Unable to ${action.replace('-', ' ')} this Planning Pack.`);
      await load(false);
      await loadApprovalHistory(selected.id);
      setApprovalComments('');
    } catch (error) { onError(error instanceof Error ? error.message : 'Unable to update Planning approval.'); }
    finally { setActionId(''); }
  }

  async function estimate(item: PlanningCenterItem, recalculate = false): Promise<EngineeringEstimation | undefined> {
    setEstimationBusy(item.id);
    try {
      const children = descendantsOf(item.id, hierarchyItems);
      const details = item.details || {};
      const repositoryContext = firstObject(details.repositoryContext, details.repository, details.repositoryIntelligence);
      const payload = {
        ...(recalculate && estimates[item.id] ? { estimateId: estimates[item.id].estimateId } : {}),
        artifact: item, children,
        repositoryContext,
        engineeringMemory: firstObject(details.memoryContext, details.engineeringMemory),
        acceptanceCriteria: arrayValue(details.acceptanceCriteria || details.acceptance_criteria),
        dependencyAnalysis: item.dependencies,
        riskAnalysis: item.risks,
      };
      const response = await fetch(`${baseUrl}/planning/estimate${recalculate ? '/recalculate' : ''}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      const result = await response.json() as EngineeringEstimation & { error?: { message?: string } };
      if (!response.ok) throw new Error(result.error?.message || 'Unable to generate the Engineering Estimation Report.');
      setEstimates((current) => ({ ...current, [item.id]: result }));
      populateOverride(result);
      void loadOverview(item.id);
      return result;
    } catch (error) { onError(error instanceof Error ? error.message : 'Unable to generate the Engineering Estimation Report.'); return undefined; }
    finally { setEstimationBusy(''); }
  }

  async function overrideEstimate(item: PlanningCenterItem) {
    const current = estimates[item.id];
    if (!current) return;
    setEstimationBusy(item.id);
    try {
      const params = new URLSearchParams();
      if (projectId) params.set('projectId', projectId);
      const query = params.toString();
      const response = await fetch(`${baseUrl}/planning/${encodeURIComponent(item.id)}/estimate${query ? `?${query}` : ''}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          engineeringHours: Number(overrideHours), engineeringDays: Number(overrideDays), storyPoints: Number(overridePoints),
          estimatedSprintCount: Number(overrideSprints), developersNeeded: Number(overrideDevelopers),
          confidence: Number(overrideConfidence), risk: overrideRisk, complexity: overrideComplexity,
          overrideReason, actor, expectedEstimateId: current.estimateId,
          expectedOverrideRevision: current.override?.revision || 0,
        }),
      });
      const result = await response.json() as EngineeringEstimation & { error?: { message?: string } };
      if (!response.ok) throw new Error(result.error?.message || 'Unable to save the estimate override.');
      setEstimates((values) => ({ ...values, [item.id]: result }));
      setOverrideOpen(false); setOverrideReason('');
      void loadOverview(item.id);
    } catch (error) { onError(error instanceof Error ? error.message : 'Unable to save the estimate override.'); }
    finally { setEstimationBusy(''); }
  }

  function populateOverride(result: EngineeringEstimation) {
    const value = result.effectiveEstimate;
    setOverrideHours(String(value.engineeringHours || ''));
    setOverrideDays(String(value.engineeringDays || ''));
    setOverridePoints(String(value.storyPoints || ''));
    setOverrideSprints(String(value.estimatedSprintCount || ''));
    setOverrideDevelopers(String(value.developersNeeded || value.suggestedTeamSize || ''));
    setOverrideConfidence(String(value.confidence ?? ''));
    setOverrideRisk(value.risk || 'Medium');
    setOverrideComplexity(value.complexity || 'Medium');
  }

  function toggleExpanded(itemId: string) {
    setExpandedIds((current) => { const next = new Set(current); if (next.has(itemId)) next.delete(itemId); else next.add(itemId); return next; });
  }

  function toggleChecked(itemId: string) {
    setCheckedIds((current) => { const next = new Set(current); if (next.has(itemId)) next.delete(itemId); else next.add(itemId); return next; });
  }

  function generate(item: PlanningCenterItem) {
    if (!currentWorkItemId || ![item.id, item.sourceItemId].includes(currentWorkItemId)) {
      onError(`Open ${item.type} ${item.sourceItemId || item.id} in Azure DevOps before generating its Execution Package.`);
      return;
    }
    onGenerateExecutionPackage();
  }

  async function saveDraft() {
    if (!selected) return;
    setActionId(selected.id);
    try {
      const response = await fetch(`${baseUrl}/planning/${encodeURIComponent(selected.id)}/save?actor=${encodeURIComponent(actor)}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: draftTitle, description: draftDescription, expectedVersion: selected.version, status: 'Draft' }),
      });
      const payload = await response.json() as PlanningCenterItem & { error?: { message?: string } };
      if (!response.ok) throw new Error(payload.error?.message || 'Unable to save the Planning draft.');
      await load(false);
    } catch (error) { onError(error instanceof Error ? error.message : 'Unable to save the Planning draft.'); }
    finally { setActionId(''); }
  }

  async function mutateHierarchy(action: 'edit' | 'move' | 'reorder' | 'duplicate' | 'split' | 'merge' | 'regenerate' | 'delete', payload: Record<string, unknown>) {
    const nodeId = String(payload.nodeId || 'hierarchy');
    setActionId(nodeId);
    try {
      const endpoint = action === 'regenerate' ? '/planning/node/regenerate' : '/planning/node';
      const method = action === 'regenerate' ? 'POST' : action === 'delete' ? 'DELETE' : 'PUT';
      const response = await fetch(`${baseUrl}${endpoint}?actor=${encodeURIComponent(actor)}`, {
        method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...payload, action }),
      });
      const result = await response.json() as Record<string, unknown> & { error?: { message?: string } };
      if (!response.ok) throw new Error(result.error?.message || `Unable to ${action} the planning node.`);
      const resultNode = firstObject(result.node, result);
      const createdNodes = arrayValue(result.nodes).filter((value): value is Record<string, unknown> => Boolean(value && typeof value === 'object' && !Array.isArray(value)));
      const nextId = String(resultNode.id || createdNodes[0]?.id || '');
      if (action === 'delete' && selectedId === nodeId) setSelectedId('');
      else if (nextId) setSelectedId(nextId);
      await load(false);
    } catch (error) {
      onError(error instanceof Error ? error.message : `Unable to ${action} the planning node.`);
    } finally {
      setActionId('');
    }
  }

  function exportPlanning() {
    if (!selected) return;
    const payload = JSON.stringify({ exportedAt: new Date().toISOString(), planningPack: selected, estimate: selectedEstimate || null }, null, 2);
    const url = URL.createObjectURL(new Blob([payload], { type: 'application/json' }));
    const link = document.createElement('a');
    link.href = url; link.download = `${selected.title.replace(/[^a-z0-9]+/gi, '-').toLowerCase() || 'planning-pack'}-v${selected.version || 1}.json`;
    link.click(); URL.revokeObjectURL(url);
  }

  const canSaveDraft = Boolean(selected && selected.source === 'planning_artifact' && ['Draft', 'Review'].includes(selected.status));
  const repositoryName = selected ? planningRepository(selected) : '';
  const workspaceActions = selected ? {
    status: selected.status,
    canGenerate: selected.type !== 'Recommendation',
    canSave: canSaveDraft,
    canApprove: canContribute && (selected.canPublish || (selected.canApprove && Boolean(selectedEstimate))),
    primaryLabel: selected.canPublish ? 'Publish' : 'Approve',
    busy: Boolean(actionId || estimationBusy),
    onGenerate: () => selected.canGenerateExecutionPackage ? generate(selected) : void estimate(selected, true),
    onSave: () => void saveDraft(),
    onApprove: () => selected.canPublish ? void transitionPlanning('publish') : void decide(selected, 'approve'),
    onExport: exportPlanning,
  } : null;

  if (!selected || !workspaceActions) return <section className="hei-planning-center"><div className="hei-planning-empty"><strong>No Planning Pack is available.</strong><span>Generate a Planning Pack from an approved Requirement Summary.</span></div></section>;

  const overview = <PlanningOverview
    data={overviewData}
    loading={overviewLoading}
    error={overviewError}
    canApprove={workspaceActions.canApprove}
    onHierarchy={() => setActiveTab('Hierarchy')}
    onEstimate={() => setActiveTab('Estimate')}
    onDependencies={() => setActiveTab('Dependencies')}
    onApprove={workspaceActions.onApprove}
  />;

  const hierarchy = hierarchyLoading && !hierarchyData
    ? <div className="hei-planning-overview-state"><strong>Loading Planning Hierarchy...</strong><span>Resolving the selected Planning Pack subtree.</span></div>
    : hierarchyError
      ? <div className="hei-planning-overview-state"><strong>Planning Hierarchy is unavailable.</strong><span>{hierarchyError}</span><button className="planner-button secondary" type="button" onClick={() => hierarchyRoot && void loadHierarchy(hierarchyRoot.id)}>Retry</button></div>
      : <PlanningHierarchy
        baseUrl={baseUrl} projectId={projectId} actor={actor}
        items={hierarchyData?.nodes || hierarchyItems} selectedId={selected.id} busy={Boolean(actionId)} canEdit={canContribute && (hierarchyData?.editable ?? true)}
        onSelect={setSelectedId} onAction={mutateHierarchy} onChanged={async () => { await load(false); }} onError={onError}
      />;

  const tabBodies: Record<PlanningTab, React.ReactNode> = {
    Overview: <PlanningContent title="Planning Overview" description="Business context, readiness, and current planning health.">{overview}</PlanningContent>,
    Hierarchy: <PlanningContent title="Planning Hierarchy" description="Explore and review the Epic, Feature, Story, and Task lineage.">{hierarchy}</PlanningContent>,
    Traceability: <PlanningContent title="Traceability" description="Follow the selected artifact back to its approved planning source."><nav className="hei-planning-breadcrumbs">{breadcrumbs.map((item, index) => <React.Fragment key={item.id}><button type="button" onClick={() => setSelectedId(item.id)}>{item.type}: {item.title}</button>{index < breadcrumbs.length - 1 ? <span>›</span> : null}</React.Fragment>)}</nav><div className="hei-planning-detail-grid"><Detail label="Planning ID" value={selected.id} /><Detail label="Source Item" value={selected.sourceItemId || 'Not linked'} /><Detail label="Source" value={selected.source} /><Detail label="Parent" value={selected.parentId || 'Root'} /><Detail label="Children" value={selected.childCount} /><Detail label="Version" value={`v${selected.version || 1}`} /></div></PlanningContent>,
    Dependencies: <PlanningContent title="Dependency Management" description="Define execution order, resolve blockers, and review the critical path."><PlanningDependencies data={dependencyData} loading={dependencyLoading} error={dependencyError} view={dependencyView} selectedId={selected.id} canEdit={canContribute} busy={dependencyBusy} onView={setDependencyView} onSave={saveDependency} onDelete={deleteDependency} onSelect={setSelectedId} onRetry={() => hierarchyRoot && void loadDependencies(hierarchyRoot.id)} /></PlanningContent>,
    Estimate: <PlanningContent title="Engineering Estimate" description="Transparent effort and delivery estimates for the complete Planning Pack."><EstimationReport estimate={packEstimate} loading={estimationBusy === hierarchyRoot?.id} onRecalculate={() => hierarchyRoot && void estimate(hierarchyRoot, true)} onEdit={canContribute && hierarchyRoot?.source === 'planning_artifact' && ['Draft', 'Review'].includes(hierarchyRoot.status) ? () => setOverrideOpen((value) => !value) : undefined} />{overrideOpen && packEstimate && hierarchyRoot ? <div className="hei-estimation-override"><label><span>Engineering Days</span><input type="number" min="0.25" step="0.25" value={overrideDays} onChange={(event) => { setOverrideDays(event.target.value); const value = Number(event.target.value); if (value > 0) setOverrideHours(String(value * 8)); }} /></label><label><span>Hours</span><input type="number" min="1" step="0.5" value={overrideHours} onChange={(event) => { setOverrideHours(event.target.value); const value = Number(event.target.value); if (value > 0) setOverrideDays(String(value / 8)); }} /></label><label><span>Story Points</span><input type="number" min="1" value={overridePoints} onChange={(event) => setOverridePoints(event.target.value)} /></label><label><span>Sprint Count</span><input type="number" min="0.5" step="0.5" value={overrideSprints} onChange={(event) => setOverrideSprints(event.target.value)} /></label><label><span>Developers Needed</span><input type="number" min="1" value={overrideDevelopers} onChange={(event) => setOverrideDevelopers(event.target.value)} /></label><label><span>Confidence</span><input type="number" min="0" max="100" value={overrideConfidence} onChange={(event) => setOverrideConfidence(event.target.value)} /></label><label><span>Risk</span><select value={overrideRisk} onChange={(event) => setOverrideRisk(event.target.value)}>{['Low', 'Medium', 'High', 'Critical'].map((value) => <option key={value}>{value}</option>)}</select></label><label><span>Complexity</span><select value={overrideComplexity} onChange={(event) => setOverrideComplexity(event.target.value)}>{['Very Low', 'Low', 'Medium', 'High', 'Very High'].map((value) => <option key={value}>{value}</option>)}</select></label><label className="wide"><span>Override Reason</span><textarea value={overrideReason} onChange={(event) => setOverrideReason(event.target.value)} placeholder="Explain the engineering evidence behind this override." /></label><div className="wide hei-estimation-override-actions"><button className="planner-button secondary" type="button" onClick={() => setOverrideOpen(false)}>Cancel</button><button className="planner-button primary" type="button" onClick={() => void overrideEstimate(hierarchyRoot)} disabled={!overrideReason.trim() || estimationBusy === hierarchyRoot.id}>Save User Estimate</button></div></div> : null}</PlanningContent>,
    Review: <PlanningContent title="Planning Review" description="Refine the draft before requesting approval."><div className="hei-planning-review-form"><label><span>Planning Pack Name</span><input value={draftTitle} onChange={(event) => setDraftTitle(event.target.value)} disabled={!canSaveDraft} /></label><label><span>Description</span><textarea value={draftDescription} onChange={(event) => setDraftDescription(event.target.value)} disabled={!canSaveDraft} /></label></div><DetailList title="Dependencies" values={selected.dependencies} empty="No dependencies identified." /><DetailList title="Risks" values={selected.risks} empty="No planning risks identified." /></PlanningContent>,
    Diff: <PlanningContent title="Planning Diff" description="Review the exact create, modify, keep, and ignore decisions before Azure DevOps synchronization."><PlanningDiff data={planningDiff} loading={planningDiffLoading} error={planningDiffError} busy={planningDiffBusy} canApprove={canContribute} onApprove={() => void approvePlanningDiff()} onRetry={() => hierarchyRoot && void loadPlanningDiff(hierarchyRoot.id)} /></PlanningContent>,
    Approval: <PlanningContent title="Planning Approval" description="Review the decision record, capture comments, and advance the approved engineering artifact."><EstimationReport estimate={selectedEstimate} loading={estimationBusy === selected.id} onRecalculate={() => void estimate(selected, true)} onEdit={() => setActiveTab('Estimate')} /><div className="hei-planning-actions"><Detail label="Status" value={selected.status} /><Detail label="Readiness" value={selected.readiness} /><Detail label="Confidence" value={`${selected.confidence}%`} /><Detail label="Approver" value={selected.approver || 'Approval Pending'} /><Detail label="Approved On" value={selected.approvedAt || 'Not approved'} /><Detail label="Version" value={`v${selected.version}`} /></div><section className="hei-planning-approval-controls"><label><span>Approval Comments</span><textarea value={approvalComments} onChange={(event) => setApprovalComments(event.target.value)} placeholder="Record the decision context, requested changes, or publication note." /></label><div>{selected.canApprove ? <button className="planner-button primary" type="button" disabled={!canContribute || !selectedEstimate || Boolean(actionId)} onClick={() => void decide(selected, 'approve')}>Approve</button> : null}{selected.canReject ? <button className="planner-button danger" type="button" disabled={!canContribute || !approvalComments.trim() || Boolean(actionId)} onClick={() => void decide(selected, 'reject')}>Reject</button> : null}{selected.canRequestChanges ? <button className="planner-button secondary" type="button" disabled={!canContribute || !approvalComments.trim() || Boolean(actionId)} onClick={() => void transitionPlanning('request-changes')}>Request Changes</button> : null}{selected.canPublish ? <button className="planner-button primary" type="button" disabled={!canContribute || Boolean(actionId)} onClick={() => void transitionPlanning('publish')}>Publish</button> : null}</div></section><ApprovalHistory value={approvalHistory} loading={approvalHistoryLoading} onRollback={(version) => void transitionPlanning('rollback', version)} canRollback={canContribute && selected.canRollback && !Boolean(actionId)} /></PlanningContent>,
  };

  return <PlanningWorkspace
    header={<PlanningHeader name={selected.title} status={selected.status} confidence={selected.confidence} repository={repositoryName} version={selected.version} updated={selected.updatedAt} />}
    tabs={<PlanningTabs active={activeTab} onChange={setActiveTab} />}
    actionPanel={<PlanningActions {...workspaceActions} />}
    footer={<PlanningActions {...workspaceActions} compact />}
  >{tabBodies[activeTab]}{data?.pagination.hasMore ? <p className="hei-planning-limit">Showing {data.pagination.returned} of {data.pagination.total} items.</p> : null}</PlanningWorkspace>;
}

function Detail({ label, value }: { label: string; value: string | number }) {
  return <div><span>{label}</span><strong>{value}</strong></div>;
}

function DetailList({ title, values, empty }: { title: string; values: string[]; empty: string }) {
  return <section className="hei-planning-list"><strong>{title}</strong>{values.length ? <ul>{values.map((value) => <li key={value}>{value}</li>)}</ul> : <p>{empty}</p>}</section>;
}

function ApprovalHistory({ value, loading, onRollback, canRollback }: { value?: PlanningApprovalHistory; loading: boolean; onRollback: (version: number) => void; canRollback: boolean }) {
  return <section className="hei-planning-approval-history"><header><div><span>Approval History</span><h4>Version and decision timeline</h4></div><strong>{value?.count || 0} records</strong></header>{loading ? <p>Loading approval history...</p> : !value?.history.length ? <p>No approval decisions recorded yet.</p> : <div>{[...value.history].reverse().map((item) => <article key={`${item.version}-${item.action}`}><div><strong>v{item.version} · {item.status}</strong><span>{item.action.replace(/_/g, ' ')} by {item.actor}</span><small>{item.timestamp || 'Timestamp not recorded'}</small>{item.comments ? <p>{item.comments}</p> : null}</div>{item.canRollback ? <button className="planner-button secondary" type="button" disabled={!canRollback} onClick={() => onRollback(item.version)}>Rollback to v{item.version}</button> : null}</article>)}</div>}</section>;
}

function EstimationReport({ estimate, loading, onRecalculate, onEdit }: { estimate?: EngineeringEstimation; loading: boolean; onRecalculate: () => void; onEdit?: () => void }) {
  if (!estimate) return <section className="hei-estimation-report loading"><div><span>Engineering Estimation</span><h4>{loading ? 'Calculating from engineering evidence...' : 'Estimation Report not available'}</h4></div><p>HEI uses task decomposition, repository context, acceptance criteria, risk, dependencies, and approved Engineering Memory.</p>{!loading ? <button className="planner-button secondary" type="button" onClick={onRecalculate}>Retry Estimation</button> : null}</section>;
  const value = estimate.effectiveEstimate;
  const report = value.report;
  return <section className="hei-estimation-report" aria-label="Engineering Estimation Report">
    <header><div><span>Planning Summary</span><h4>Engineering Estimation Report</h4><p>Standard Engineering Estimation · Version {estimate.version}{estimate.status === 'Overridden' ? ' · Human override applied' : ''}</p></div><StatusBadge value={estimate.status} /></header>
    <div className="hei-estimation-metrics">
      <Detail label="Engineering Days" value={value.engineeringDays} />
      <Detail label="Story Points" value={report.storyPoints} />
      <Detail label="Hours" value={value.engineeringHours} />
      <Detail label="Sprint Count" value={value.estimatedSprintCount} />
      <Detail label="Developers Needed" value={value.developersNeeded || value.suggestedTeamSize || report.suggestedTeamSize || 1} />
      <Detail label="Confidence" value={`${report.confidence}%`} />
      <Detail label="Risk" value={value.risk} />
      <Detail label="Complexity" value={value.complexity} />
    </div>
    <div className="hei-estimation-supporting-metrics">
      <Detail label="Repository Reuse" value={`${report.repositoryReuse}%`} />
      <Detail label="Estimated Test Cases" value={report.estimatedTestCases} />
      <Detail label="Estimated Pull Requests" value={report.estimatedPullRequests} />
      <Detail label="High Risk Stories" value={report.highRiskStories} />
    </div>
    <div className="hei-estimation-comparison"><EstimateSnapshot title="AI Estimate" value={estimate.aiEstimate || estimate.originalEstimate} /><EstimateSnapshot title="User Estimate" value={estimate.userEstimate} empty="No manual override applied." />{estimate.isOverridden ? <section><span>Override Reason</span><strong>{estimate.override?.reason || estimate.overrideReason}</strong><small>Revision {estimate.override?.revision || 1} · Original AI estimate retained</small></section> : null}</div>
    <div className="hei-estimation-body"><section><strong>Top Estimation Drivers</strong>{value.topEstimationDrivers.length ? <ul>{value.topEstimationDrivers.map((driver) => <li key={driver}>{driver}</li>)}</ul> : <p>No estimation drivers were supplied.</p>}</section><section><strong>Task Foundation</strong>{value.taskEstimates.slice(0, 8).map((task) => <div className="hei-estimation-task" key={task.taskId || task.taskName}><span>{task.taskName}</span><strong>{task.estimatedDuration} · {task.storyPointContribution} pts</strong><small>{task.complexity} · {task.confidence}% confidence</small></div>)}</section></div>
    {value.warnings.length ? <details><summary>{value.warnings.length} confidence warning{value.warnings.length === 1 ? '' : 's'}</summary><ul>{value.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></details> : null}
    {estimate.override?.history?.length ? <details><summary>Override History ({estimate.override.history.length})</summary><ul>{estimate.override.history.map((item) => <li key={item.revision}>Revision {item.revision}: {item.reason} · {item.actor}</li>)}</ul></details> : null}
    <div className="hei-estimation-actions"><button className="planner-button secondary" type="button" onClick={onRecalculate} disabled={loading}>{loading ? 'Recalculating...' : 'Recalculate AI Estimate'}</button>{onEdit ? <button className="planner-button secondary" type="button" onClick={onEdit}>Edit Estimate</button> : null}</div>
  </section>;
}

function EstimateSnapshot({ title, value, empty }: { title: string; value?: EstimateValues; empty?: string }) {
  return <section><span>{title}</span>{value ? <><strong>{value.engineeringDays || 0} days · {value.storyPoints || 0} points</strong><small>{value.engineeringHours || 0} hours · {value.estimatedSprintCount || 0} sprints · {value.developersNeeded || value.suggestedTeamSize || 1} developers</small></> : <strong>{empty || 'Not available'}</strong>}</section>;
}

function buildTree(items: PlanningCenterItem[]): PlanningTreeNode[] {
  const nodes = new Map(items.map((item) => [item.id, { ...item, children: [] } as PlanningTreeNode]));
  const sourceIds = new Map(items.filter((item) => item.sourceItemId).map((item) => [item.sourceItemId, item.id]));
  const roots: PlanningTreeNode[] = [];
  nodes.forEach((node) => {
    const parentId = nodes.has(node.parentId) ? node.parentId : sourceIds.get(node.parentId) || '';
    const parent = parentId ? nodes.get(parentId) : undefined;
    if (parent && parent.id !== node.id) parent.children.push(node); else roots.push(node);
  });
  const sort = (values: PlanningTreeNode[]) => values.sort((left, right) => (TYPE_ORDER[left.type] ?? 99) - (TYPE_ORDER[right.type] ?? 99) || left.title.localeCompare(right.title)).forEach((item) => sort(item.children));
  sort(roots);
  return roots;
}

function flattenVisible(tree: PlanningTreeNode[], expanded: Set<string>): Array<{ item: PlanningTreeNode; level: number; hasChildren: boolean }> {
  const output: Array<{ item: PlanningTreeNode; level: number; hasChildren: boolean }> = [];
  const visit = (nodes: PlanningTreeNode[], level: number) => nodes.forEach((item) => {
    output.push({ item, level, hasChildren: Boolean(item.children.length) });
    if (item.children.length && expanded.has(item.id)) visit(item.children, level + 1);
  });
  visit(tree, 0);
  return output;
}

function buildBreadcrumbs(selected: PlanningCenterItem, items: PlanningCenterItem[]): PlanningCenterItem[] {
  const byId = new Map(items.map((item) => [item.id, item]));
  const sourceIds = new Map(items.filter((item) => item.sourceItemId).map((item) => [item.sourceItemId, item]));
  const path: PlanningCenterItem[] = [];
  const visited = new Set<string>();
  let cursor: PlanningCenterItem | undefined = selected;
  while (cursor && !visited.has(cursor.id)) {
    visited.add(cursor.id);
    path.unshift(cursor);
    cursor = byId.get(cursor.parentId) || sourceIds.get(cursor.parentId);
  }
  return path;
}

function descendantsOf(parentId: string, items: PlanningCenterItem[]): PlanningCenterItem[] {
  const output: PlanningCenterItem[] = [];
  const visited = new Set<string>();
  const visit = (id: string) => {
    if (visited.has(id)) return;
    visited.add(id);
    const sourceId = items.find((candidate) => candidate.id === id)?.sourceItemId;
    items.filter((item) => item.parentId === id || Boolean(sourceId && item.parentId === sourceId)).forEach((item) => { output.push(item); visit(item.id); });
  };
  visit(parentId);
  return output;
}
function firstObject(...values: unknown[]): Record<string, unknown> { return values.find((value) => value && typeof value === 'object' && !Array.isArray(value)) as Record<string, unknown> || {}; }
function arrayValue(value: unknown): unknown[] { return Array.isArray(value) ? value : value == null ? [] : [value]; }
function planningRepository(item: PlanningCenterItem): string {
  const details = item.details || {};
  const requirementSummary = firstObject(details.requirementSummary);
  const projectContext = firstObject(details.projectContext);
  const repository = firstObject(requirementSummary.repository, details.repository, details.repositoryContext, details.repositoryIntelligence);
  return String(repository.name || repository.repositoryName || repository.repository_name || repository.repositoryId || repository.repository_id || projectContext.repositoryId || '').trim();
}

function TypeBadge({ value }: { value: string }) { return <span className="hei-type-badge">{value}</span>; }
function StatusBadge({ value }: { value: string }) { return <span className={`hei-status-badge status-${value.toLowerCase().replace(/[^a-z]+/g, '-')}`}>{value}</span>; }
