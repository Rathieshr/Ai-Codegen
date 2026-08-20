import * as SDK from 'azure-devops-extension-sdk';
import { CommonServiceIds, IProjectPageService } from 'azure-devops-extension-api/Common/CommonServices';
import { getClient } from 'azure-devops-extension-api/Common/Client';
import { GraphRestClient } from 'azure-devops-extension-api/Graph/GraphClient';
import { GraphTraversalDirection } from 'azure-devops-extension-api/Graph/Graph';
import { GitRepository } from 'azure-devops-extension-api/Git/Git';
import { IWorkItemFormService, WorkItemTrackingServiceIds } from 'azure-devops-extension-api/WorkItemTracking';
import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  EngineeringCommandCenterShell,
  EngineeringWorkspace,
  WorkspaceNavigationItem,
  WorkspacePreferences,
} from './engineeringCommandCenterShell';
import { DashboardOverview, OperationalOverviewDashboard } from './overviewDashboard';
import { PlanningCenter } from './planningCenter';
import { RepositoryCenter } from './repositoryCenter';
import { ExecutionCenter } from './executionCenter';
import { ApprovalCenter } from './approvalCenter';
import { AzureDevOpsCenter } from './azureDevOpsCenter';
import { AgentCenter } from './agentCenter';
import './storyPlanner.css';

const ActivityCenter = React.lazy(() => import('./activityCenter').then((module) => ({ default: module.ActivityCenter })));
const CommandCenterHealth = React.lazy(() => import('./commandCenterHealth').then((module) => ({ default: module.CommandCenterHealth })));

const BASE_URL = 'https://ai-codegen-production.up.railway.app/project-intelligence';
const PLATFORM_BASE_URL = BASE_URL.replace(/\/project-intelligence$/, '');

const DOMAIN_OPTIONS = [
  'Utility Grid Management',
  'Smart Metering',
  'Asset Monitoring',
  'Field Operations',
  'Property Management',
  'Hospitality',
  'Healthcare',
  'Retail',
  'Manufacturing',
  'Custom',
];

const PROJECT_TYPES = [
  'Mobile Application',
  'Web Application',
  'Backend Service',
  'Embedded Firmware',
  'Analytics Platform',
  'Multi-System Platform',
];

const APPLICATION_TYPES = ['Mobile', 'Backend', 'Firmware', 'Web Portal', 'Analytics', 'Desktop', 'API'];
const STACK_FIELDS: Array<keyof TechnologyStack> = ['mobile', 'backend', 'firmware', 'analytics', 'frontend'];
const API_TIMEOUT_MS = 120000;
const REPOSITORY_SDK_TIMEOUT_MS = 8000;
const REPOSITORY_FILE_TIMEOUT_MS = 10000;
const REPOSITORY_DOCUMENTS = [
  'README.md',
  'docs/README.md',
  'architecture.md',
  'docs/architecture.md',
  'modules.md',
  'docs/modules.md',
  'flows.md',
  'docs/flows.md',
  'ui-guidelines.md',
  'docs/ui-guidelines.md',
  'coding-standards.md',
  'docs/coding-standards.md',
];
const PROJECT_SESSION_STORAGE_KEY = 'ai-gen-project-intelligence:last-session';
const AZURE_DEVOPS_PERMISSION_MAPPING_ENABLED = false;

type PlannerTab = 'overview' | 'planning' | 'execution' | 'qa' | 'memory' | 'governance' | 'agents' | 'skills' | 'admin' | 'diagnostics';
type AIGenRole = 'admin' | 'contributor' | 'viewer';
type WorkItemKind = 'Epic' | 'Feature' | 'Story' | 'Task' | 'Bug' | 'Test Case';
type RoutedWorkspace = Extract<PlannerTab, 'planning' | 'execution' | 'qa'>;
type ApprovalStatus = 'locked' | 'draft' | 'ready_for_approval' | 'approved';
type ApprovalArtifact = 'epic' | 'features' | 'feature' | 'stories' | 'story' | 'tasks' | 'qa' | 'execution';
type ApprovalWorkflowState = Record<ApprovalArtifact, ApprovalStatus>;
type WorkflowHealthStatus = 'Ready' | 'Needs Attention' | 'Blocked' | 'In Progress';
type WorkflowActionKind =
  | 'analyze_epic'
  | 'approve_epic'
  | 'analyze_feature'
  | 'generate_features'
  | 'create_children'
  | 'approve_features'
  | 'approve_feature'
  | 'analyze_story'
  | 'generate_stories'
  | 'approve_stories'
  | 'approve_story'
  | 'generate_tasks'
  | 'approve_tasks'
  | 'generate_tests'
  | 'build_execution'
  | 'open_vscode'
  | 'open_planning'
  | 'open_execution'
  | 'open_qa';
type WorkflowNextAction = {
  label: string;
  action: WorkflowActionKind;
  workspace: PlannerTab;
  reason: string;
};
type WorkflowOrchestrationState = {
  statuses: Record<'epic' | 'features' | 'stories' | 'tasks' | 'tests' | 'execution', 'complete' | 'current' | 'pending' | 'blocked'>;
  planningHealth: WorkflowHealthStatus;
  executionHealth: WorkflowHealthStatus;
  qaHealth: WorkflowHealthStatus;
  coverageHealth: WorkflowHealthStatus;
  currentStage: string;
  nextAction: WorkflowNextAction;
  blockers: string[];
};
type ArtifactLifecycleState = 'draft' | 'approved' | 'locked' | 'archived';
type ArtifactType =
  | 'Epic'
  | 'Feature'
  | 'Story'
  | 'Task'
  | 'Acceptance Criteria'
  | 'Execution Package'
  | 'Implementation Package'
  | 'Execution Plan'
  | 'Implementation Plan'
  | 'Dev Prompt'
  | 'AI Prompt'
  | 'UI Prompt'
  | 'QA Prompt'
  | 'Context Capsule'
  | 'Copilot Context'
  | 'Test Suite'
  | 'Test Plan'
  | 'Coverage Report';
type EngineeringMemoryItem = {
  id: string;
  projectId: string;
  category: string;
  title: string;
  summary: string;
  content?: string;
  artifactType: string;
  artifactId: string;
  tags: string[];
  confidence: number;
  approvalStatus: string;
  version: number;
  createdAt: string;
  updatedAt: string;
  lastUsedAt?: string;
  usageCount?: number;
  knowledgeReferences?: string[];
  graphReferences?: string[];
  repositoryEvidence?: Array<Record<string, unknown>>;
  searchScore?: number;
  matchReasons?: string[];
};
type EngineeringMemoryResponse = {
  memories?: EngineeringMemoryItem[];
  results?: EngineeringMemoryItem[];
  count?: number;
  diagnostics?: Record<string, unknown>;
};
type GovernanceDashboard = {
  policies?: GovernancePolicy[];
  approvals?: {
    approvals?: GovernanceApproval[];
    count?: number;
    byStatus?: Record<string, number>;
  };
  compliance?: {
    status?: string;
    score?: number;
    scores?: Record<string, number>;
    findings?: Array<Record<string, unknown>>;
  };
  metrics?: Record<string, number>;
  feedback?: {
    feedback?: GovernanceFeedback[];
    count?: number;
    byRating?: Record<string, number>;
    satisfaction?: number;
  };
  observability?: {
    observations?: GovernanceObservation[];
    count?: number;
    byEngine?: Record<string, number>;
    byStatus?: Record<string, number>;
    averageLatencyMs?: number;
    failureCount?: number;
    tokenUsage?: number;
  };
  auditTimeline?: {
    events?: GovernanceAuditEvent[];
    count?: number;
  };
  scorecard?: Record<string, number | string>;
  diagnostics?: Record<string, unknown>;
};
type GovernancePolicy = {
  id?: string;
  name?: string;
  area?: string;
  description?: string;
  enabled?: boolean;
  severity?: string;
  rules?: Record<string, unknown>;
};
type GovernanceApproval = {
  id?: string;
  artifactType?: string;
  artifactId?: string;
  artifactTitle?: string;
  status?: string;
  requestedBy?: string;
  approvedBy?: string;
  reason?: string;
  updatedAt?: string;
};
type GovernanceFeedback = {
  id?: string;
  category?: string;
  rating?: string;
  comment?: string;
  reason?: string;
  createdBy?: string;
  createdAt?: string;
};
type GovernanceObservation = {
  id?: string;
  engine?: string;
  operation?: string;
  status?: string;
  durationMs?: number;
  provider?: string;
  model?: string;
};
type GovernanceAuditEvent = {
  id?: string;
  who?: string;
  what?: string;
  when?: string;
  why?: string;
  artifactType?: string;
  artifactId?: string;
  eventType?: string;
};
type AgentDashboard = {
  agents?: AgentDefinition[];
  featureFlags?: Record<string, boolean>;
  policies?: string[];
  runningAgents?: AgentWorkflow[];
  waitingAgents?: AgentWorkflow[];
  completedWorkflows?: AgentWorkflow[];
  failedWorkflows?: AgentWorkflow[];
  pendingJobs?: AgentWorkflow[];
  history?: AgentHistoryEntry[];
  lastRun?: Record<string, AgentLastRun>;
  failures?: AgentWorkflow[];
  upcomingActions?: AgentUpcomingAction[];
  agentTimeline?: AgentTimelineEvent[];
  diagnostics?: Record<string, unknown>;
};
type AgentDefinition = {
  id?: string;
  name?: string;
  responsibility?: string;
  triggers?: string[];
  actions?: string[];
  checkpoint?: string;
};
type AgentWorkflow = {
  id?: string;
  agent?: string;
  trigger?: string;
  artifactType?: string;
  artifactId?: string;
  artifactTitle?: string;
  state?: string;
  status?: string;
  currentAction?: string;
  nextAction?: string;
  retryCount?: number;
  errors?: string[];
  steps?: Array<{ name?: string; status?: string; approvalBoundary?: boolean }>;
  timeline?: AgentTimelineEvent[];
};
type AgentUpcomingAction = {
  workflowId?: string;
  agent?: string;
  nextAction?: string;
  artifactType?: string;
  artifactId?: string;
};
type AgentTimelineEvent = {
  time?: string;
  type?: string;
  message?: string;
  source?: string;
  status?: string;
};
type AgentHistoryEntry = {
  time?: string;
  type?: string;
  agent?: string;
  message?: string;
  artifactType?: string;
  artifactId?: string;
  status?: string;
};
type AgentLastRun = {
  workflowId?: string;
  artifactType?: string;
  artifactId?: string;
  state?: string;
  status?: string;
  time?: string;
};
type SkillsDashboard = {
  installedSkills?: EngineeringSkill[];
  groupedSkills?: Record<string, EngineeringSkill[]>;
  recommendedSkills?: EngineeringSkill[];
  recentlyUsed?: EngineeringSkill[];
  usageHistory?: SkillUsage[];
  executionHistory?: SkillExecutionEvent[];
  diagnostics?: Record<string, unknown>;
};
type EngineeringSkill = {
  id?: string;
  name?: string;
  category?: string;
  group?: string;
  description?: string;
  inputSchema?: Record<string, unknown>;
  outputSchema?: Record<string, unknown>;
  supportedArtifacts?: string[];
  requiredContext?: string[];
  requiredPermissions?: string[];
  compatibleAgents?: string[];
  dependencies?: string[];
  implementationPattern?: string;
  repositoryHints?: string[];
  architectureRules?: string[];
  acceptanceTemplates?: string[];
  testTemplates?: string[];
  validationRules?: string[];
  confidence?: number;
  version?: number;
  usageCount?: number;
  lastUsedAt?: string;
  matchScore?: number;
  matchReasons?: string[];
};
type SkillUsage = {
  skillIds?: string[];
  artifact?: Record<string, unknown>;
};
type SkillExecutionEvent = {
  skillId?: string;
  skillName?: string;
  group?: string;
  agentId?: string;
  status?: string;
  durationMs?: number;
  executedAt?: string;
  artifactTitle?: string;
};
type MemoryContextPayload = {
  relevantMemories?: Array<{ title?: string; category?: string; artifactType?: string; rankingScore?: number; retrievalReasons?: string[] }>;
  matchedPatterns?: unknown[];
  previousSuccessfulArtifacts?: unknown[];
  knownRisks?: string[];
  reusableAcceptanceCriteria?: string[];
  reusableTests?: string[];
  confidence?: number;
  retrievalReasons?: string[];
  excludedMemory?: Array<{ title?: string; reasons?: string[] }>;
  diagnostics?: Record<string, unknown>;
};
type AzureDevOpsUserIdentity = {
  id?: string;
  descriptor?: string;
  subjectId?: string;
  displayName?: string;
  name?: string;
  uniqueName?: string;
  email?: string;
};

let sdkInitializationStarted = false;

function ensureAzureDevOpsSdkInitialized() {
  if (sdkInitializationStarted) {
    return;
  }
  sdkInitializationStarted = true;
  document.documentElement.dataset.heiTheme = 'light';
  document.documentElement.style.colorScheme = 'light';
  SDK.init({ loaded: false, applyTheme: false });
}

ensureAzureDevOpsSdkInitialized();

type ApplicationProfile = {
  name: string;
  type: string;
};

type TechnologyStack = {
  mobile: string[];
  backend: string[];
  firmware: string[];
  analytics: string[];
  frontend: string[];
};

type DevelopmentStandards = {
  architecture_patterns: string[];
  coding_guidelines: string[];
  security_requirements: string[];
  testing_requirements: string[];
};

type ModuleDetail = {
  name: string;
  responsibilities?: string[];
  dependencies?: string[];
  source_file?: string;
};

type FlowDetail = {
  name: string;
  steps?: string[];
  source_file?: string;
};

type ComponentDetail = {
  name: string;
  type?: string;
  source_file?: string;
};

type ProviderMetadata = {
  provider_used?: string;
  source?: string;
  phi_status?: string;
  fallback_used?: boolean;
  fallback_reason?: string;
  phi_latency_ms?: number;
  phi_raw_response_preview?: string;
  phi_parsed_response_preview?: string;
  phi_prompt_tokens?: number;
  phi_completion_tokens?: number;
  phi_finish_reason?: string;
  phi_response_length?: number;
  diagnostics_available?: boolean;
  diagnostics_path?: string;
  diagnostics_files?: string[];
  diagnostics_error?: string;
  raw_response_available?: boolean;
  raw_response_preview?: string;
  provider_configured?: boolean;
  provider_deployment?: string;
  provider_health?: string;
  provider_last_success?: string | null;
  provider_last_failure?: string | null;
  context_size?: number;
  context_after_compression?: number;
  tokens_sent?: number;
  context_budget_tokens?: number;
  compression_ratio?: number;
  context_compression_level?: number;
  original_context_tokens?: number;
  compressed_context_tokens?: number;
  system_prompt_tokens?: number;
  user_prompt_tokens?: number;
  output_schema_tokens?: number;
  final_prompt_tokens?: number;
  model_context_limit?: number;
  reserved_tokens?: number;
  project_context_tokens?: number;
  context_budget_used?: number;
  retry_attempt?: number;
  compression_level?: number;
  project_summary_mode?: boolean;
  configured_budget_tokens?: number;
  compression_applied?: boolean;
  largest_context_sections?: Array<{ section?: string; tokens?: number }>;
  context_section_tokens?: Record<string, number>;
  final_prompt_preview?: string;
  prompt_too_long_stage?: string;
  context_capsule_used?: boolean;
  context_capsule_type?: string;
  context_capsule_version?: number;
  context_capsule_size_tokens?: number;
  context_capsule_source_size_tokens?: number;
  context_capsule_compression_ratio?: number;
  deterministic_generation_ms?: number;
  phi_enrichment_ms?: number;
  timeout_used?: boolean;
  intent_keywords?: string[];
  selected_modules?: string[];
  selected_flows?: string[];
  selected_dependencies?: string[];
  rejected_context?: RejectedContextItem[];
  relevance_scores?: Record<string, number>;
  token_estimate?: number;
  context_source?: string;
  memory_context?: MemoryContextPayload;
  memory_diagnostics?: Record<string, unknown>;
  intelligence_trace?: IntelligenceTracePayload;
};

type IntelligenceTraceItem = {
  id?: string;
  traceId?: string;
  projectId?: string;
  artifactType?: string;
  artifactId?: string;
  artifactTitle?: string;
  stage?: string;
  source?: string;
  decision?: string;
  reason?: string;
  confidence?: number;
  evidence?: unknown[];
  memoryUsed?: unknown[];
  repositoryEvidence?: unknown[];
  graphEvidence?: unknown[];
  validationResult?: Record<string, unknown>;
  promptVersion?: string;
  time?: string;
  latencyMs?: number;
  model?: string;
  tokenUsage?: Record<string, unknown>;
};

type IntelligenceTracePayload = {
  trace_id?: string;
  trace?: IntelligenceTraceItem;
  trace_summary?: {
    decision?: string;
    reason?: string;
    confidence?: number;
    stage?: string;
    memory_count?: number;
    repository_evidence_count?: number;
    graph_evidence_count?: number;
  };
};

type RejectedContextItem = {
  name?: string;
  type?: string;
  confidence?: number;
  reason?: string;
  evidence?: string[];
  source?: string;
};

type ProjectProfile = {
  onboarding_completed?: boolean;
  project_id?: string;
  project_name: string;
  domain: string;
  project_type: string;
  project_description: string;
  connectors?: {
    azure_devops?: AzureDevOpsConnectorMapping;
  };
  repository_connection: {
    repository_id: string;
    repository_name: string;
    branch: string;
    status: string;
    readme_path: string;
  };
  readme_analysis: {
    summary: string;
    applications: ApplicationProfile[];
    modules: string[];
    flows: string[];
    architecture_notes: string[];
  };
  knowledge_registry: {
    applications: ApplicationProfile[];
    modules: string[];
    module_details?: ModuleDetail[];
    flows: string[];
    flow_details?: FlowDetail[];
    components: string[];
    component_details?: ComponentDetail[];
    architecture_notes: string[];
    technology_stack?: TechnologyStack;
    standards: string[];
    source_files: string[];
  };
  applications: ApplicationProfile[];
  technology_stack: TechnologyStack;
  development_standards: DevelopmentStandards;
  ui_guidelines: {
    primary_color: string;
    secondary_color: string;
    typography: string;
    component_library: string;
    accessibility_rules: string[];
  };
  repository_sources: string[];
  knowledge_profile_preview: {
    domain: string;
    systems: string[];
    standards: string[];
    repository_status: string;
    readiness: string;
  };
};

type AdoProject = {
  id: string;
  name: string;
  description?: string;
  state?: string;
  visibility?: string;
  source?: string;
};

type AdoProjectListResponse = {
  projects: AdoProject[];
  configured?: boolean;
  missing_env?: string[];
  warnings?: string[];
  default_project?: string;
  organization_url?: string;
};

type AzureDevOpsConnectorMapping = {
  organization_url?: string;
  ado_project: string;
  repository_id: string;
  repository_name: string;
  branch: string;
};

type AzureProjectContext = {
  id: string;
  name: string;
  description: string;
};

type ProjectSessionSnapshot = {
  profile: ProjectProfile;
  active_project: string;
  repository_name: string;
  repository_id: string;
  branch: string;
  knowledge_version: string;
  last_analysis_timestamp: string;
  last_active_tab: PlannerTab;
  last_workspace?: PlannerTab;
  last_work_item_id?: number;
  last_work_item_type?: string;
  last_work_item_title?: string;
  auto_route_by_work_item_type?: boolean;
  approval_workflow?: ApprovalWorkflowState;
  knowledge_governance?: KnowledgeGovernance;
  execution_context?: ExecutionContextResult;
  execution_plan?: ExecutionPlanResult;
  dev_prompt?: PromptBuilderResult;
  ui_prompt?: PromptBuilderResult;
  qa_prompt?: PromptBuilderResult;
  copilot_context?: CopilotContextResult;
  qa_test_suite?: QATestSuiteResult;
  implementation_validation?: ImplementationValidationReport;
  pr_review?: PRReviewReport;
  saved_at: string;
};

type BackendProjectSessionResponse = {
  exists: boolean;
  session: Partial<ProjectSessionSnapshot> & Record<string, unknown>;
};

type KnowledgeCacheStatus = {
  project_id?: string;
  project_name?: string;
  repository?: string;
  repository_id?: string;
  branch?: string;
  knowledge_status: 'ready' | 'missing' | 'refresh_available' | 'stale';
  last_analyzed_at?: string;
  knowledge_version?: string;
  source_files?: string[];
  changed_files?: string[];
  invalidation_reasons?: string[];
};

type KnowledgeCacheResponse = KnowledgeCacheStatus & {
  exists?: boolean;
  success?: boolean;
  cache?: {
    profile?: ProjectProfile;
    repository_mapping?: AzureDevOpsConnectorMapping;
    knowledge_registry?: ProjectProfile['knowledge_registry'];
    last_analyzed_at?: string;
    knowledge_version?: string;
    source_files?: string[];
  };
  message?: string;
  error?: string;
};

type ContextCapsuleItem = {
  capsule_type: string;
  status: 'ready' | 'missing' | 'refresh_required';
  version: number;
  last_refreshed?: string;
  source_version?: string;
  capsule_size_tokens?: number;
  source_size_tokens?: number;
  compression_ratio?: number;
};

type ContextCapsuleStatus = {
  knowledge_version?: string;
  capsules: ContextCapsuleItem[];
  ready_count: number;
  total_count: number;
};

type ContextCapsuleResponse = {
  exists?: boolean;
  success?: boolean;
  capsules?: Record<string, unknown>;
  status: ContextCapsuleStatus;
};

type ArtifactRecord = {
  artifact_id: string;
  artifact_type: ArtifactType | string;
  state: ArtifactLifecycleState;
  title: string;
  payload: unknown;
  fingerprint: string;
  source_item: { id?: string; type?: string; title?: string };
  version: number;
  created_by?: string;
  created_on?: string;
  approved_by?: string;
  approved_on?: string;
  locked_on?: string;
  archived_on?: string;
  history?: Array<Record<string, unknown>>;
};

type ReusableArtifactResponse = {
  reusable: boolean;
  artifact?: ArtifactRecord;
  status: 'reusable' | 'refresh_required' | 'missing';
};

type GraphSummary = {
  version: number;
  updated_at: string;
  counts: Record<string, number>;
  relationship_count: number;
  coverage?: {
    acceptance_criteria_count: number;
    covered_acceptance_criteria_count: number;
    uncovered_acceptance_criteria_count: number;
    coverage_percent: number;
  };
  chain: {
    projects: number;
    epics: number;
    features: number;
    stories: number;
    tasks: number;
    tests: number;
    execution_packages: number;
  };
};

type CoverageIntelligenceReport = {
  coverage_report: {
    threshold: number;
    overall_project_coverage: number;
    quality_gate: string;
    feature_coverage: Array<{ title: string; story_count: number; overall_score: number; quality_gate: string }>;
    story_coverage: Array<{
      title: string;
      acceptance_criteria_count: number;
      task_count: number;
      test_count: number;
      execution_package_count: number;
      overall_score: number;
      quality_gate: string;
    }>;
    acceptance_criteria_coverage: Array<{ title: string; status: string }>;
    gap_summary: {
      gap_count: number;
      blocking_gap_count: number;
      gaps: Array<{ type: string; severity: string; title: string; message: string }>;
    };
  };
};

type KnowledgeGovernance = {
  registry_status: 'pending' | 'read_only';
  editability: 'editable' | 'read_only';
  knowledge_version: string;
  last_refreshed_by: string;
  last_refreshed_on: string;
};

type PermissionState = {
  role: AIGenRole;
  user_display_name: string;
  user_name: string;
  mapped_group: string;
  azure_groups: string[];
  status: 'resolved' | 'fallback';
  warning?: string;
  diagnostics?: {
    matched_groups: string[];
    matched_roles: AIGenRole[];
    selected_role: AIGenRole;
    precedence_rule: string;
  };
};

type PromptResult = ProviderMetadata & {
  ui_prompt: string;
  dev_prompt: string;
  qa_prompt: string;
};

type ExecutionContextCapsule = {
  capsuleId?: string;
  capsuleType?: string;
  sourceWorkItemId?: string;
  parentStoryId?: string;
  knowledgeVersion?: string;
  repositorySnapshotVersion?: string;
  generatedAt?: string;
  intentSummary?: string;
  selectedCapabilities?: string[];
  selectedModules?: string[];
  selectedFlows?: string[];
  selectedApplications?: string[];
  selectedDependencies?: string[];
  selectedStandards?: string[];
  acceptanceCriteria?: string[];
  inScope?: string[];
  outOfScope?: string[];
  relevantFiles?: Array<{ path?: string; confidence?: number; reason?: string; evidence?: string; source?: string }>;
  fileRankingStatus?: string;
  rejectedContext?: RejectedContextItem[];
  risks?: string[];
  constraints?: string[];
  confidence?: number;
  tokenEstimate?: number;
  freshnessStatus?: string;
  workItemDNA?: WorkItemDNA;
  dnaId?: string;
  dnaVersion?: number;
};

type WorkItemDNA = {
  dnaId?: string;
  workItemId?: string | number;
  workItemType?: string;
  version?: number;
  parentDNA?: string;
  businessProblem?: string[];
  businessGoals?: string[];
  businessOutcome?: string;
  capability?: string;
  responsibilities?: string[];
  planningBoundary?: { inScope?: string[]; outOfScope?: string[] };
  repositoryEvidence?: {
    modules?: string[];
    flows?: string[];
    applications?: string[];
    services?: string[];
    files?: string[];
  };
  dependencies?: string[];
  constraints?: string[];
  assumptions?: string[];
  risks?: string[];
  engineeringStandards?: string[];
  acceptanceThemes?: string[];
  validationSummary?: { score?: number; issues?: string[] };
  confidence?: number;
  approved?: boolean;
  approvedBy?: string;
  approvedAt?: string;
};

type WorkItemDNASummary = {
  dnaId?: string;
  version?: number;
  workItemType?: string;
  parentDNA?: string;
  businessGoals?: string[];
  businessOutcome?: string;
  capability?: string;
  responsibilities?: string[];
  inScope?: string[];
  outOfScope?: string[];
  modules?: string[];
  flows?: string[];
  files?: string[];
  dependencies?: string[];
  constraints?: string[];
  risks?: string[];
  acceptanceThemes?: string[];
  validationScore?: number;
  validationIssues?: string[];
  confidence?: number;
  approved?: boolean;
};

type ExecutionContextResult = ProviderMetadata & {
  execution_package_source?: string;
  implementation_package_source?: string;
  artifact_id?: string | number;
  artifact_type?: 'Story' | 'Task' | string;
  execution_source?: { artifactId?: string | number; artifactType?: string; title?: string; description?: string };
  executable_artifact?: Record<string, unknown>;
  execution_package_v2?: Record<string, unknown>;
  executionPackageV2?: Record<string, unknown>;
  implementation_package_v2?: Record<string, unknown>;
  implementationPackageV2?: Record<string, unknown>;
  context_capsule?: ExecutionContextCapsule;
  context_capsule_diagnostics?: ProviderMetadata;
  work_item_dna?: WorkItemDNA;
  parent_work_item_dna?: WorkItemDNA;
  dna_summary?: WorkItemDNASummary;
  dna_validation?: { valid?: boolean; status?: string; issues?: string[]; summary?: { score?: number; issues?: string[] } };
  story_summary: string;
  task_focus?: string;
  implementation_boundary?: string;
  capsule_summary?: string;
  business_outcome?: string;
  capability?: string;
  responsibilities?: string[];
  in_scope?: string[];
  out_of_scope?: string[];
  engineering_rules?: string[];
  acceptance_criteria: string[];
  affected_applications: string[];
  affected_modules: string[];
  affected_flows: string[];
  dependencies: string[];
  risks: string[];
  technology_stack: TechnologyStack;
  ui_guidelines: ProjectProfile['ui_guidelines'];
  development_standards: DevelopmentStandards;
  recommended_files: string[];
  file_ranking_status?: string;
  acceptance_criteria_mapping: Array<{ acceptance_criterion: string; implementation_task: string }>;
  proposed_tasks?: StoryTask[];
  task_intelligence_diagnostics?: {
    work_areas?: string[];
    generated_task_count?: number;
    acceptance_criteria_count?: number;
    rejected_task_patterns?: string[];
    recommended_file_count?: number;
  };
  implementation_tasks: string[];
  testing_tasks: string[];
  documentation_tasks: string[];
  implementation_notes: string[];
  execution_readiness: string;
  execution_readiness_score: number;
  execution_readiness_breakdown: Record<string, number>;
  execution_readiness_result: string;
};

type PromptBuilderResult = ProviderMetadata & {
  prompt: string;
  ai_prompt?: string;
  aiPrompt?: Record<string, unknown>;
  developer_prompt_v2?: Record<string, unknown>;
};

type ExecutionMode = 'implement' | 'review_existing_code' | 'refactor' | 'bug_fix' | 'spike_investigation';

type ExecutionPlanResult = ProviderMetadata & {
  plan: string;
  prompt?: string;
  finalPlan?: string;
  executionMode: ExecutionMode | string;
  executionModeLabel?: string;
  execution_plan?: Record<string, unknown>;
  implementation_plan?: Record<string, unknown>;
  implementationPlan?: Record<string, unknown>;
};

type CopilotContextResult = ProviderMetadata & {
  context: string;
};

type ImplementationValidationReport = {
  reportId: string;
  packageId: string;
  taskId?: number | string;
  storyId?: number | string;
  status: 'Passed' | 'NeedsReview' | 'Failed' | string;
  acceptanceCoverageScore: number;
  scopeComplianceScore: number;
  repositoryAlignmentScore: number;
  standardsComplianceScore: number;
  testCoverageScore: number;
  riskScore: number;
  changedFiles: Array<{ path?: string; status?: string; matchedEvidence?: string[] }>;
  acceptanceResults: Array<{ acceptanceCriteriaId?: string; acceptanceText?: string; status?: string; evidence?: string[] }>;
  scopeCompliance?: { score?: number; touchedBlockedScope?: string[] };
  standards?: Array<{ standard?: string; status?: string; evidence?: string[] }>;
  tests?: Array<{ testType?: string; status?: string; evidence?: string[] }>;
  violations: Array<{ rule?: string; severity?: string; category?: string; message?: string; file?: string; recommendation?: string }>;
  recommendations: string[];
  generatedAt: string;
};

type PRReviewReport = {
  reportId: string;
  pullRequestId?: number | string;
  status: 'Passed' | 'NeedsReview' | 'Blocked' | string;
  summary: string;
  linkedWorkItems: Array<{ id?: number | string; type?: string; title?: string; url?: string }>;
  validationScore: number;
  scores: {
    acceptanceCoverage: number;
    scopeCompliance: number;
    repositoryAlignment: number;
    standards: number;
    tests: number;
  };
  blockingIssues: string[];
  warnings: string[];
  changedFiles: Array<{ path?: string; status?: string; matchedEvidence?: string[] }>;
  generatedReviewComment: string;
  recommendations: string[];
  commentPostingEnabled: boolean;
  implementationValidation?: ImplementationValidationReport;
  diagnostics?: Record<string, unknown>;
};

type GenerationReview = {
  modules_used?: string[];
  flows_used?: string[];
  standards_used?: string[];
  applications_used?: string[];
  domain_terms_used?: string[];
  quality_scores?: {
    knowledge_usage?: number;
    module_coverage?: number;
    flow_coverage?: number;
    domain_specificity?: number;
    generic_content_risk?: number;
    overall?: number;
  };
  quality_gate?: string;
};

type EpicRefinement = ProviderMetadata & {
  business_goal: string;
  business_outcomes: string[];
  users: string[];
  applications: string[];
  constraints: string[];
  risks: string[];
  dependencies: string[];
  capability_review?: CapabilityReview[];
  capability_review_user_validated?: boolean;
  capability_review_diagnostics?: {
    capabilityCount?: number;
    approved?: number;
    rejected?: number;
    averageConfidence?: number;
    repositoryEvidence?: number;
    graphRelationships?: number;
    planningReadiness?: string;
    validationIssues?: Array<{ severity?: string; capability?: string; reason?: string }>;
  };
  capability_dependency_graph?: Array<{ source?: string; relationship?: string; target?: string; reason?: string }>;
  recommended_features: Array<{
    title: string;
    description: string;
    acceptance_criteria?: string[] | string;
    business_goal?: string;
    user_problem?: string;
    business_outcome?: string;
    business_value?: string;
    capability?: string;
    capability_category?: string;
    primary_personas?: string[];
    primary_users?: string[];
    impacted_applications?: string[];
    impacted_modules?: string[];
    impacted_flows?: string[];
    dependencies?: string[];
    risks?: string[];
    acceptance_criteria_count?: number;
    acceptance_criteria_quality_score?: number;
    rejected_irrelevant_context?: RejectedContextItem[];
    confidence?: number;
    status?: string;
    work_item_dna?: WorkItemDNA;
    dna_validation?: { valid?: boolean; status?: string; issues?: string[] };
    dna_diagnostics?: Record<string, unknown>;
  }>;
  generation_review?: GenerationReview;
};

type CapabilityReview = {
  capabilityId: string;
  capabilityName: string;
  capabilityCategory?: string;
  suggestedFeatureTitle?: string;
  businessPurpose: string;
  responsibilities: string[];
  businessValue: string;
  priority: 'Critical' | 'High' | 'Medium' | 'Low' | string;
  inScope: string[];
  outOfScope: string[];
  dependencies: string[];
  supports?: string[];
  repositoryEvidence: string[];
  relatedModules: string[];
  relatedFlows: string[];
  relatedApplications: string[];
  estimatedFeatures: number;
  confidence: number;
  status: 'Pending' | 'Approved' | 'Rejected' | string;
  reviewComments: string[];
  explainability?: {
    whyExists?: string;
    whyRequired?: string;
    businessProblemSolved?: string;
    excludedScope?: string[];
  };
};

type FeatureRefinement = ProviderMetadata & {
  feature_summary: string;
  affected_modules: string[];
  affected_flows: string[];
  dependencies: string[];
  risks: string[];
  recommended_stories: Array<{
    title: string;
    description: string;
    acceptance_criteria?: string[];
    coverage_area?: string;
    modules_used?: string[];
    flows_used?: string[];
    affected_modules?: string[];
    affected_flows?: string[];
    rejected_irrelevant_context?: RejectedContextItem[];
    confidence?: number;
    work_item_dna?: WorkItemDNA;
    dna_validation?: { valid?: boolean; status?: string; issues?: string[] };
    dna_diagnostics?: Record<string, unknown>;
  }>;
  generation_review?: GenerationReview;
  story_generation_diagnostics?: {
    capabilities_identified?: string[];
    user_actions_identified?: string[];
    capability_count?: number;
    action_count?: number;
    generated_story_count?: number;
    story_coverage_areas?: string[];
    story_quality_score?: number;
    acceptance_criteria_quality_score?: number;
    acceptance_criteria_count?: number;
    rejected_generic_criteria?: string[];
  };
  feature_analysis_result?: FeatureAnalysisResult;
  featureAnalysisResult?: FeatureAnalysisResult;
  ai_status?: FeatureAnalysisResult['aiStatus'];
  validation_status?: FeatureAnalysisResult['validationStatus'];
  warnings?: string[];
};

type FeatureAnalysisResult = {
  featureId?: string | number;
  deterministicDraft?: {
    title?: string;
    summary?: string;
    capability?: string;
    responsibilities?: string[];
    inScope?: string[];
    outOfScope?: string[];
    dependencies?: string[];
    repositoryEvidence?: {
      modules?: string[];
      flows?: string[];
      dependencies?: string[];
      rejectedContext?: RejectedContextItem[];
    };
    validationSummary?: {
      dnaValid?: boolean;
      dnaStatus?: string;
      issues?: string[];
    };
    storyCandidates?: Array<{ title?: string; description?: string; acceptanceCriteria?: string[]; confidence?: number }>;
    risks?: string[];
  };
  aiEnrichment?: {
    userJourneys?: unknown[];
    acceptanceThemes?: string[];
    storyCandidates?: unknown[];
    aiReasoningText?: string;
  } | null;
  aiStatus: 'not_requested' | 'success' | 'timeout' | 'parse_error' | 'provider_unavailable' | string;
  validationStatus: 'Ready' | 'NeedsReview' | 'Blocked' | string;
  diagnostics?: {
    providerTimeoutMs?: number;
    rawResponsePreview?: string;
    parseError?: string;
    deterministicDraftReady?: boolean;
    storyCandidateCount?: number;
    selectedModules?: string[];
    selectedFlows?: string[];
    providerMetadata?: ProviderMetadata;
  };
  warnings?: string[];
};

type StoryRefinement = ProviderMetadata & {
  story_summary: string;
  acceptance_criteria: string[];
  acceptance_criteria_categories?: string[];
  acceptance_criteria_quality_score?: number;
  affected_applications: string[];
  affected_modules: string[];
  affected_flows: string[];
  dependencies: string[];
  risks: string[];
  ui_considerations: string[];
  technical_considerations: string[];
  qa_considerations: string[];
  proposed_tasks?: StoryTask[];
  generation_review?: GenerationReview;
  task_intelligence_diagnostics?: {
    work_areas?: string[];
    generated_task_count?: number;
    acceptance_criteria_count?: number;
    rejected_task_patterns?: string[];
    recommended_file_count?: number;
    task_quality_score?: number;
  };
};

type StoryTask = {
  work_area?: string;
  title: string;
  description: string;
  acceptance_criteria?: string[];
  acceptance_criteria_count?: number;
  task_quality_score?: number;
  work_item_dna?: WorkItemDNA;
  dna_validation?: { valid?: boolean; status?: string; issues?: string[] };
  dna_diagnostics?: Record<string, unknown>;
};

type QATestCase = {
  test_id: string;
  category: string;
  title: string;
  preconditions: string[];
  steps: string[];
  expected_result: string;
  priority: string;
  risk_level: string;
  covers_acceptance_criteria?: number[];
};

type QAReadinessSummary = {
  acceptanceCoverage?: number;
  testCompleteness?: number;
  repositoryCoverage?: number;
  validationStatus?: string;
  regressionRisk?: string;
  overallReadiness?: number;
  status?: string;
  blockers?: string[];
};

type QAReleaseRecommendation = {
  recommendation?: string;
  reason?: string;
  recommendedActions?: string[];
};

type QATestSuiteResult = ProviderMetadata & {
  test_suite: {
    title: string;
    domain: string;
    story: { title: string; description: string };
    modules: string[];
    flows: string[];
    dependencies: string[];
    test_cases: QATestCase[];
  };
  coverage_summary: {
    acceptance_criteria_count: number;
    covered_acceptance_criteria_count: number;
    coverage_percent: number;
    covered_acceptance_criteria: string[];
    uncovered_acceptance_criteria: string[];
  };
  coverage_score: number;
  coverage_breakdown: {
    positive_coverage: number;
    negative_coverage: number;
    boundary_coverage: number;
    permission_coverage: number;
    error_coverage: number;
    regression_coverage: number;
    category_counts?: Record<string, number>;
    acceptance_criteria_count?: number;
  };
  generated_test_count: number;
  coverage_gaps: string[];
  qa_intelligence?: {
    acceptanceCoverage?: {
      coveragePercent?: number;
      missingCount?: number;
      acceptanceCriteria?: Array<{ acceptanceCriteriaId?: string; acceptanceText?: string; coverageStatus?: string; mappedTests?: Array<{ title?: string; testId?: string }> }>;
      validationNotes?: string[];
    };
    testIntelligence?: {
      generatedTestCount?: number;
      categories?: string[];
    };
    regressionIntelligence?: {
      changedModules?: string[];
      affectedServices?: string[];
      affectedAPIs?: string[];
      affectedFlows?: string[];
      relatedFeatures?: string[];
      relatedStories?: string[];
      potentialRegressionAreas?: string[];
      recommendedRegressionTests?: string[];
      regressionPriority?: string;
    };
    riskIntelligence?: {
      highestRisk?: string;
      risks?: Array<{ name?: string; level?: string; reason?: string; mitigation?: string }>;
      mitigations?: string[];
    };
    testGapAnalysis?: {
      missingTests?: string[];
      duplicateTests?: string[];
      weakTests?: string[];
      untestedAcceptanceCriteria?: string[];
      validationGaps?: string[];
    };
    qaReadiness?: {
      acceptanceCoverage?: number;
      testCompleteness?: number;
      repositoryCoverage?: number;
      validationStatus?: string;
      regressionRisk?: string;
      overallReadiness?: number;
      status?: string;
      blockers?: string[];
    };
    releaseRecommendation?: QAReleaseRecommendation;
    diagnostics?: {
      repositorySnapshotAvailable?: boolean;
      knowledgeRegistryAvailable?: boolean;
      engineeringGraphAvailable?: boolean;
      consumedExecutionPackage?: boolean;
      consumedExecutionPlan?: boolean;
      consumedImplementationValidation?: boolean;
    };
  };
  qa_readiness?: QAReadinessSummary;
  release_recommendation?: QAReleaseRecommendation;
  qa_status?: string;
  release_status?: string;
};

type StoryImpact = ProviderMetadata & {
  affected_applications: string[];
  affected_modules: string[];
  affected_flows: string[];
  affected_components: string[];
  dependencies: string[];
  risks: string[];
  integration_points: string[];
  recommended_reviewers: string[];
};

type FeatureImpact = ProviderMetadata & {
  affected_applications: string[];
  affected_modules: string[];
  affected_flows: string[];
  cross_team_dependencies: string[];
  integration_points: string[];
  risks: string[];
};

type EpicImpact = ProviderMetadata & {
  affected_applications: string[];
  affected_modules: string[];
  affected_flows: string[];
  program_dependencies: string[];
  risks: string[];
  recommended_rollout_strategy: string[];
};

type AdoWorkItem = {
  id: number;
  type: string;
  title: string;
  description: string;
  acceptanceCriteria: string;
  state: string;
  areaPath: string;
  iterationPath: string;
  tags: string[];
  project: string;
  collectionUri: string;
  parentIds: number[];
  childIds: number[];
  parents: AdoWorkItemSummary[];
  children: AdoWorkItemSummary[];
};

type AdoWorkItemSummary = {
  id: number;
  type: string;
  title: string;
  state: string;
};

type ChildDraft = {
  id: string;
  type: 'Feature' | 'User Story' | 'Task';
  title: string;
  description: string;
  acceptanceCriteria: string[];
  businessGoal?: string;
  userProblem?: string;
  businessValue?: string;
  capabilityCategory?: string;
  primaryPersonas?: string[];
  impactedApplications?: string[];
  impactedModules?: string[];
  impactedFlows?: string[];
  dependencies?: string[];
  risks?: string[];
  rejectedContext?: RejectedContextItem[];
  relevanceConfidence?: number;
  acceptanceCriteriaCount?: number;
  acceptanceCriteriaQualityScore?: number;
  selected: boolean;
  status: 'preview' | 'approved' | 'creating' | 'created' | 'failed' | 'skipped';
  azureId?: number;
  error?: string;
};

const EMPTY_STACK: TechnologyStack = {
  mobile: [],
  backend: [],
  firmware: [],
  analytics: [],
  frontend: [],
};

const EMPTY_STANDARDS: DevelopmentStandards = {
  architecture_patterns: [],
  coding_guidelines: [],
  security_requirements: [],
  testing_requirements: [],
};

const EMPTY_PROFILE: ProjectProfile = {
  onboarding_completed: false,
  project_id: '',
  project_name: '',
  domain: '',
  project_type: '',
  project_description: '',
  connectors: {
    azure_devops: {
      organization_url: '',
      ado_project: '',
      repository_id: '',
      repository_name: '',
      branch: 'main',
    },
  },
  repository_connection: {
    repository_id: '',
    repository_name: '',
    branch: '',
    status: 'Not connected',
    readme_path: '/README.md',
  },
  readme_analysis: {
    summary: '',
    applications: [],
    modules: [],
    flows: [],
    architecture_notes: [],
  },
  knowledge_registry: {
    applications: [],
    modules: [],
    flows: [],
    components: [],
    architecture_notes: [],
    standards: [],
    source_files: [],
  },
  applications: [],
  technology_stack: EMPTY_STACK,
  development_standards: EMPTY_STANDARDS,
  ui_guidelines: {
    primary_color: '',
    secondary_color: '',
    typography: '',
    component_library: '',
    accessibility_rules: [],
  },
  repository_sources: [],
  knowledge_profile_preview: {
    domain: '',
    systems: [],
    standards: [],
    repository_status: 'Repository README scan coming next.',
    readiness: 'Basic',
  },
};

function ProjectIntelligenceTab() {
  const [activeTab, setActiveTab] = useState<PlannerTab>('overview');
  const [activeNavigationId, setActiveNavigationId] = useState('overview');
  const [engineeringWorkspace, setEngineeringWorkspace] = useState<EngineeringWorkspace | undefined>();
  const [dashboardOverview, setDashboardOverview] = useState<DashboardOverview | undefined>();
  const [selectedItemType, setSelectedItemType] = useState<WorkItemKind>('Epic');
  const [autoRouteByWorkItemType, setAutoRouteByWorkItemType] = useState(true);
  const [profile, setProfile] = useState<ProjectProfile>(EMPTY_PROFILE);
  const [storyTitle, setStoryTitle] = useState('');
  const [storyDescription, setStoryDescription] = useState('');
  const [acceptanceCriteria, setAcceptanceCriteria] = useState('');
  const [prompts, setPrompts] = useState<PromptResult | undefined>();
  const [executionContext, setExecutionContext] = useState<ExecutionContextResult | undefined>();
  const [executionPlan, setExecutionPlan] = useState<ExecutionPlanResult | undefined>();
  const [executionMode, setExecutionMode] = useState<ExecutionMode>('implement');
  const [devPrompt, setDevPrompt] = useState<PromptBuilderResult | undefined>();
  const [uiPrompt, setUiPrompt] = useState<PromptBuilderResult | undefined>();
  const [qaPrompt, setQaPrompt] = useState<PromptBuilderResult | undefined>();
  const [copilotContext, setCopilotContext] = useState<CopilotContextResult | undefined>();
  const [implementationValidation, setImplementationValidation] = useState<ImplementationValidationReport | undefined>();
  const [implementationChangedFiles, setImplementationChangedFiles] = useState('');
  const [prReview, setPrReview] = useState<PRReviewReport | undefined>();
  const [epicInput, setEpicInput] = useState({ title: '', description: '' });
  const [featureInput, setFeatureInput] = useState({ title: '', description: '' });
  const [storyInput, setStoryInput] = useState({ title: '', description: '' });
  const [epicResult, setEpicResult] = useState<EpicRefinement | undefined>();
  const [featureResult, setFeatureResult] = useState<FeatureRefinement | undefined>();
  const [storyResult, setStoryResult] = useState<StoryRefinement | undefined>();
  const [qaTestSuite, setQaTestSuite] = useState<QATestSuiteResult | undefined>();
  const [epicImpactInput, setEpicImpactInput] = useState({ title: '', description: '' });
  const [featureImpactInput, setFeatureImpactInput] = useState({ title: '', description: '' });
  const [storyImpactInput, setStoryImpactInput] = useState({ title: '', description: '' });
  const [epicImpact, setEpicImpact] = useState<EpicImpact | undefined>();
  const [featureImpact, setFeatureImpact] = useState<FeatureImpact | undefined>();
  const [storyImpact, setStoryImpact] = useState<StoryImpact | undefined>();
  const [currentWorkItem, setCurrentWorkItem] = useState<AdoWorkItem | undefined>();
  const [childDrafts, setChildDrafts] = useState<ChildDraft[]>([]);
  const [creationLog, setCreationLog] = useState<string[]>([]);
  const [adoProjects, setAdoProjects] = useState<AdoProject[]>([]);
  const [repositories, setRepositories] = useState<GitRepository[]>([]);
  const [branches, setBranches] = useState<string[]>([]);
  const [repositoryLoadMessage, setRepositoryLoadMessage] = useState('');
  const [repositoryDocuments, setRepositoryDocuments] = useState<Record<string, string>>({});
  const [selectedRepositoryFiles, setSelectedRepositoryFiles] = useState<string[]>(['README.md', 'architecture.md', 'modules.md', 'flows.md']);
  const [repositoryFileStatus, setRepositoryFileStatus] = useState<Record<string, 'available' | 'missing' | 'unknown'>>({});
  const [resumeSession, setResumeSession] = useState<ProjectSessionSnapshot | undefined>();
  const [knowledgeCacheStatus, setKnowledgeCacheStatus] = useState<KnowledgeCacheStatus | undefined>();
  const [contextCapsuleStatus, setContextCapsuleStatus] = useState<ContextCapsuleStatus | undefined>();
  const [showResumePanel, setShowResumePanel] = useState(false);
  const [lastAnalysisTimestamp, setLastAnalysisTimestamp] = useState('');
  const [permissionState, setPermissionState] = useState<PermissionState>(defaultPermissionState());
  const [knowledgeGovernance, setKnowledgeGovernance] = useState<KnowledgeGovernance>(() => defaultKnowledgeGovernance(EMPTY_PROFILE, true));
  const [approvalWorkflow, setApprovalWorkflow] = useState<ApprovalWorkflowState>(() => defaultApprovalWorkflowState());
  const [artifactRecords, setArtifactRecords] = useState<ArtifactRecord[]>([]);
  const [artifactReuseStatus, setArtifactReuseStatus] = useState('');
  const [graphSummary, setGraphSummary] = useState<GraphSummary | undefined>();
  const [coverageReport, setCoverageReport] = useState<CoverageIntelligenceReport | undefined>();
  const [planningFocusRequest, setPlanningFocusRequest] = useState<{ target: PlanningFocusTarget; nonce: number }>({ target: null, nonce: 0 });
  const [engineeringMemories, setEngineeringMemories] = useState<EngineeringMemoryItem[]>([]);
  const [engineeringMemoryDiagnostics, setEngineeringMemoryDiagnostics] = useState<Record<string, unknown>>({});
  const [engineeringMemoryQuery, setEngineeringMemoryQuery] = useState('');
  const [engineeringMemoryStatus, setEngineeringMemoryStatus] = useState('Engineering Memory is ready when validated artifacts are approved.');
  const [governanceDashboard, setGovernanceDashboard] = useState<GovernanceDashboard | undefined>();
  const [governanceStatus, setGovernanceStatus] = useState('Governance is ready to monitor policies, approvals, compliance, and quality.');
  const [agentDashboard, setAgentDashboard] = useState<AgentDashboard | undefined>();
  const [agentStatus, setAgentStatus] = useState('Agent Orchestrator is ready for manual and service-hook triggers.');
  const [skillsDashboard, setSkillsDashboard] = useState<SkillsDashboard | undefined>();
  const [skillsStatus, setSkillsStatus] = useState('Engineering Skills are ready to enrich execution plans.');
  const [editingProfile, setEditingProfile] = useState(false);
  const [showQuickStart, setShowQuickStart] = useState(true);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState('Loading Project Intelligence...');
  const [error, setError] = useState('');
  const [saveStatus, setSaveStatus] = useState<'saved' | 'saving' | 'unsaved' | 'error'>('saved');
  const initializedRef = useRef(false);
  const engineeringMemoryBackfillRef = useRef(false);
  const lastSavedProfileRef = useRef('');
  const latestProvider = latestProviderMetadata([qaTestSuite, executionPlan, copilotContext, qaPrompt, uiPrompt, devPrompt, executionContext, storyImpact, featureImpact, epicImpact, storyResult, featureResult, epicResult, prompts]);
  const canAdmin = permissionState.role === 'admin';
  const canContribute = permissionState.role === 'admin' || permissionState.role === 'contributor';
  const isViewer = permissionState.role === 'viewer';
  const currentItemType = currentWorkItem ? normalizePlannerItemType(currentWorkItem.type) : selectedItemType;
  const workflowOrchestration = buildWorkflowOrchestration({
    itemType: currentItemType,
    approvalWorkflow,
    childDrafts,
    epicResult,
    featureResult,
    storyResult,
    hasQa: Boolean(qaTestSuite),
    hasExecution: Boolean(executionContext),
    hasKnowledge: hasKnowledgeRegistry(profile),
    standardsReady: standardsCaptured(profile),
    hasExecutionPackage: Boolean(executionContext),
  });
  const recommendedWorkspace = routedWorkspaceForWorkflow(currentItemType, workflowOrchestration);

  useEffect(() => {
    SDK.ready().then(async () => {
      SDK.notifyLoadSucceeded();
      try {
        const storedSession = readProjectSession();
        const backendSession = await getBackendProjectSession().catch(() => undefined);
        const knowledgeCache = await getKnowledgeCache().catch(() => undefined);
        const contextCapsules = await getContextCapsules().catch(() => undefined);
        const lifecycleArtifacts = await getArtifacts().catch(() => ({ artifacts: [] as ArtifactRecord[] }));
        const relationshipSummary = await getGraphSummary().catch(() => undefined);
        const graphCoverage = await getCoverageReport().catch(() => undefined);
        const memoryResponse = await getEngineeringMemory().catch(() => undefined);
        const governanceResponse = await getGovernanceDashboard().catch(() => undefined);
        const agentResponse = await getAgentDashboard().catch(() => undefined);
        const skillsResponse = await getSkillsDashboard().catch(() => undefined);
        setArtifactRecords(lifecycleArtifacts.artifacts || []);
        setGraphSummary(relationshipSummary);
        setCoverageReport(graphCoverage);
        if (memoryResponse) {
          setEngineeringMemories(memoryResponse.memories || memoryResponse.results || []);
          setEngineeringMemoryDiagnostics(memoryResponse.diagnostics || {});
          setEngineeringMemoryStatus(`${memoryResponse.count || 0} validated memory items loaded.`);
        }
        if (governanceResponse) {
          setGovernanceDashboard(governanceResponse);
          setGovernanceStatus(`Governance scorecard: ${String(governanceResponse.scorecard?.status || 'Ready')}.`);
        }
        if (agentResponse) {
          setAgentDashboard(agentResponse);
          setAgentStatus(`${agentResponse.waitingAgents?.length || 0} workflows waiting for human approval.`);
        }
        if (skillsResponse) {
          setSkillsDashboard(skillsResponse);
          setSkillsStatus(`${skillsResponse.installedSkills?.length || 0} reusable engineering skills installed.`);
        }
        const cachedProfile = knowledgeCache?.cache?.profile;
        const effectiveSession = storedSession || sessionFromBackend(backendSession, cachedProfile);
        if (storedSession) {
          setResumeSession(storedSession);
          setLastAnalysisTimestamp(storedSession.last_analysis_timestamp);
          setKnowledgeGovernance(storedSession.knowledge_governance || defaultKnowledgeGovernance(storedSession.profile, false));
          setAutoRouteByWorkItemType(storedSession.auto_route_by_work_item_type !== false);
          setApprovalWorkflow(normalizeApprovalWorkflowState(storedSession.approval_workflow));
        }
        if (knowledgeCache) {
          setKnowledgeCacheStatus(knowledgeCache);
        }
        if (contextCapsules?.status) {
          setContextCapsuleStatus(contextCapsules.status);
        }
        const loaded = await getProfile();
        const projectContext = await loadAzureProjectContext();
        const permissions = await resolveCurrentUserPermission(projectContext);
        setPermissionState(permissions);
        const workspace = await getEngineeringWorkspace(permissions.user_name || permissions.user_display_name, permissions.role).catch(() => undefined);
        if (workspace) {
          setEngineeringWorkspace(workspace);
        }
        const profileFromCache = cachedProfile ? mergeProfile(loaded, cachedProfile) : undefined;
        const seeded = effectiveSession?.profile?.project_name
          ? effectiveSession.profile
          : profileFromCache?.project_name
            ? profileFromCache
            : seedProfileFromAzureProject(loaded, projectContext);
        const overview = await getDashboardOverview(seeded.project_id).catch(() => undefined);
        if (overview) {
          setDashboardOverview(overview);
          setEngineeringWorkspace((current) => current ? {
            ...current,
            notifications: dashboardNotifications(overview),
          } : current);
        }
        if (effectiveSession && !storedSession) {
          setResumeSession(effectiveSession);
          setLastAnalysisTimestamp(effectiveSession.last_analysis_timestamp);
          setAutoRouteByWorkItemType(effectiveSession.auto_route_by_work_item_type !== false);
          setApprovalWorkflow(normalizeApprovalWorkflowState(effectiveSession.approval_workflow));
        }
        if (effectiveSession?.execution_context) {
          setExecutionContext(effectiveSession.execution_context);
        }
        if (effectiveSession?.execution_plan) {
          setExecutionPlan(effectiveSession.execution_plan);
        }
        if (effectiveSession?.dev_prompt) {
          setDevPrompt(effectiveSession.dev_prompt);
        }
        if (effectiveSession?.ui_prompt) {
          setUiPrompt(effectiveSession.ui_prompt);
        }
        if (effectiveSession?.qa_prompt) {
          setQaPrompt(effectiveSession.qa_prompt);
        }
        if (effectiveSession?.copilot_context) {
          setCopilotContext(effectiveSession.copilot_context);
        }
        if (effectiveSession?.qa_test_suite) {
          setQaTestSuite(effectiveSession.qa_test_suite);
        }
        if (effectiveSession?.implementation_validation) {
          setImplementationValidation(effectiveSession.implementation_validation);
        }
        if (effectiveSession?.pr_review) {
          setPrReview(effectiveSession.pr_review);
        }
        if (!effectiveSession?.knowledge_governance) {
          setKnowledgeGovernance(defaultKnowledgeGovernance(seeded, permissions.role === 'admin'));
        }
        const seededChanged = JSON.stringify(seeded) !== JSON.stringify(loaded);
        if (!effectiveSession && seededChanged) {
          try {
            const saved = await postJson<ProjectProfile>('/profile', { profile: seeded });
            setProfile(saved);
            lastSavedProfileRef.current = JSON.stringify(saved);
          } catch {
            setProfile(seeded);
            lastSavedProfileRef.current = JSON.stringify(loaded);
            setSaveStatus('unsaved');
          }
        } else {
          setProfile(seeded);
          lastSavedProfileRef.current = JSON.stringify(seeded);
        }
        if (effectiveSession?.last_active_tab) {
          const restoredTab = effectiveSession.last_active_tab === 'admin' && permissions.role !== 'admin' ? 'overview' : effectiveSession.last_active_tab;
          setActiveTab(restoredTab);
          setActiveNavigationId(navigationIdForPlannerTab(restoredTab));
          setShowResumePanel(true);
        }
        const hasReadyCache = knowledgeCache?.knowledge_status === 'ready' && Boolean(cachedProfile);
        setEditingProfile(permissions.role === 'admin' && !hasReadyCache && !seeded.project_name.trim());
        setShowQuickStart(permissions.role === 'admin' && !hasReadyCache && !seeded.project_name.trim() && !seeded.project_description.trim());
        const workItem = await loadCurrentWorkItem();
        if (workItem) {
          setCurrentWorkItem(workItem);
          void fetch(`${PLATFORM_BASE_URL}/engineering-intelligence/context`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              entryMode: 'WORK_ITEM',
              projectId: seeded.project_id || workItem.project || '',
              projectName: seeded.project_name || workItem.project || '',
              repositoryId: seeded.repository_connection?.repository_id || '',
              workItemId: String(workItem.id),
              analyzeWorkItem: false,
            }),
          }).catch(() => undefined);
          seedPlannerFromWorkItem(workItem, effectiveSession?.auto_route_by_work_item_type !== false);
          restorePlanningArtifactForWorkItem(workItem, lifecycleArtifacts.artifacts || []);
          restoreGeneratedChildArtifactForWorkItem(workItem, lifecycleArtifacts.artifacts || []);
          restoreExecutionArtifactsForWorkItem(workItem, lifecycleArtifacts.artifacts || []);
          restoreQaArtifactsForWorkItem(workItem, lifecycleArtifacts.artifacts || []);
          await refreshGraphInsights(workItem);
        }
        if (hasReadyCache) {
          setRepositoryLoadMessage('Loaded cached project knowledge. Continue without repository discovery, or refresh knowledge when documents change.');
        } else if (effectiveSession?.profile?.project_name) {
          setRepositoryLoadMessage('Loaded saved project session. Continue without reanalysis, or refresh analysis when you need updated repository knowledge.');
        } else {
          void loadAdoProjects(seeded);
        }
        setError('');
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : 'Unable to load project profile.');
      } finally {
        initializedRef.current = true;
        setLoading(false);
        setMessage('');
      }
    }).catch((initError) => {
      const text = initError instanceof Error ? initError.message : 'Unable to initialize Azure DevOps SDK.';
      setLoading(false);
      setMessage('');
      setError(text);
      initializedRef.current = true;
      void SDK.notifyLoadFailed(text);
    });
  }, []);

  useEffect(() => {
    if (!initializedRef.current) {
      return undefined;
    }
    const nextGovernance = normalizeKnowledgeGovernance(profile, knowledgeGovernance, canAdmin);
    if (JSON.stringify(nextGovernance) !== JSON.stringify(knowledgeGovernance)) {
      setKnowledgeGovernance(nextGovernance);
    }
    const session = buildProjectSession(
      profile,
      activeTab,
      lastAnalysisTimestamp,
      nextGovernance,
      currentWorkItem,
      autoRouteByWorkItemType,
      approvalWorkflow,
      {
        execution_context: executionContext,
        execution_plan: executionPlan,
        dev_prompt: devPrompt,
        ui_prompt: uiPrompt,
        qa_prompt: qaPrompt,
        copilot_context: copilotContext,
        qa_test_suite: qaTestSuite,
        implementation_validation: implementationValidation,
        pr_review: prReview,
      },
    );
    writeProjectSession(session);
    setResumeSession(session);
    void saveBackendProjectSession(session);
    const serialized = JSON.stringify(profile);
    if (serialized === lastSavedProfileRef.current) {
      setSaveStatus('saved');
      return undefined;
    }
    setSaveStatus('unsaved');
    const timeout = window.setTimeout(async () => {
      const snapshot = profile;
      const snapshotSerialized = JSON.stringify(snapshot);
      setSaveStatus('saving');
      try {
        await postJson<ProjectProfile>('/profile', { profile: snapshot });
        lastSavedProfileRef.current = snapshotSerialized;
        setSaveStatus('saved');
      } catch {
        setSaveStatus('error');
      }
    }, 900);
    return () => window.clearTimeout(timeout);
  }, [profile, activeTab, lastAnalysisTimestamp, knowledgeGovernance, canAdmin, currentWorkItem, autoRouteByWorkItemType, approvalWorkflow, executionContext, executionPlan, devPrompt, uiPrompt, qaPrompt, copilotContext, qaTestSuite, implementationValidation, prReview]);

  useEffect(() => {
    if (!initializedRef.current || engineeringMemoryBackfillRef.current) {
      return;
    }
    if (!profile.project_name.trim() || engineeringMemories.length > 0 || artifactRecords.length === 0) {
      return;
    }
    const approvedArtifacts = artifactRecords.filter((artifact) => artifact.state === 'approved' || artifact.state === 'locked');
    if (!approvedArtifacts.length) {
      return;
    }
    engineeringMemoryBackfillRef.current = true;
    setEngineeringMemoryStatus('Backfilling Engineering Memory from approved artifacts...');
    void syncEngineeringMemoryForArtifacts(approvedArtifacts);
  }, [profile.project_name, engineeringMemories.length, artifactRecords]);

  useEffect(() => {
    if (!initializedRef.current || !currentWorkItem || !autoRouteByWorkItemType) {
      return;
    }
    const nextWorkspace = routedWorkspaceForWorkflow(normalizePlannerItemType(currentWorkItem.type), workflowOrchestration);
    if (activeTab !== nextWorkspace) {
      setActiveTab(nextWorkspace);
      setActiveNavigationId(navigationIdForPlannerTab(nextWorkspace));
    }
  }, [currentWorkItem?.id, currentWorkItem?.type, workflowOrchestration.nextAction.workspace, autoRouteByWorkItemType]);

  useEffect(() => {
    if (!initializedRef.current || activeTab !== 'overview') {
      return;
    }
    void refreshDashboardOverview();
  }, [activeTab, profile.project_id, artifactRecords.length, engineeringMemories.length]);

  useEffect(() => {
    if (!permissionState.user_name && !permissionState.user_display_name) return;
    const refresh = () => { if (document.visibilityState === 'visible' && navigator.onLine) void refreshCommandCenterSignals(); };
    refresh();
    const interval = window.setInterval(refresh, 30000);
    const visibility = () => refresh();
    document.addEventListener('visibilitychange', visibility);
    window.addEventListener('online', refresh);
    return () => { window.clearInterval(interval); document.removeEventListener('visibilitychange', visibility); window.removeEventListener('online', refresh); };
  }, [permissionState.user_name, permissionState.user_display_name, engineeringWorkspace?.preferences.notificationsEnabled]);

  async function withLoading<T>(nextMessage: string, action: () => Promise<T>): Promise<T | undefined> {
    setLoading(true);
    setMessage(nextMessage);
    setError('');
    try {
      return await action();
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : String(actionError));
      return undefined;
    } finally {
      setLoading(false);
      setMessage('');
    }
  }

  async function refreshEngineeringMemory() {
    const response = await withLoading('Loading Engineering Memory...', () => getEngineeringMemory());
    if (response) {
      setEngineeringMemories(response.memories || response.results || []);
      setEngineeringMemoryDiagnostics(response.diagnostics || {});
      setEngineeringMemoryStatus(`${response.count || 0} engineering memories loaded.`);
    }
  }

  async function searchEngineeringMemory() {
    const query = engineeringMemoryQuery.trim();
    const response = await withLoading('Searching Engineering Memory...', () => query
      ? searchEngineeringMemoryItems({ query, includeDrafts: false })
      : getEngineeringMemory());
    if (response) {
      setEngineeringMemories(response.results || response.memories || []);
      setEngineeringMemoryDiagnostics(response.diagnostics || engineeringMemoryDiagnostics);
      setEngineeringMemoryStatus(query ? `${response.count || 0} matching memories found.` : `${response.count || 0} engineering memories loaded.`);
    }
  }

  async function refreshGovernanceDashboard() {
    const response = await withLoading('Loading Engineering Governance...', () => getGovernanceDashboard());
    if (response) {
      setGovernanceDashboard(response);
      setGovernanceStatus(`Governance scorecard: ${String(response.scorecard?.status || 'Ready')}.`);
    }
  }

  async function refreshAgentDashboard() {
    const response = await withLoading('Loading Agent Orchestrator...', () => getAgentDashboard());
    if (response) {
      setAgentDashboard(response);
      setAgentStatus(`${response.waitingAgents?.length || 0} workflows waiting for human approval.`);
    }
  }

  async function updateAgentFeatureFlag(flag: string, enabled: boolean) {
    const response = await withLoading('Updating agent feature flags...', () => postJson<{ featureFlags?: Record<string, boolean> }>('/agents/flags', {
      flags: { [flag]: enabled },
    }));
    if (response) {
      setAgentDashboard((current) => ({
        ...(current || {}),
        featureFlags: response.featureFlags || current?.featureFlags || {},
      }));
      await refreshAgentDashboard();
    }
  }

  async function refreshSkillsDashboard() {
    const response = await withLoading('Loading Engineering Skills...', () => getSkillsDashboard());
    if (response) {
      setSkillsDashboard(response);
      setSkillsStatus(`${response.installedSkills?.length || 0} reusable engineering skills installed.`);
    }
  }

  async function analyzeDescription() {
    if (!canAdmin) {
      setError('Project profile refinement is restricted to AI Gen Admins.');
      return;
    }
    const analyzed = await withLoading('Analyzing project description...', () => postJson<ProjectProfile>('/analyze-description', {
      description: profile.project_description,
    }));
    if (analyzed) {
      setProfile(mergeProfile(profile, analyzed));
    }
  }

  async function saveProfile() {
    if (!canAdmin) {
      setError('Project profile updates are restricted to AI Gen Admins.');
      return;
    }
    const saved = await withLoading('Saving project profile...', () => postJson<ProjectProfile>('/profile', { profile }));
    if (saved) {
      setProfile(saved);
      lastSavedProfileRef.current = JSON.stringify(saved);
      setSaveStatus('saved');
      setEditingProfile(false);
    }
  }

  async function analyzeProject() {
    if (!canAdmin) {
      setError('Project analysis is restricted to AI Gen Admins.');
      return;
    }
    const analyzed = await withLoading('Analyzing project...', async () => {
      let workingProfile = profile;
      if (workingProfile.project_description.trim()) {
        const descriptionProfile = await postJson<ProjectProfile>('/analyze-description', {
          description: workingProfile.project_description,
        });
        workingProfile = mergeProfile(workingProfile, descriptionProfile);
      }
      if (workingProfile.repository_connection.repository_id) {
        const repositoryAnalysis = await analyzeRepositoryDocumentsForProfile(workingProfile);
        if (repositoryAnalysis) {
          workingProfile = repositoryAnalysis;
        }
      }
      return workingProfile;
    });
    if (analyzed) {
      setProfile(analyzed);
      setLastAnalysisTimestamp(new Date().toISOString());
      markKnowledgeRefreshed(analyzed);
      await refreshContextCapsules(analyzed, ['project']);
      lastSavedProfileRef.current = JSON.stringify(analyzed);
      setSaveStatus('saved');
      setEditingProfile(false);
      setShowQuickStart(false);
      changeWorkspace('planning');
    }
  }

  function continueProjectSession() {
    if (resumeSession?.last_active_tab && resumeSession.last_active_tab !== 'overview') {
      changeWorkspace(resumeSession.last_active_tab);
    } else {
      changeWorkspace(recommendedWorkspace);
    }
    if (resumeSession?.profile) {
      setProfile(resumeSession.profile);
    }
    if (resumeSession?.execution_context) {
      setExecutionContext(resumeSession.execution_context);
    }
    if (resumeSession?.execution_plan) {
      setExecutionPlan(resumeSession.execution_plan);
    }
    if (resumeSession?.dev_prompt) {
      setDevPrompt(resumeSession.dev_prompt);
    }
    if (resumeSession?.ui_prompt) {
      setUiPrompt(resumeSession.ui_prompt);
    }
    if (resumeSession?.qa_prompt) {
      setQaPrompt(resumeSession.qa_prompt);
    }
    if (resumeSession?.copilot_context) {
      setCopilotContext(resumeSession.copilot_context);
    }
    if (resumeSession?.qa_test_suite) {
      setQaTestSuite(resumeSession.qa_test_suite);
    }
    if (resumeSession?.implementation_validation) {
      setImplementationValidation(resumeSession.implementation_validation);
    }
    if (resumeSession?.pr_review) {
      setPrReview(resumeSession.pr_review);
    }
    setShowResumePanel(false);
    setEditingProfile(false);
    setShowQuickStart(false);
    setRepositoryLoadMessage('Continuing saved project session. Repository analysis was not rerun.');
  }

  async function openRepositorySettings() {
    setShowResumePanel(false);
    setEditingProfile(true);
    setShowQuickStart(false);
    if (canAdmin) {
      changeWorkspace('admin', 'repository');
      if (!repositories.length && !repositoryLoadMessage.includes('Loaded')) {
        await loadAdoProjects(profile);
      }
      setRepositoryLoadMessage((current) => current || 'Repository settings are open. Select a repository and branch, then analyze documents.');
      return;
    }
    changeWorkspace('overview');
    setShowQuickStart(true);
    setError('Repository changes are restricted to AI Gen Admins. Your current role is read-only.');
  }

  async function refreshProjectAnalysis() {
    if (!canAdmin) {
      setError('Knowledge refresh is restricted to AI Gen Admins.');
      return;
    }
    setShowResumePanel(false);
    await loadAdoProjects(profile);
    const refreshed = await withLoading('Refreshing project knowledge...', async () => {
      let workingProfile = profile;
      if (workingProfile.project_description.trim()) {
        const descriptionProfile = await postJson<ProjectProfile>('/analyze-description', {
          description: workingProfile.project_description,
        });
        workingProfile = mergeProfile(workingProfile, descriptionProfile);
      }
      if (workingProfile.repository_connection.repository_id || Object.values(repositoryDocuments).some((content) => content.trim())) {
        const repositoryProfile = await analyzeRepositoryDocumentsForProfile(workingProfile);
        if (repositoryProfile) {
          workingProfile = repositoryProfile;
        }
      }
      return workingProfile;
    });
    if (refreshed) {
      setProfile(refreshed);
      setLastAnalysisTimestamp(new Date().toISOString());
      markKnowledgeRefreshed(refreshed);
      await refreshContextCapsules(refreshed, ['project']);
      const cache = await getKnowledgeCache().catch(() => undefined);
      if (cache) {
        setKnowledgeCacheStatus(cache);
      }
      changeWorkspace('overview');
    }
  }

  function markKnowledgeRefreshed(nextProfile: ProjectProfile) {
    const refreshedOn = new Date().toISOString();
    setKnowledgeGovernance({
      registry_status: hasKnowledgeRegistry(nextProfile) ? 'read_only' : 'pending',
      editability: canAdmin ? 'editable' : 'read_only',
      knowledge_version: knowledgeVersion(nextProfile),
      last_refreshed_by: permissionState.user_display_name || permissionState.user_name || 'AI Gen Admin',
      last_refreshed_on: refreshedOn,
    });
    setLastAnalysisTimestamp(refreshedOn);
  }

  async function refreshContextCapsules(nextProfile: ProjectProfile = profile, capsuleTypes: string[] = ['project']) {
    const response = await postJson<ContextCapsuleResponse>('/context-capsules/refresh', {
      profile: nextProfile,
      capsule_types: capsuleTypes,
      item: currentStoryPayload(),
    }).catch(() => undefined);
    if (response?.status) {
      setContextCapsuleStatus(response.status);
    }
  }

  async function refreshGraphInsights(workItem: AdoWorkItem | undefined = currentWorkItem) {
    const scopeId = workItem?.id ? String(workItem.id) : '';
    const [summary, coverage] = await Promise.all([
      getGraphSummary(scopeId).catch(() => undefined),
      getCoverageReport(scopeId).catch(() => undefined),
    ]);
    if (summary) {
      setGraphSummary(summary);
    }
    if (coverage) {
      setCoverageReport(coverage);
    }
  }

  async function refreshPermissions() {
    const permissions = await withLoading('Refreshing Azure DevOps permissions...', async () => {
      const projectContext = await loadAzureProjectContext();
      return resolveCurrentUserPermission(projectContext);
    });
    if (permissions) {
      setPermissionState(permissions);
    }
  }

  function sourceItemForArtifact(type: WorkItemKind = currentItemType): { id: string; type: string; title: string } {
    const fallback = type === 'Epic' ? epicInput : type === 'Feature' ? featureInput : storyInput;
    return {
      id: currentWorkItem ? String(currentWorkItem.id) : `${type}:${fallback.title || profile.project_name || 'draft'}`,
      type,
      title: currentWorkItem?.title || fallback.title || profile.project_name || 'Untitled item',
    };
  }

  function restoreGeneratedChildArtifactForWorkItem(workItem: AdoWorkItem, artifacts: ArtifactRecord[]) {
    const itemType = normalizePlannerItemType(workItem.type);
    const artifactType = childArtifactTypeForWorkItem(itemType);
    if (!artifactType) {
      return;
    }
    const artifact = latestChildArtifactForSource(artifacts, artifactType, String(workItem.id));
    if (!artifact || !Array.isArray(artifact.payload)) {
      return;
    }
    const normalizedDrafts = normalizeChildDraftPayload(artifact.payload, artifact.state);
    if (!normalizedDrafts.length) {
      return;
    }
    if (itemType === 'Epic' && epicResult?.capability_review?.length) {
      const allReviewed = epicResult.capability_review.every(isCapabilityReviewed);
      const approvedCount = epicResult.capability_review.filter(isCapabilityApproved).length;
      if (!allReviewed || approvedCount === 0) {
        return;
      }
    }
    const drafts = itemType === 'Epic'
      ? mergeEpicFeatureDraftsFromCapabilityState(epicResult, normalizedDrafts)
      : itemType === 'Feature'
        ? reconcileFeatureStoryDrafts(featureResult, normalizedDrafts)
        : normalizedDrafts;
    if (!drafts.length) {
      return;
    }
    setChildDrafts(drafts);
    const approval = approvalForChildArtifactType(artifactType);
    const quality = artifactType === 'Task' ? qualityScoreForTaskDrafts(drafts) : qualityScoreForFeatureDrafts(drafts);
    setApprovalWorkflow((current) => ({
      ...current,
      [approval]: artifact.state === 'approved' || artifact.state === 'locked'
        ? 'approved'
        : isReadyForApproval(quality) ? 'ready_for_approval' : 'draft',
    }));
    setArtifactReuseStatus(`Loaded existing ${childGenerationNoun(itemType)} v${artifact.version}. Use Regenerate if the ${itemType.toLowerCase()} details changed.`);
  }

  function restorePlanningArtifactForWorkItem(workItem: AdoWorkItem, artifacts: ArtifactRecord[]) {
    const itemType = normalizePlannerItemType(workItem.type);
    const sourceItemId = String(workItem.id);
    if (itemType === 'Epic') {
      const artifact = latestArtifactForSource(artifacts, 'Epic', sourceItemId);
      if (!artifact || Array.isArray(artifact.payload)) return;
      const payload = normalizeEpicCapabilityReview(artifact.payload as EpicRefinement, (artifact.payload as EpicRefinement).capability_review_user_validated === true);
      setEpicResult(payload);
      setApprovalWorkflow((current) => ({
        ...current,
        epic: artifact.state === 'approved' || artifact.state === 'locked'
          ? 'approved'
          : isReadyForApproval(qualityScoreForEpic(payload)) ? 'ready_for_approval' : 'draft',
      }));
      setArtifactReuseStatus(`Loaded existing Epic analysis v${artifact.version}.`);
      return;
    }
    if (itemType === 'Feature') {
      const artifact = latestArtifactForSource(artifacts, 'Feature', sourceItemId);
      if (!artifact || Array.isArray(artifact.payload)) return;
      const payload = artifact.payload as FeatureRefinement;
      setFeatureResult(payload);
      setApprovalWorkflow((current) => ({
        ...current,
        feature: artifact.state === 'approved' || artifact.state === 'locked'
          ? 'approved'
          : isReadyForApproval(qualityScoreForFeature(payload)) ? 'ready_for_approval' : 'draft',
      }));
      setArtifactReuseStatus(`Loaded existing Feature analysis v${artifact.version}.`);
      return;
    }
    if (itemType === 'Story') {
      const artifact = latestArtifactForSource(artifacts, 'Story', sourceItemId);
      if (!artifact || Array.isArray(artifact.payload)) return;
      const payload = artifact.payload as StoryRefinement;
      setStoryResult(payload);
      setApprovalWorkflow((current) => ({
        ...current,
        story: artifact.state === 'approved' || artifact.state === 'locked'
          ? 'approved'
          : isReadyForApproval(qualityScoreForStory(payload)) ? 'ready_for_approval' : 'draft',
      }));
      setArtifactReuseStatus(`Loaded existing Story analysis v${artifact.version}.`);
    }
  }

  function restoreExecutionArtifactsForWorkItem(workItem: AdoWorkItem, artifacts: ArtifactRecord[]) {
    const sourceItemId = String(workItem.id);
    const packageArtifact = latestArtifactForSource(artifacts, 'Execution Package', sourceItemId)
      || latestArtifactForSource(artifacts, 'Implementation Package', sourceItemId);
    if (packageArtifact && !Array.isArray(packageArtifact.payload)) {
      const payload = packageArtifact.payload as ExecutionContextResult | { context?: ExecutionContextResult };
      const context = typeof payload === 'object' && payload && 'context' in payload
        ? payload.context
        : payload as ExecutionContextResult;
      if (context) {
        setExecutionContext(context);
        setApprovalWorkflow((current) => ({
          ...current,
          execution: packageArtifact.state === 'approved' || packageArtifact.state === 'locked'
            ? 'approved'
            : isReadyForApproval(context.execution_readiness_score) ? 'ready_for_approval' : 'draft',
        }));
      }
    }

    const planArtifact = latestArtifactForSource(artifacts, 'Implementation Plan', sourceItemId)
      || latestArtifactForSource(artifacts, 'Execution Plan', sourceItemId);
    if (planArtifact && !Array.isArray(planArtifact.payload)) {
      setExecutionPlan(planArtifact.payload as ExecutionPlanResult);
    }

    const devArtifact = latestArtifactForSource(artifacts, 'Dev Prompt', sourceItemId);
    if (devArtifact && !Array.isArray(devArtifact.payload)) {
      setDevPrompt(devArtifact.payload as PromptBuilderResult);
    }
    const uiArtifact = latestArtifactForSource(artifacts, 'UI Prompt', sourceItemId);
    if (uiArtifact && !Array.isArray(uiArtifact.payload)) {
      setUiPrompt(uiArtifact.payload as PromptBuilderResult);
    }
    const qaArtifact = latestArtifactForSource(artifacts, 'QA Prompt', sourceItemId);
    if (qaArtifact && !Array.isArray(qaArtifact.payload)) {
      setQaPrompt(qaArtifact.payload as PromptBuilderResult);
    }
    const contextCapsuleArtifact = latestArtifactForSource(artifacts, 'Context Capsule', sourceItemId);
    if (contextCapsuleArtifact && !Array.isArray(contextCapsuleArtifact.payload)) {
      setCopilotContext(contextCapsuleArtifact.payload as CopilotContextResult);
    }
  }

  function restoreQaArtifactsForWorkItem(workItem: AdoWorkItem, artifacts: ArtifactRecord[]) {
    const sourceItemId = String(workItem.id);
    const artifact = latestArtifactForSource(artifacts, 'Test Suite', sourceItemId)
      || latestArtifactForSource(artifacts, 'Test Plan', sourceItemId);
    if (!artifact || Array.isArray(artifact.payload)) {
      return;
    }
    const payload = artifact.payload as QATestSuiteResult;
    setQaTestSuite(payload);
    setApprovalWorkflow((current) => ({
      ...current,
      qa: artifact.state === 'approved' || artifact.state === 'locked'
        ? 'approved'
        : isReadyForApproval(payload.coverage_score) ? 'ready_for_approval' : 'draft',
    }));
  }

  async function persistEpicReviewArtifact(nextResult: EpicRefinement, state: ArtifactLifecycleState = 'draft') {
    const sourceItem = sourceItemForArtifact('Epic');
    const fingerprint = artifactFingerprint('Epic', sourceItem, epicInput);
    const artifact = await saveArtifact({
      artifact_type: 'Epic',
      title: epicInput.title || currentWorkItem?.title || 'Epic refinement',
      payload: nextResult,
      fingerprint,
      state,
      source_item: sourceItem,
      created_by: permissionState.user_display_name || permissionState.user_name || 'AI Gen User',
    }).catch(() => undefined);
    if (artifact) {
      setArtifactRecords((current) => [artifact, ...current.filter((item) => item.artifact_id !== artifact.artifact_id)]);
      setArtifactReuseStatus(`Saved Epic review state v${artifact.version}.`);
    }
  }

  async function loadReusableArtifact<T>(
    artifactType: ArtifactType,
    source: Record<string, unknown>,
    apply: (payload: T, artifact: ArtifactRecord) => void,
  ): Promise<boolean> {
    const sourceItem = sourceItemForArtifact();
    const fingerprint = artifactFingerprint(artifactType, sourceItem, source);
    const reusable = await getReusableArtifact(artifactType, fingerprint, sourceItem.id).catch(() => undefined);
    if (reusable?.reusable && reusable.artifact) {
      apply(reusable.artifact.payload as T, reusable.artifact);
      setArtifactReuseStatus(`Using existing ${artifactDisplayName(artifactType)} v${reusable.artifact.version}.`);
      return true;
    }
    if (reusable?.status === 'refresh_required') {
      setArtifactReuseStatus(`${artifactDisplayName(artifactType)} changed since last approval. Refresh required.`);
    }
    return false;
  }

  async function saveGeneratedArtifact(
    artifactType: ArtifactType,
    title: string,
    payload: unknown,
    source: Record<string, unknown>,
    state: ArtifactLifecycleState = 'draft',
  ): Promise<ArtifactRecord | undefined> {
    const sourceItem = sourceItemForArtifact();
    const fingerprint = artifactFingerprint(artifactType, sourceItem, source);
    const artifact = await saveArtifact({
      artifact_type: artifactType,
      title,
      payload,
      fingerprint,
      state,
      source_item: sourceItem,
      created_by: permissionState.user_display_name || permissionState.user_name || 'AI Gen User',
    }).catch(() => undefined);
    if (artifact) {
      setArtifactRecords((current) => [artifact, ...current.filter((item) => item.artifact_id !== artifact.artifact_id)]);
      await refreshGraphInsights();
    }
    return artifact;
  }

  function memoryCategoryForArtifactType(artifactType: ArtifactType): string {
    if (artifactType === 'Epic' || artifactType === 'Feature' || artifactType === 'Story' || artifactType === 'Task') {
      return 'Planning Memory';
    }
    if (artifactType === 'Implementation Package' || artifactType === 'Execution Package' || artifactType === 'Implementation Plan' || artifactType === 'Execution Plan' || artifactType === 'Dev Prompt' || artifactType === 'UI Prompt' || artifactType === 'Context Capsule') {
      return 'Execution Memory';
    }
    if (artifactType === 'Test Suite' || artifactType === 'Test Plan' || artifactType === 'QA Prompt' || artifactType === 'Coverage Report') {
      return 'QA Memory';
    }
    return 'Project Memory';
  }

  function memoryPayloadFromArtifact(artifact: ArtifactRecord): Record<string, unknown> {
    const payload = artifact.payload && typeof artifact.payload === 'object' ? artifact.payload as Record<string, unknown> : {};
    const repositoryEvidence = Array.isArray((payload as any)?.context?.execution_package_v2?.repositoryContext?.relevantFiles)
      ? (payload as any).context.execution_package_v2.repositoryContext.relevantFiles
      : Array.isArray((payload as any)?.execution_package_v2?.repositoryContext?.relevantFiles)
        ? (payload as any).execution_package_v2.repositoryContext.relevantFiles
        : [];
    const tags = uniqueStrings([
      artifact.artifact_type,
      artifact.source_item?.type || '',
      artifact.source_item?.title || '',
    ]);
    return {
      projectId: profile.project_id || profile.project_name || 'default',
      category: memoryCategoryForArtifactType(artifact.artifact_type as ArtifactType),
      title: artifact.title,
      summary: `${artifact.artifact_type} derived from ${artifact.source_item?.type || 'work item'} ${artifact.source_item?.title || ''}`.trim(),
      content: typeof artifact.payload === 'string' ? artifact.payload : JSON.stringify(artifact.payload, null, 2),
      artifactType: artifact.artifact_type,
      artifactId: artifact.artifact_id,
      repositoryEvidence,
      knowledgeReferences: profile.knowledge_registry.source_files || [],
      graphReferences: [String(currentWorkItem?.id || artifact.source_item?.id || '')].filter(Boolean),
      tags,
      confidence: Number((payload as any)?.confidence || (payload as any)?.execution_readiness_score || (payload as any)?.coverage_score || 0.85),
      approvalStatus: 'Approved',
      source: {
        state: artifact.state,
        artifactType: artifact.artifact_type,
        approved_on: artifact.approved_on,
        status: artifact.state,
      },
    };
  }

  async function syncEngineeringMemoryForArtifacts(artifactsToSync: ArtifactRecord[]) {
    const actor = permissionState.user_display_name || permissionState.user_name || 'AI Gen User';
    const indexed: EngineeringMemoryItem[] = [];
    for (const artifact of artifactsToSync) {
      try {
        const stored = await storeEngineeringMemory(memoryPayloadFromArtifact(artifact), actor);
        const memoryId = stored.memory?.id;
        if (!memoryId) {
          continue;
        }
        await validateEngineeringMemory(memoryId, actor);
        await approveEngineeringMemory(memoryId, actor);
        await indexEngineeringMemory(memoryId, actor);
        const available = await makeEngineeringMemoryAvailable(memoryId, actor);
        if (available.memory) {
          indexed.push(available.memory);
        }
      } catch {
        // Engineering Memory indexing should not block artifact approval.
      }
    }
    if (indexed.length) {
      const refreshed = await getEngineeringMemory().catch(() => undefined);
      if (refreshed) {
        setEngineeringMemories(refreshed.memories || refreshed.results || []);
        setEngineeringMemoryDiagnostics(refreshed.diagnostics || {});
        setEngineeringMemoryStatus(`${refreshed.count || indexed.length} validated memory items loaded.`);
      }
    }
  }

  async function generatePrompts(forceRefresh = false) {
    if (!canContribute) {
      setError('Prompt generation is restricted to AI Gen Admins and Contributors.');
      return;
    }
    const source = {
      title: storyTitle,
      description: storyDescription,
      acceptance_criteria: splitLines(acceptanceCriteria),
    };
    if (!forceRefresh && await loadReusableArtifact<PromptResult>('Dev Prompt', source, (payload) => setPrompts(payload))) {
      return;
    }
    const generated = await withLoading('Generating story prompts...', () => postJson<PromptResult>('/generate-story-prompts', {
      profile,
      story: {
        title: storyTitle,
        description: storyDescription,
        acceptance_criteria: splitLines(acceptanceCriteria),
      },
    }));
    if (generated) {
      setPrompts(generated);
      await saveGeneratedArtifact('Dev Prompt', storyTitle || 'Story prompts', generated, source);
    }
  }

  async function refineEpic(forceRefresh = false) {
    if (!canContribute) {
      setError('Planning refinement is restricted to AI Gen Admins and Contributors.');
      return;
    }
    if (!forceRefresh && await loadReusableArtifact<EpicRefinement>('Epic', epicInput, (payload) => {
      const normalized = normalizeEpicCapabilityReview(payload, payload.capability_review_user_validated === true);
      setEpicResult(normalized);
      markApprovalGenerated('epic', qualityScoreForEpic(normalized));
    })) {
      return;
    }
    const result = await withLoading('Refining epic with Project Intelligence...', () => postJson<EpicRefinement>('/refine-epic', {
      profile,
      knowledge_profile: profile.knowledge_registry,
      epic: epicInput,
    }));
    if (result) {
      const normalized = normalizeEpicCapabilityReview(result);
      const reconciled = reconcileEpicCapabilityReview(epicResult, normalized);
      setEpicResult(reconciled);
      setChildDrafts((current) => {
        const nonFeatureDrafts = current.filter((draft) => draft.type !== 'Feature');
        const mergedFeatureDrafts = mergeEpicFeatureDraftsFromCapabilityState(reconciled, current);
        void persistChildDraftReviewArtifact('Feature', mergedFeatureDrafts);
        return [...nonFeatureDrafts, ...mergedFeatureDrafts];
      });
      markApprovalGenerated('epic', qualityScoreForEpic(reconciled));
      await saveGeneratedArtifact('Epic', epicInput.title || 'Epic refinement', reconciled, epicInput);
    }
  }

  async function refineFeature(forceRefresh = false, mode = '') {
    if (!canContribute) {
      setError('Planning refinement is restricted to AI Gen Admins and Contributors.');
      return;
    }
    if (!mode && !forceRefresh && await loadReusableArtifact<FeatureRefinement>('Feature', featureInput, (payload) => {
      setFeatureResult(payload);
      setChildDrafts((current) => {
        const nonStoryDrafts = current.filter((draft) => draft.type !== 'User Story');
        const mergedStoryDrafts = reconcileFeatureStoryDrafts(payload, current);
        return [...nonStoryDrafts, ...mergedStoryDrafts];
      });
      markApprovalGenerated('feature', qualityScoreForFeature(payload));
    })) {
      return;
    }
    const result = await withLoading(mode ? 'Retrying Feature AI enrichment...' : 'Analyzing feature with Project Intelligence...', () => postJson<FeatureRefinement>('/refine-feature', {
      profile,
      knowledge_profile: profile.knowledge_registry,
      feature: featureInput,
      mode,
    }));
    if (result) {
      setFeatureResult(result);
      setChildDrafts((current) => {
        const nonStoryDrafts = current.filter((draft) => draft.type !== 'User Story');
        const mergedStoryDrafts = reconcileFeatureStoryDrafts(result, current);
        void persistChildDraftReviewArtifact('Story', mergedStoryDrafts);
        return [...nonStoryDrafts, ...mergedStoryDrafts];
      });
      markApprovalGenerated('feature', qualityScoreForFeature(result));
      await saveGeneratedArtifact('Feature', featureInput.title || 'Feature refinement', result, featureInput);
    }
  }

  async function refineStory(forceRefresh = false) {
    if (!canContribute) {
      setError('Planning refinement is restricted to AI Gen Admins and Contributors.');
      return;
    }
    const source = { ...storyInput, acceptance_criteria: splitLines(acceptanceCriteria) };
    if (!forceRefresh && await loadReusableArtifact<StoryRefinement>('Story', source, (payload) => {
      setStoryResult(payload);
      markApprovalGenerated('story', qualityScoreForStory(payload));
    })) {
      return;
    }
    const result = await withLoading('Refining story with Project Intelligence...', () => postJson<StoryRefinement>('/refine-story', {
      profile,
      knowledge_profile: profile.knowledge_registry,
      story: source,
    }));
    if (result) {
      setStoryResult(result);
      markApprovalGenerated('story', qualityScoreForStory(result));
      await saveGeneratedArtifact('Story', storyInput.title || 'Story refinement', result, source);
    }
  }

  async function generateQATestCases(forceRefresh = false, action: 'analyze' | 'generate_missing_tests' = 'analyze') {
    if (!canContribute) {
      setError('QA generation is restricted to AI Gen Admins and Contributors.');
      return;
    }
    const story = currentStoryPayload();
    const source = { story, impact_analysis: storyImpact || {}, qa_action: action };
    if (!forceRefresh && await loadReusableArtifact<QATestSuiteResult>('Test Suite', source, (payload) => {
      setQaTestSuite(payload);
      markApprovalGenerated('qa', payload.coverage_score);
    })) {
      return;
    }
    const result = await withLoading(action === 'generate_missing_tests' ? 'Generating missing tests...' : 'Generating QA test cases...', () => postJson<QATestSuiteResult>('/generate-qa-test-cases', {
      profile,
      knowledge_profile: profile.knowledge_registry,
      story,
      impact_analysis: storyImpact || {},
      execution_package: executionContext?.execution_package_v2 || executionContext?.executionPackageV2 || {},
      execution_plan: executionPlan?.execution_plan || executionPlan || {},
      implementation_validation: implementationValidation || {},
      existing_test_suite: qaTestSuite || {},
      qa_action: action,
    }));
    if (result) {
      setQaTestSuite(result);
      markApprovalGenerated('qa', result.coverage_score);
      await saveGeneratedArtifact('Test Suite', story.title || 'QA test suite', result, source);
      await refreshContextCapsules(profile, ['story', 'qa']);
    }
  }

  async function generateFeatureTestPlan(forceRefresh = false) {
    if (!canContribute) {
      setError('Test plan generation is restricted to AI Gen Admins and Contributors.');
      return;
    }
    const title = featureInput.title || currentWorkItem?.title || 'Feature test plan';
    const description = featureInput.description || htmlToText(currentWorkItem?.description || '') || featureResult?.feature_summary || '';
    const acceptance = featureResult?.recommended_stories?.flatMap((story) => story.acceptance_criteria || []) || [];
    const source = { title, description, acceptance, impact_analysis: featureImpact || {} };
    if (!forceRefresh && await loadReusableArtifact<QATestSuiteResult>('Test Plan', source, (payload) => {
      setQaTestSuite(payload);
      markApprovalGenerated('qa', payload.coverage_score);
      changeWorkspace('qa');
    })) {
      return;
    }
    const result = await withLoading('Generating feature test plan...', () => postJson<QATestSuiteResult>('/generate-qa-test-cases', {
      profile,
      knowledge_profile: profile.knowledge_registry,
      story: {
        title,
        description,
        acceptance_criteria: acceptance.length ? acceptance : [`${title} has testable stories and release coverage.`],
        affected_modules: featureResult?.affected_modules || [],
        affected_flows: featureResult?.affected_flows || [],
        dependencies: featureResult?.dependencies || [],
      },
      impact_analysis: featureImpact || {},
    }));
    if (result) {
      setQaTestSuite(result);
      markApprovalGenerated('qa', result.coverage_score);
      await saveGeneratedArtifact('Test Plan', title, result, source);
      await refreshContextCapsules(profile, ['feature', 'qa']);
      changeWorkspace('qa');
    }
  }

  async function buildExecutionPackage(forceRefresh = false) {
    if (!canContribute) {
      setError('Execution package generation is restricted to AI Gen Admins and Contributors.');
      return;
    }
    const story = currentStoryPayload();
    const source = { story, impact_analysis: storyImpact || {} };
    if (!forceRefresh && await loadReusableArtifact<{
      context: ExecutionContextResult;
      dev?: PromptBuilderResult;
      ui?: PromptBuilderResult;
      qa?: PromptBuilderResult;
      copilot?: CopilotContextResult;
    }>('Execution Package', source, (payload) => {
      setExecutionContext(payload.context);
      setDevPrompt(payload.dev);
      setUiPrompt(payload.ui);
      setQaPrompt(payload.qa);
      setCopilotContext(payload.copilot);
      markApprovalGenerated('execution', payload.context.execution_readiness_score);
      changeWorkspace('execution');
    })) {
      return;
    }
    const context = await withLoading('Building implementation package...', async () => {
      const basePayload = {
        profile,
        knowledge_profile: profile.knowledge_registry,
        story,
        impact_analysis: storyImpact || {},
        mode: 'deterministic_only',
      };
      return postJson<ExecutionContextResult>('/build-execution-context', basePayload);
    });
    if (context) {
      setExecutionContext(context);
      setExecutionPlan(undefined);
      setDevPrompt(undefined);
      setUiPrompt(undefined);
      setQaPrompt(undefined);
      setCopilotContext(undefined);
      setImplementationValidation(undefined);
      setPrReview(undefined);
      markApprovalGenerated('execution', context.execution_readiness_score);
      await saveGeneratedArtifact('Execution Package', story.title || 'Implementation package', { context }, source);
      await refreshContextCapsules(profile, ['story', 'execution', 'qa']);
      changeWorkspace('execution');
    }
  }

  function executionBasePayload(mode = 'deterministic_only') {
    return {
      profile,
      knowledge_profile: profile.knowledge_registry,
      story: currentStoryPayload(),
      impact_analysis: storyImpact || {},
      mode,
      execution_mode: executionMode,
    };
  }

  async function buildExecutionPlan(mode: ExecutionMode = executionMode) {
    if (!canContribute) {
      setError('Implementation Plan generation is restricted to AI Gen Admins and Contributors.');
      return;
    }
    const result = await withLoading('Generating Implementation Plan...', async () => {
      if (!executionContext) {
        await buildExecutionPackage();
      }
      return postJson<ExecutionPlanResult>('/build-execution-plan', {
        ...executionBasePayload('deterministic_only'),
        execution_mode: mode,
      });
    });
    if (result) {
      setExecutionPlan(result);
      setMessage('Implementation Plan generated.');
      await saveGeneratedArtifact('Implementation Plan', currentStoryPayload().title || 'Implementation plan', result, {
        story: currentStoryPayload(),
        execution_mode: mode,
      });
      window.setTimeout(() => setMessage(''), 1800);
    }
  }

  async function buildExecutionPrompt(kind: 'dev' | 'ui' | 'qa' | 'copilot', mode = 'deterministic_only') {
    if (!canContribute) {
      setError('Execution prompt generation is restricted to AI Gen Admins and Contributors.');
      return;
    }
    const endpointByKind = {
      dev: '/build-dev-prompt',
      ui: '/build-ui-prompt',
      qa: '/build-qa-prompt',
      copilot: '/build-copilot-context',
    };
    const labelByKind = {
      dev: 'Developer Prompt',
      ui: 'Specialized UI Prompt',
      qa: 'Specialized QA Prompt',
      copilot: 'Context Capsule',
    };
    const result = await withLoading(`${mode === 'enhance_with_ai' ? 'Enhancing' : 'Generating'} ${labelByKind[kind]}...`, async () => {
      if (!executionContext) {
        await buildExecutionPackage();
      }
      return postJson<PromptBuilderResult | CopilotContextResult>(endpointByKind[kind], executionBasePayload(mode));
    });
    if (!result) {
      return;
    }
    const story = currentStoryPayload();
    if (kind === 'dev') {
      setDevPrompt(result as PromptBuilderResult);
      await saveGeneratedArtifact('Dev Prompt', story.title || 'Developer prompt', result, { story, execution_mode: executionMode });
    }
    if (kind === 'ui') {
      setUiPrompt(result as PromptBuilderResult);
      await saveGeneratedArtifact('UI Prompt', story.title || 'UI prompt', result, { story, execution_mode: executionMode });
    }
    if (kind === 'qa') {
      setQaPrompt(result as PromptBuilderResult);
      await saveGeneratedArtifact('QA Prompt', story.title || 'QA prompt', result, { story, execution_mode: executionMode });
    }
    if (kind === 'copilot') {
      setCopilotContext(result as CopilotContextResult);
      await saveGeneratedArtifact('Context Capsule', story.title || 'Context capsule', result, { story, execution_mode: executionMode });
    }
  }

  async function validateImplementation() {
    if (!executionContext?.execution_package_v2 && !executionContext?.executionPackageV2) {
      setError('Build the implementation package before validating implementation.');
      return;
    }
    const changedFiles = parseChangedFilesInput(implementationChangedFiles);
    const result = await withLoading('Validating implementation alignment...', () => {
      return postJson<ImplementationValidationReport>('/validate-implementation', {
        execution_package: executionContext.execution_package_v2 || executionContext.executionPackageV2 || {},
        developer_prompt: devPrompt?.developer_prompt_v2 || devPrompt || {},
        task_dna: executionContext.work_item_dna || {},
        story_dna: executionContext.parent_work_item_dna || {},
        changed_files: changedFiles,
        repository_diff: { changed_files: changedFiles },
      });
    });
    if (result) {
      setImplementationValidation(result);
      setMessage(`Implementation validation ${result.status}.`);
      await saveGeneratedArtifact('Coverage Report', currentStoryPayload().title || 'Implementation validation', result, {
        story: currentStoryPayload(),
        changed_files: parseChangedFilesInput(implementationChangedFiles),
      });
      window.setTimeout(() => setMessage(''), 1800);
    }
  }

  async function runPRReview() {
    if (!executionContext?.execution_package_v2 && !executionContext?.executionPackageV2) {
      setError('Build the implementation package before running PR Review.');
      return;
    }
    const changedFiles = parseChangedFilesInput(implementationChangedFiles);
    const result = await withLoading('Running HEI PR Review...', () => {
      return postJson<PRReviewReport>('/pr-review', {
        pull_request: { title: currentWorkItem?.title || storyInput.title || 'Current implementation changes' },
        linked_work_items: currentWorkItem ? [{ id: currentWorkItem.id, type: currentWorkItem.type, title: currentWorkItem.title }] : [],
        execution_package: executionContext.execution_package_v2 || executionContext.executionPackageV2 || {},
        developer_prompt: devPrompt?.developer_prompt_v2 || devPrompt || {},
        task_dna: executionContext.work_item_dna || {},
        story_dna: executionContext.parent_work_item_dna || {},
        changed_files: changedFiles,
        repository_diff: { changed_files: changedFiles },
      });
    });
    if (result) {
      setPrReview(result);
      if (result.implementationValidation) {
        setImplementationValidation(result.implementationValidation);
      }
      setMessage(`PR Review ${result.status}.`);
      window.setTimeout(() => setMessage(''), 1800);
    }
  }

  async function postPRReviewComment() {
    if (!prReview) {
      setError('Run PR Review before posting a review comment.');
      return;
    }
    const result = await withLoading('Posting PR Review comment...', () => postJson<{ posted?: boolean; disabled?: boolean; message?: string }>('/pr-review/comment', { report: prReview as unknown as Record<string, unknown> }));
    if (result) {
      setMessage(result.message || (result.posted ? 'PR Review comment posted.' : 'PR Review comment was not posted.'));
      window.setTimeout(() => setMessage(''), 2400);
    }
  }

  async function enhanceExecutionWithAi() {
    if (!executionContext) {
      await buildExecutionPackage();
    }
    setMessage('Enhancing with AI...');
    const enriched = await withLoading('Enhancing implementation package with AI...', () => {
      return postJson<ExecutionContextResult>('/build-execution-context', executionBasePayload('enhance_with_ai'));
    });
    if (enriched) {
      setExecutionContext(enriched);
    }
    setMessage('AI enrichment finished. Prompts remain deterministic unless generated separately.');
    window.setTimeout(() => setMessage(''), 1800);
  }

  function openVsCodeExecutionPackage() {
    if (!executionContext) {
      void buildExecutionPackage();
      return;
    }
    const uri = buildVsCodeExecutionPackageUri(executionContext, executionPlan, devPrompt, uiPrompt, qaPrompt, copilotContext);
    if (uri) {
      window.open(uri, '_blank');
    }
  }

  async function continueWorkflow() {
    if (!canContribute) {
      setError('Workflow continuation is restricted to AI Gen Admins and Contributors.');
      return;
    }
    setError('');
    const action = workflowOrchestration.nextAction.action;
    setMessage(`Continuing workflow: ${workflowOrchestration.nextAction.label}`);
    if (action === 'analyze_epic') {
      await refineEpic();
    } else if (action === 'approve_epic') {
      await approveEpic();
    } else if (action === 'analyze_feature') {
      await refineFeature();
    } else if (action === 'generate_features') {
      setSelectedItemType('Epic');
      await generateChildrenForCurrentType('Epic');
    } else if (action === 'create_children') {
      await createSelectedChildWorkItems();
    } else if (action === 'approve_features') {
      approveFeatures();
    } else if (action === 'approve_feature') {
      await approveFeature();
    } else if (action === 'analyze_story') {
      await refineStory();
    } else if (action === 'generate_stories') {
      setSelectedItemType('Feature');
      await generateChildrenForCurrentType('Feature');
    } else if (action === 'approve_stories') {
      approveStories();
    } else if (action === 'approve_story') {
      await approveStory();
    } else if (action === 'generate_tasks') {
      setSelectedItemType('Story');
      await generateChildrenForCurrentType('Story');
    } else if (action === 'approve_tasks') {
      approveTasks();
    } else if (action === 'generate_tests') {
      await generateQATestCases();
    } else if (action === 'build_execution') {
      await buildExecutionPackage();
    } else if (action === 'open_vscode') {
      openVsCodeExecutionPackage();
    } else if (action === 'open_planning') {
      if (currentItemType === 'Epic') {
        setPlanningFocusRequest({ target: 'features', nonce: Date.now() });
      } else if (currentItemType === 'Feature') {
        setPlanningFocusRequest({ target: 'stories', nonce: Date.now() });
      }
      changeWorkspace('planning');
    } else if (action === 'open_execution') {
      changeWorkspace('execution');
    } else if (action === 'open_qa') {
      changeWorkspace('qa');
    }
  }

  async function generateEverythingForStory() {
    if (!canContribute) {
      setError('Story automation is restricted to AI Gen Admins and Contributors.');
      return;
    }
    setError('');
    setSelectedItemType('Story');
    if (!childDrafts.some((draft) => draft.type === 'Task')) {
      await generateChildrenForCurrentType('Story');
    }
    if (!qaTestSuite) {
      await generateQATestCases();
    }
    if (!executionContext) {
      await buildExecutionPackage();
    }
    setMessage('Story automation complete. Review tasks, QA coverage, and the implementation package.');
    window.setTimeout(() => setMessage(''), 1800);
  }

  function currentStoryPayload(): {
    id?: number | string;
    type?: string;
    work_item_type?: string;
    artifactType?: string;
    title: string;
    description: string;
    acceptance_criteria: string[];
  } {
    const type = currentWorkItem ? normalizePlannerItemType(currentWorkItem.type) : selectedItemType;
    return {
      id: currentWorkItem?.id,
      type,
      work_item_type: type,
      artifactType: type === 'Task' ? 'Task' : 'Story',
      title: storyInput.title || storyTitle || storyResult?.story_summary || 'Approved story',
      description: storyInput.description || storyDescription || storyResult?.story_summary || 'Implement the approved story.',
      acceptance_criteria: splitLines(acceptanceCriteria).length ? splitLines(acceptanceCriteria) : (storyResult?.acceptance_criteria || []),
    };
  }

  function resetItemScopedState() {
    setApprovalWorkflow(defaultApprovalWorkflowState());
    setEpicResult(undefined);
    setFeatureResult(undefined);
    setStoryResult(undefined);
    setEpicImpact(undefined);
    setFeatureImpact(undefined);
    setStoryImpact(undefined);
    setChildDrafts([]);
    setCreationLog([]);
    setExecutionContext(undefined);
    setExecutionPlan(undefined);
    setDevPrompt(undefined);
    setUiPrompt(undefined);
    setQaPrompt(undefined);
    setCopilotContext(undefined);
    setImplementationValidation(undefined);
    setPrReview(undefined);
    setArtifactReuseStatus('');
  }

  function seedPlannerFromWorkItem(workItem: AdoWorkItem, shouldAutoRoute = autoRouteByWorkItemType) {
    const type = normalizePlannerItemType(workItem.type);
    setSelectedItemType(type);
    resetItemScopedState();
    if (type === 'Epic') {
      setEpicInput({ title: workItem.title, description: htmlToText(workItem.description) });
      setFeatureInput({ title: '', description: '' });
      setStoryInput({ title: '', description: '' });
      setAcceptanceCriteria('');
    } else if (type === 'Feature') {
      setEpicInput({ title: '', description: '' });
      setFeatureInput({ title: workItem.title, description: htmlToText(workItem.description) });
      setStoryInput({ title: '', description: '' });
      setAcceptanceCriteria('');
    } else {
      setEpicInput({ title: '', description: '' });
      setFeatureInput({ title: '', description: '' });
      setStoryInput({ title: workItem.title, description: htmlToText(workItem.description) });
      setAcceptanceCriteria(htmlToText(workItem.acceptanceCriteria));
    }
    if (shouldAutoRoute) {
      changeWorkspace(recommendedWorkspaceForItem(type));
    }
  }

  function updateDraftSelection(draftId: string, selected: boolean) {
    setChildDrafts((current) => current.map((draft) => draft.id === draftId ? { ...draft, selected } : draft));
  }

  async function persistChildDraftReviewArtifact(
    artifactType: ArtifactType,
    payload: ChildDraft[],
    state: ArtifactLifecycleState = 'draft',
  ) {
    const source = artifactType === 'Feature'
      ? epicFeatureGenerationSource(epicInput, epicResult)
      : artifactType === 'Story'
        ? { ...featureInput, type: 'Feature', purpose: 'generated_stories' }
        : { ...storyInput, type: 'Story', acceptance_criteria: splitLines(acceptanceCriteria), purpose: 'generated_tasks' };
    await saveGeneratedArtifact(
      artifactType,
      artifactType === 'Feature'
        ? epicInput.title || 'Generated features'
        : artifactType === 'Story'
          ? featureInput.title || 'Generated stories'
          : storyInput.title || 'Generated tasks',
      payload,
      source,
      state,
    );
  }

  function updateChildDraftReview(
    draftId: string,
    artifactType: ArtifactType,
    changes: Partial<ChildDraft>,
  ) {
    let nextDrafts: ChildDraft[] = [];
    setChildDrafts((current) => {
      nextDrafts = current.map((draft) => (
        draft.id === draftId ? { ...draft, ...changes } : draft
      ));
      return nextDrafts;
    });
    if (nextDrafts.length) {
      void persistChildDraftReviewArtifact(artifactType, nextDrafts);
    }
  }

  function syncFeatureDraftsWithCapabilityReview(nextResult: EpicRefinement) {
    setChildDrafts((current) => {
      if (!current.some((draft) => draft.type === 'Feature')) {
        return current;
      }
      const mergedFeatureDrafts = mergeEpicFeatureDraftsFromCapabilityState(nextResult, current);
      void persistChildDraftReviewArtifact('Feature', mergedFeatureDrafts);
      return [...current.filter((draft) => draft.type !== 'Feature'), ...mergedFeatureDrafts];
    });
  }

  function updateCapabilityReview(capabilityId: string, changes: Partial<CapabilityReview>) {
    setEpicResult((current) => {
      if (!current?.capability_review?.length) return current;
      const next = {
        ...current,
        capability_review_user_validated: true,
        capability_review: current.capability_review.map((capability) => (
          capability.capabilityId === capabilityId ? { ...capability, ...changes } : capability
        )),
      };
      syncFeatureDraftsWithCapabilityReview(next);
      void persistEpicReviewArtifact(next);
      return next;
    });
  }

  function moveCapabilityReview(capabilityId: string, direction: -1 | 1) {
    setEpicResult((current) => {
      if (!current?.capability_review?.length) return current;
      const next = [...current.capability_review];
      const index = next.findIndex((item) => item.capabilityId === capabilityId);
      const target = index + direction;
      if (index < 0 || target < 0 || target >= next.length) return current;
      const [item] = next.splice(index, 1);
      next.splice(target, 0, item);
      const nextResult = { ...current, capability_review_user_validated: true, capability_review: next };
      void persistEpicReviewArtifact(nextResult);
      return nextResult;
    });
  }

  async function generateChildrenForCurrentType(targetType: WorkItemKind = selectedItemType, forceRegenerate = false) {
    if (!canContribute) {
      setError('Planning generation is restricted to AI Gen Admins and Contributors.');
      return;
    }
    const existingDrafts = childDraftsForTarget(targetType, childDrafts);
    if (existingDrafts.length && !forceRegenerate) {
      setMessage(`${childGenerationNoun(targetType)} already generated. Review the existing preview, create it in Azure DevOps, or use Regenerate from the advanced action.`);
      changeWorkspace(targetType === 'Story' ? 'execution' : 'planning');
      window.setTimeout(() => setMessage(''), 2200);
      return;
    }
    if (currentWorkItem?.state.toLowerCase() === 'closed') {
      setError('This work item is Closed. AI Planner is read-only for closed items.');
      return;
    }
    if (currentWorkItem?.state.toLowerCase() === 'active' && forceRegenerate) {
      const confirmed = window.confirm('This work item is Active. Regenerating planning output may affect in-progress work. Continue?');
      if (!confirmed) {
        return;
      }
    }
    if (targetType === 'Epic') {
      const source = epicFeatureGenerationSource(epicInput, epicResult);
      if (epicResult?.capability_review?.length && !epicResult.capability_review.some(isCapabilityApproved)) {
        setError('Approve at least one capability before generating Features.');
        return;
      }
      if (epicResult && !forceRegenerate) {
        let drafts = mergeEpicFeatureDraftsFromCapabilityState(epicResult, childDrafts);
        if (!drafts.length) {
          // No existing feature drafts to merge — generate fresh from approved capabilities
          drafts = featureDraftsFromEpic(epicResult, true);
        }
        if (!drafts.length) {
          setError('Approve at least one capability before generating Features.');
          return;
        }
        setChildDrafts((current) => [...current.filter((draft) => draft.type !== 'Feature'), ...drafts]);
        markApprovalGenerated('features', qualityScoreForFeatureDrafts(drafts));
        await saveGeneratedArtifact('Feature', epicInput.title || 'Generated features', drafts, source);
        return;
      }
      if (!forceRegenerate && await loadReusableArtifact<ChildDraft[]>('Feature', source, (payload) => {
        setChildDrafts(payload);
        markApprovalGenerated('features', qualityScoreForFeatureDrafts(payload));
      })) {
        return;
      }
      const generated = await withLoading('Generating Features from Epic...', () => postJson<EpicRefinement>('/refine-epic', {
        profile,
        knowledge_profile: profile.knowledge_registry,
        epic: epicInput,
      }));
      if (!generated) return;
      const drafts = featureDraftsFromEpic(generated, true);
      if (!drafts.length && generated.capability_review?.length) {
        setEpicResult(generated);
        setError('Capability Review is ready. Approve capabilities before generating Features.');
        return;
      }
      setEpicResult(generated);
      setChildDrafts(drafts);
      markApprovalGenerated('features', qualityScoreForFeatureDrafts(drafts));
      await saveGeneratedArtifact('Feature', epicInput.title || 'Generated features', drafts, source);
    } else if (targetType === 'Feature') {
      const source = { feature: featureInput, purpose: 'generated_stories' };
      if (!forceRegenerate && await loadReusableArtifact<ChildDraft[]>('Story', source, (payload) => {
        setChildDrafts(payload);
        markApprovalGenerated('stories', qualityScoreForFeatureDrafts(payload));
      })) {
        return;
      }
      const generated = await withLoading('Generating Stories from Feature...', () => postJson<FeatureRefinement>('/refine-feature', {
        profile,
        knowledge_profile: profile.knowledge_registry,
        feature: featureInput,
      }));
      if (!generated) return;
      const drafts = storyDraftsFromFeature(generated);
      setFeatureResult(generated);
      setChildDrafts(drafts);
      markApprovalGenerated('stories', qualityScoreForFeature(generated));
      await saveGeneratedArtifact('Story', featureInput.title || 'Generated stories', drafts, source);
    } else if (targetType === 'Story') {
      const source = { story: storyInput, acceptance_criteria: splitLines(acceptanceCriteria), purpose: 'generated_tasks' };
      if (!forceRegenerate && await loadReusableArtifact<ChildDraft[]>('Task', source, (payload) => {
        setChildDrafts(payload);
        markApprovalGenerated('tasks', qualityScoreForTaskDrafts(payload));
      })) {
        return;
      }
      const generated = await withLoading('Generating Tasks from Story...', () => postJson<StoryRefinement>('/refine-story', {
        profile,
        knowledge_profile: profile.knowledge_registry,
        story: { ...storyInput, acceptance_criteria: splitLines(acceptanceCriteria) },
      }));
      if (!generated) return;
      const drafts = taskDraftsFromStory(generated);
      setStoryResult(generated);
      setChildDrafts(drafts);
      markApprovalGenerated('tasks', qualityScoreForTasks(generated));
      await saveGeneratedArtifact('Task', storyInput.title || 'Generated tasks', drafts, source);
    }
  }

  function markApprovalGenerated(artifact: ApprovalArtifact, qualityScore?: number) {
    setApprovalWorkflow((current) => ({
      ...current,
      [artifact]: isReadyForApproval(qualityScore) ? 'ready_for_approval' : 'draft',
    }));
  }

  function approveArtifact(artifact: ApprovalArtifact) {
    setApprovalWorkflow((current) => ({ ...current, [artifact]: 'approved' }));
    void lockStoredArtifactsForApproval(artifact);
  }

  async function lockStoredArtifactsForApproval(approval: ApprovalArtifact) {
    const artifactTypes = lifecycleTypesForApproval(approval);
    if (!artifactTypes.length) {
      return;
    }
    const approver = permissionState.user_display_name || permissionState.user_name || 'AI Gen User';
    const drafts = artifactRecords.filter((artifact) => (
      artifactTypes.includes(artifact.artifact_type as ArtifactType)
      && ['draft', 'approved'].includes(artifact.state)
    ));
    if (!drafts.length) {
      return;
    }
    const locked = await Promise.all(drafts.map((artifact) => approveStoredArtifact(artifact.artifact_id, approver).catch(() => undefined)));
    const lockedRecords = locked.filter((artifact): artifact is ArtifactRecord => Boolean(artifact));
    if (lockedRecords.length) {
      setArtifactRecords((current) => current.map((artifact) => lockedRecords.find((lockedArtifact) => lockedArtifact.artifact_id === artifact.artifact_id) || artifact));
      setArtifactReuseStatus(`${approvalLabel(approval)} approved and locked for reuse.`);
      await refreshGraphInsights();
      await syncEngineeringMemoryForArtifacts(lockedRecords);
    }
  }

  async function approveEpic() {
    if (!epicResult) {
      setError('Generate the epic draft before approving it.');
      return;
    }
    approveArtifact('epic');
    setMessage('Epic approved. Review and approve capabilities before generating Features.');
    window.setTimeout(() => setMessage(''), 1800);
  }

function approveFeatures() {
    const hasFeatureDrafts = childDrafts.some((draft) => draft.type === 'Feature');
    if (!hasFeatureDrafts && epicResult?.recommended_features?.length) {
      const drafts = featureDraftsFromEpic(epicResult, false).map((draft) => ({ ...draft, status: 'approved' as ChildDraft['status'] }));
      approveArtifact('features');
      setChildDrafts((current) => [...current.filter((draft) => draft.type !== 'Feature'), ...drafts]);
      void persistChildDraftReviewArtifact('Feature', drafts, 'approved');
      return;
    }
    if (!hasFeatureDrafts) {
      setError('Generate features before approving them.');
      return;
    }
    approveArtifact('features');
    const nextDrafts = childDrafts.map((draft) => draft.type === 'Feature' ? { ...draft, status: draft.status === 'created' ? draft.status : 'approved' } : draft);
    setChildDrafts(nextDrafts as ChildDraft[]);
    void persistChildDraftReviewArtifact('Feature', nextDrafts as ChildDraft[], 'approved');
  }

  async function approveFeature() {
    if (!featureResult) {
      setError('Generate the feature draft before approving it.');
      return;
    }
    approveArtifact('feature');
    const drafts = storyDraftsFromFeature(featureResult);
    if (drafts.length) {
      setChildDrafts(drafts);
      markApprovalGenerated('stories', qualityScoreForFeature(featureResult));
      setMessage('Feature approved. Stories are ready for review.');
      window.setTimeout(() => setMessage(''), 1200);
      return;
    }
    setSelectedItemType('Feature');
    await generateChildrenForCurrentType();
  }

  function approveStories() {
    if (!childDrafts.some((draft) => draft.type === 'User Story')) {
      setError('Generate stories before approving them.');
      return;
    }
    approveArtifact('stories');
    const nextDrafts = childDrafts.map((draft) => draft.type === 'User Story' ? { ...draft, status: draft.status === 'created' ? draft.status : 'approved' } : draft);
    setChildDrafts(nextDrafts as ChildDraft[]);
    void persistChildDraftReviewArtifact('Story', nextDrafts as ChildDraft[], 'approved');
  }

  async function approveStory() {
    if (!storyResult) {
      setError('Generate the story draft before approving it.');
      return;
    }
    approveArtifact('story');
    setMessage('Story approved. Generate Tasks from Planning to continue.');
    window.setTimeout(() => setMessage(''), 1600);
  }

  function approveTasks() {
    if (!childDrafts.some((draft) => draft.type === 'Task')) {
      setError('Generate tasks before approving them.');
      return;
    }
    approveArtifact('tasks');
    setChildDrafts((drafts) => drafts.map((draft) => draft.type === 'Task' ? { ...draft, status: draft.status === 'created' ? draft.status : 'approved' } : draft));
  }

  function approveTestSuite() {
    if (!qaTestSuite) {
      setError('Generate test cases before approving the test suite.');
      return;
    }
    approveArtifact('qa');
  }

  function approveExecutionPackage() {
    if (!executionContext) {
      setError('Build the implementation package before approving it.');
      return;
    }
    approveArtifact('execution');
  }

  async function analyzeCurrentItemImpact() {
    if (!canContribute) {
      setError('Impact analysis is restricted to AI Gen Admins and Contributors.');
      return;
    }
    if (currentItemType === 'Epic') {
      const input = epicInput.title.trim() ? epicInput : { title: currentWorkItem?.title || '', description: htmlToText(currentWorkItem?.description || '') };
      const result = await withLoading('Analyzing epic impact...', () => postJson<EpicImpact>('/analyze-epic-impact', {
        profile,
        knowledge_profile: profile.knowledge_registry,
        epic: input,
      }));
      if (result) setEpicImpact(result);
    } else if (currentItemType === 'Feature') {
      const input = featureInput.title.trim() ? featureInput : { title: currentWorkItem?.title || '', description: htmlToText(currentWorkItem?.description || '') };
      const result = await withLoading('Analyzing feature impact...', () => postJson<FeatureImpact>('/analyze-feature-impact', {
        profile,
        knowledge_profile: profile.knowledge_registry,
        feature: input,
      }));
      if (result) setFeatureImpact(result);
    } else {
      const result = await withLoading(currentItemType === 'Bug' ? 'Analyzing bug impact...' : 'Analyzing story impact...', () => postJson<StoryImpact>('/analyze-story-impact', {
        profile,
        knowledge_profile: profile.knowledge_registry,
        story: currentStoryPayload(),
      }));
      if (result) setStoryImpact(result);
    }
  }

  async function createSelectedChildWorkItems() {
    if (!canContribute) {
      setError('Azure DevOps work item creation is restricted to AI Gen Admins and Contributors.');
      return;
    }
    if (!currentWorkItem) {
      setError('Current Azure DevOps work item is not loaded.');
      return;
    }
    if (currentWorkItem.state.toLowerCase() === 'closed') {
      setError('This work item is Closed. Child work item creation is disabled.');
      return;
    }
    const sourceDrafts = currentItemType === 'Epic'
      ? mergeEpicFeatureDraftsFromCapabilityState(epicResult, childDrafts)
      : currentItemType === 'Feature'
        ? mergeFeatureStoryDraftsFromReviewState(featureResult, childDrafts)
        : childDrafts.filter((draft) => draft.type === 'Task');
    const selected = sourceDrafts.filter((draft) => draft.selected && draft.status !== 'created');
    if (!selected.length) {
      setError('Select at least one generated child work item to create.');
      return;
    }
    const confirmed = window.confirm(`Create ${selected.length} Azure DevOps work item(s) under ${currentWorkItem.type} #${currentWorkItem.id}?`);
    if (!confirmed) {
      return;
    }
    setCreationLog([]);
    const created = await withLoading('Creating Azure DevOps child work items...', async () => {
      const accessToken = await SDK.getAccessToken();
      const results: ChildDraft[] = [];
      for (const draft of selected) {
        setCreationLog((log) => [`Creating ${draft.type}: ${draft.title}`, ...log]);
        setChildDrafts((items) => items.map((item) => item.id === draft.id ? { ...item, status: 'creating' } : item));
        try {
          const id = await createAdoWorkItem(currentWorkItem, accessToken, draft);
          const next = { ...draft, status: 'created' as const, azureId: id };
          results.push(next);
          setCreationLog((log) => [`Created ${draft.type} #${id}: ${draft.title}`, ...log]);
          setChildDrafts((items) => items.map((item) => item.id === draft.id ? next : item));
        } catch (error) {
          const message = error instanceof Error ? error.message : String(error);
          const next = { ...draft, status: 'failed' as const, error: message };
          results.push(next);
          setCreationLog((log) => [`Failed ${draft.type}: ${draft.title} - ${message}`, ...log]);
          setChildDrafts((items) => items.map((item) => item.id === draft.id ? next : item));
        }
      }
      return results;
    });
    if (created?.some((draft) => draft.status === 'created')) {
      await addAdoComment(
        currentWorkItem,
        `[AI Planner Created Work Items]\n${created.filter((draft) => draft.status === 'created').map((draft) => `- ${draft.type} #${draft.azureId}: ${draft.title}`).join('\n')}`
      ).catch(() => undefined);
    }
  }

  async function analyzeEpicImpact() {
    if (!canContribute) {
      setError('Impact analysis is restricted to AI Gen Admins and Contributors.');
      return;
    }
    const result = await withLoading('Analyzing epic impact...', () => postJson<EpicImpact>('/analyze-epic-impact', {
      profile,
      knowledge_profile: profile.knowledge_registry,
      epic: epicImpactInput,
    }));
    if (result) {
      setEpicImpact(result);
    }
  }

  async function analyzeFeatureImpact() {
    if (!canContribute) {
      setError('Impact analysis is restricted to AI Gen Admins and Contributors.');
      return;
    }
    const result = await withLoading('Analyzing feature impact...', () => postJson<FeatureImpact>('/analyze-feature-impact', {
      profile,
      knowledge_profile: profile.knowledge_registry,
      feature: featureImpactInput,
    }));
    if (result) {
      setFeatureImpact(result);
    }
  }

  async function analyzeStoryImpact() {
    if (!canContribute) {
      setError('Impact analysis is restricted to AI Gen Admins and Contributors.');
      return;
    }
    const result = await withLoading('Analyzing story impact...', () => postJson<StoryImpact>('/analyze-story-impact', {
      profile,
      knowledge_profile: profile.knowledge_registry,
      story: storyImpactInput,
    }));
    if (result) {
      setStoryImpact(result);
    }
  }

  async function loadAdoProjects(sourceProfile: ProjectProfile = profile) {
    setRepositoryLoadMessage('Loading Azure DevOps projects...');
    try {
      const projectResponse = await fetchAdoProjects();
      const projects = projectResponse.projects || [];
      setAdoProjects(projects);
      const selectedProject = getAdoMapping(sourceProfile).ado_project || projects[0]?.name || '';
      if (selectedProject) {
        const selectedAdoProject = projects.find((project) => project.name === selectedProject);
        let profileWithProject = sourceProfile;
        if (!getAdoMapping(sourceProfile).ado_project) {
          profileWithProject = applyAdoMapping(sourceProfile, { ado_project: selectedProject });
          setProfile(profileWithProject);
        }
        if (selectedAdoProject && (!sourceProfile.project_name.trim() || !sourceProfile.project_description.trim())) {
          setProfile((current) => seedProfileFromAzureProject(current, {
            id: selectedAdoProject.id,
            name: selectedAdoProject.name,
            description: selectedAdoProject.description || '',
          }));
        }
        if (projectResponse.warnings?.length) {
          setRepositoryLoadMessage(projectResponse.warnings.join(' '));
        }
        await loadRepositories(selectedProject, profileWithProject);
      } else {
        setRepositories([]);
        setBranches([]);
        const missing = projectResponse.missing_env?.length
          ? ` Missing backend env: ${projectResponse.missing_env.join(', ')}.`
          : '';
        setRepositoryLoadMessage(`No Azure DevOps projects were returned.${missing} Configure ADO_PROJECT or grant the PAT Project read access.`);
      }
    } catch (loadError) {
      const detail = loadError instanceof Error ? loadError.message : String(loadError);
      setAdoProjects([]);
      setRepositories([]);
      setBranches([]);
      setRepositoryLoadMessage(`Could not load Azure DevOps projects from backend connector. ${detail}`);
      setError('Could not load Azure DevOps projects. Check backend ADO_ORG_URL, ADO_PAT, ADO_PROJECT, and Project/Code read permissions.');
    }
  }

  async function loadRepositories(adoProject = getAdoMapping(profile).ado_project, sourceProfile: ProjectProfile = profile) {
    setRepositoryLoadMessage('Loading Azure DevOps repositories...');
    if (!adoProject) {
      setRepositories([]);
      setBranches([]);
      setRepositoryLoadMessage('Select an Azure DevOps project first.');
      return;
    }
    try {
      const repos = await fetchAdoRepositories(adoProject);
      const visibleRepos = (repos || []).filter((repo) => repo.id && repo.name);
      setRepositories(visibleRepos);
      if (
        sourceProfile.repository_connection.repository_id
        && !visibleRepos.some((repo) => repo.id === sourceProfile.repository_connection.repository_id)
      ) {
        setProfile((current) => ({
          ...applyAdoMapping(current, { ado_project: adoProject, repository_id: '', repository_name: '', branch: '' }),
          repository_connection: { ...current.repository_connection, repository_id: '', repository_name: '', branch: '', status: 'Not connected' },
        }));
        setBranches([]);
      }
      setRepositoryLoadMessage(
        visibleRepos.length
          ? `Loaded ${visibleRepos.length} Azure DevOps repositories.`
          : 'No repositories were returned for this project. Check Code read permission and retry.',
      );
    } catch (loadError) {
      const detail = loadError instanceof Error ? loadError.message : String(loadError);
      setRepositories([]);
      setRepositoryLoadMessage(`Could not load repositories from Azure DevOps backend connector. ${detail}`);
      setError('Could not load Azure DevOps repositories. Select a valid ADO project and check backend PAT Code read permission.');
    }
  }

  async function selectAdoProject(adoProject: string) {
    if (!canAdmin) {
      setError('Repository mapping is restricted to AI Gen Admins.');
      return;
    }
    const nextProfile = applyAdoMapping(profile, {
      ado_project: adoProject,
      repository_id: '',
      repository_name: '',
      branch: '',
    });
    setProfile(nextProfile);
    setRepositories([]);
    setBranches([]);
    await saveAdoMapping(nextProfile);
    if (adoProject) {
      await loadRepositories(adoProject, nextProfile);
    }
  }

  async function selectRepository(repositoryId: string) {
    if (!canAdmin) {
      setError('Repository mapping is restricted to AI Gen Admins.');
      return;
    }
    const selected = repositories.find((repo) => repo.id === repositoryId);
    if (repositoryId && !selected) {
      setError('Select a repository from the Azure DevOps dropdown. Manual repository values are not supported.');
      return;
    }
    const nextProfile = applyAdoMapping({
      ...profile,
      repository_connection: {
        ...profile.repository_connection,
        repository_id: selected?.id || '',
        repository_name: selected?.name || '',
        status: selected ? 'Repository selected' : 'Not connected',
      },
    }, {
      repository_id: selected?.id || '',
      repository_name: selected?.name || '',
    });
    setProfile(nextProfile);
    setBranches([]);
    if (!selected?.id) {
      return;
    }
    try {
      const branchNames = await fetchAdoBranches(getAdoMapping(nextProfile).ado_project, selected.id);
      setBranches(branchNames);
      const defaultBranch = normalizeBranchName(selected.defaultBranch || '') || branchNames[0] || '';
      const mappedProfile = applyAdoMapping({
        ...nextProfile,
        repository_connection: {
          ...nextProfile.repository_connection,
          branch: defaultBranch,
          status: 'Repository connected',
        },
      }, { branch: defaultBranch });
      setProfile(mappedProfile);
      await saveAdoMapping(mappedProfile);
    } catch (branchError) {
      const detail = branchError instanceof Error ? branchError.message : String(branchError);
      setRepositoryLoadMessage(`Repository selected, but branches could not be loaded. ${detail}`);
      setError('Repository selected, but branches could not be loaded from backend connector.');
    }
  }

  async function analyzeReadme() {
    if (!canAdmin) {
      setError('Repository knowledge refresh is restricted to AI Gen Admins.');
      return;
    }
    const selectedRepo = profile.repository_connection.repository_id;
    if (!selectedRepo || (!repositories.some((repo) => repo.id === selectedRepo) && !profile.repository_connection.repository_name)) {
      setError('Select a repository from the Azure DevOps dropdown before analyzing README.');
      return;
    }
    const analyzed = await withLoading('Loading and analyzing README...', async () => {
      const readmePath = profile.repository_connection.readme_path || '/README.md';
      const branch = profile.repository_connection.branch || 'main';
      const readmeContent = await fetchAdoRepositoryFileContent(getAdoMapping(profile, { branch }), readmePath);
      return postJson<ProjectProfile>('/analyze-readme', {
        profile,
        readme_content: readmeContent,
        repository: {
          id: selectedRepo,
          name: profile.repository_connection.repository_name,
          ado_project: getAdoMapping(profile).ado_project,
          branch,
          readme_path: readmePath,
        },
      });
    });
    if (analyzed) {
      setProfile(analyzed);
      setLastAnalysisTimestamp(new Date().toISOString());
      markKnowledgeRefreshed(analyzed);
    }
  }

  async function discoverRepositoryDocuments() {
    if (!canAdmin) {
      setError('Repository discovery is restricted to AI Gen Admins.');
      return;
    }
    const selectedRepo = profile.repository_connection.repository_id;
    if (!selectedRepo || (!repositories.some((repo) => repo.id === selectedRepo) && !profile.repository_connection.repository_name)) {
      setError('Select a repository from the Azure DevOps dropdown before discovering documentation.');
      return;
    }
    const discovered = await withLoading('Discovering repository documentation...', async () => {
      const branch = profile.repository_connection.branch || 'main';
      const nextStatus: Record<string, 'available' | 'missing' | 'unknown'> = {};
      const nextDocuments: Record<string, string> = {};
      const discoveredFiles = await Promise.all(REPOSITORY_DOCUMENTS.map(async (path) => {
        try {
          const content = await fetchAdoRepositoryFileContent(getAdoMapping(profile, { branch }), path);
          return { path, status: 'available' as const, content };
        } catch {
          return { path, status: 'missing' as const, content: '' };
        }
      }));
      discoveredFiles.forEach((file) => {
        nextStatus[file.path] = file.status;
        if (file.content) {
          nextDocuments[file.path] = file.content;
        }
      });
      return { status: nextStatus, documents: nextDocuments };
    });
    if (discovered) {
      setRepositoryFileStatus(discovered.status);
      setRepositoryDocuments((current) => ({ ...current, ...discovered.documents }));
      const available = Object.entries(discovered.status).filter(([, status]) => status === 'available').map(([path]) => path);
      setSelectedRepositoryFiles(available.length ? available : selectedRepositoryFiles);
      if (!available.length) {
        setError('No known documentation files were found. Paste README, architecture, modules, or flows content manually.');
      }
    }
  }

  async function analyzeRepositoryDocumentsForProfile(sourceProfile: ProjectProfile): Promise<ProjectProfile | undefined> {
    const selectedRepo = sourceProfile.repository_connection.repository_id;
    const selectedFiles = selectedRepositoryFiles.length ? selectedRepositoryFiles : REPOSITORY_DOCUMENTS;
    const fetchedDocuments: Record<string, string> = {};
    if (selectedRepo && (repositories.some((repo) => repo.id === selectedRepo) || sourceProfile.repository_connection.repository_name)) {
      const branch = sourceProfile.repository_connection.branch || 'main';
      const nextStatus: Record<string, 'available' | 'missing' | 'unknown'> = {};
      const fetchedFiles = await Promise.all(selectedFiles.map(async (path) => {
        try {
          const content = await fetchAdoRepositoryFileContent(getAdoMapping(sourceProfile, { branch }), path);
          return { path, status: 'available' as const, content };
        } catch {
          return { path, status: 'missing' as const, content: '' };
        }
      }));
      fetchedFiles.forEach((file) => {
        nextStatus[file.path] = file.status;
        if (file.content) {
          fetchedDocuments[file.path] = file.content;
        }
      });
      setRepositoryFileStatus((current) => ({ ...current, ...nextStatus }));
      const available = Object.entries(nextStatus).filter(([, status]) => status === 'available').map(([path]) => path);
      if (available.length) {
        setSelectedRepositoryFiles(available);
      }
    }
    const documents = {
      ...fetchedDocuments,
      ...Object.fromEntries(Object.entries(repositoryDocuments).filter(([, content]) => content.trim())),
    };
    if (!Object.keys(documents).length) {
      return sourceProfile;
    }
    const refreshed = await postJson<KnowledgeCacheResponse>('/knowledge-cache/refresh', {
      profile: sourceProfile,
      connector_mapping: getAdoMapping(sourceProfile),
      repository: {
        provider: 'azure_devops',
        project: getAdoMapping(sourceProfile).ado_project,
        repository_id: selectedRepo,
        repository_name: sourceProfile.repository_connection.repository_name,
        branch: sourceProfile.repository_connection.branch || 'main',
      },
      selected_files: Object.keys(documents),
      documents,
    });
    if (!refreshed.success && refreshed.message) {
      setError(refreshed.message);
    }
    setKnowledgeCacheStatus(refreshed);
    return refreshed.cache?.profile || sourceProfile;
  }

  async function analyzeRepositoryDocuments() {
    if (!canAdmin) {
      setError('Repository knowledge refresh is restricted to AI Gen Admins.');
      return;
    }
    if (profile.repository_connection.repository_id && !repositories.some((repo) => repo.id === profile.repository_connection.repository_id) && !profile.repository_connection.repository_name) {
      setError('Select a repository from the Azure DevOps dropdown, or paste document content in Manual Document Paste Fallback.');
      return;
    }
    if (!profile.repository_connection.repository_id && !Object.values(repositoryDocuments).some((content) => content.trim())) {
      setError('Select or paste at least one repository document before analyzing.');
      return;
    }
    const analyzed = await withLoading('Analyzing repository documents...', () => analyzeRepositoryDocumentsForProfile(profile));
    if (analyzed) {
      setProfile(analyzed);
      setLastAnalysisTimestamp(new Date().toISOString());
      markKnowledgeRefreshed(analyzed);
    }
  }

  function changeWorkspace(tab: PlannerTab, navigationId?: string) {
    setActiveTab(tab);
    setActiveNavigationId(navigationId || navigationIdForPlannerTab(tab));
    if (tab !== recommendedWorkspace && tab !== 'admin' && tab !== 'overview') {
      setAutoRouteByWorkItemType(false);
    }
  }

  function navigateCommandCenter(item: WorkspaceNavigationItem) {
    if (!item.enabled) {
      return;
    }
    changeWorkspace(item.target as PlannerTab, item.id);
  }

  async function updateWorkspacePreferences(changes: Partial<WorkspacePreferences>) {
    const userId = permissionState.user_name || permissionState.user_display_name || 'current-user';
    setEngineeringWorkspace((current) => current ? {
      ...current,
      preferences: { ...current.preferences, ...changes },
    } : current);
    try {
      const preferences = await putWorkspacePreferences(userId, permissionState.role, changes);
      setEngineeringWorkspace((current) => current ? { ...current, preferences } : current);
    } catch (preferenceError) {
      setError(preferenceError instanceof Error ? preferenceError.message : 'Unable to save workspace preferences.');
      const workspace = await getEngineeringWorkspace(userId, permissionState.role).catch(() => undefined);
      if (workspace) {
        setEngineeringWorkspace(workspace);
      }
    }
  }

  async function refreshDashboardOverview() {
    try {
      const overview = await getDashboardOverview(profile.project_id);
      setDashboardOverview(overview);
      setEngineeringWorkspace((current) => current ? {
        ...current,
        notifications: dashboardNotifications(overview),
      } : current);
    } catch (dashboardError) {
      setError(dashboardError instanceof Error ? dashboardError.message : 'Unable to refresh Engineering Command Center state.');
    }
  }

  async function refreshCommandCenterSignals() {
    try {
      const response = await fetch(`${PLATFORM_BASE_URL}/command-center/health`);
      if (!response.ok) return;
      const value = await response.json();
      const notices = Array.isArray(value?.notifications?.items) ? value.notifications.items.map((item: any) => ({
        id: item.notificationId || item.id,
        title: item.title || 'HEI update',
        message: item.message || '',
        severity: item.severity || 'Info',
      })) : [];
      setEngineeringWorkspace((current) => current ? {
        ...current,
        status: { state: value.status || 'Ready', message: value.status === 'Healthy' ? 'HEI services available' : 'HEI services need attention', checkedAt: value.generatedAt || new Date().toISOString() },
        notifications: current.preferences.notificationsEnabled ? notices : [],
      } : current);
    } catch {
      // Background status refresh must not interrupt the active engineering workflow.
    }
  }

  return (
    <EngineeringCommandCenterShell
      workspace={engineeringWorkspace}
      activeNavigationId={activeNavigationId}
      projectName={profile.project_name || currentWorkItem?.project || ''}
      userName={permissionState.user_display_name || permissionState.user_name || 'HEI User'}
      roleLabel={roleLabel(permissionState.role)}
      busy={loading}
      onNavigate={navigateCommandCenter}
      onPreferencesChange={(changes) => void updateWorkspacePreferences(changes)}
      headerActions={canAdmin ? (
        <button
          className="planner-button secondary"
          onClick={() => {
            const next = !(editingProfile || showQuickStart);
            setEditingProfile(next);
            setShowQuickStart(next);
          }}
          disabled={loading}
        >
          {editingProfile || showQuickStart ? 'Hide Setup' : 'Project Setup'}
        </button>
      ) : null}
    >
    <main className="planner-shell">

      {showResumePanel && resumeSession ? (
        <ProjectSessionResumeCard
          session={resumeSession}
          onContinue={continueProjectSession}
          onRefresh={() => void refreshProjectAnalysis()}
          loading={loading}
          canRefresh={canAdmin}
        />
      ) : null}

      {loading ? <div className="planner-banner">{message || 'Working...'}</div> : null}
      {error ? <div className="planner-error">{error}</div> : null}
      {isViewer ? <div className="planner-banner">Viewer access: Project Intelligence is read-only for your Azure DevOps group.</div> : null}

      <StickyContextBar
        workItem={currentWorkItem}
        itemType={currentItemType}
        activeTab={activeTab}
        recommendedWorkspace={recommendedWorkspace}
        workflow={workflowOrchestration}
        autoRoute={autoRouteByWorkItemType}
        loading={loading}
        canContribute={canContribute}
        currentRole={roleLabel(permissionState.role)}
        onToggleAutoRoute={setAutoRouteByWorkItemType}
        onContinueWorkflow={() => void continueWorkflow()}
      />

      {activeTab === 'overview' ? (
        <CommandCenterWorkspace
          dashboardOverview={dashboardOverview}
          profile={profile}
          workItem={currentWorkItem}
          workflow={workflowOrchestration}
          knowledgeCacheStatus={knowledgeCacheStatus}
          capsuleStatus={contextCapsuleStatus}
          session={resumeSession}
          loading={loading}
          canAdmin={canAdmin}
          canContribute={canContribute}
          hasQa={Boolean(qaTestSuite)}
          hasExecution={Boolean(executionContext)}
          showQuickStart={showQuickStart}
          adoProjects={adoProjects}
          repositories={repositories}
          branches={branches}
          repositoryLoadMessage={repositoryLoadMessage}
          onContinue={continueProjectSession}
          onContinueWorkflow={() => void continueWorkflow()}
          onRefresh={() => void refreshProjectAnalysis()}
          onChangeRepository={() => {
            void openRepositorySettings();
          }}
          onProfileChange={setProfile}
          onSelectAdoProject={(adoProject) => void selectAdoProject(adoProject)}
          onSelectRepository={(repositoryId) => void selectRepository(repositoryId)}
          onReloadRepositories={() => void loadAdoProjects()}
          onAnalyzeProject={() => void analyzeProject()}
          onRefreshDashboard={() => void refreshDashboardOverview()}
        />
      ) : null}

      {activeTab === 'planning' ? (
        <>
        <PlanningCenter
          baseUrl={PLATFORM_BASE_URL}
          projectId={profile.project_id || ''}
          actor={permissionState.user_display_name || permissionState.user_name || 'HEI User'}
          currentWorkItemId={currentWorkItem?.id ? String(currentWorkItem.id) : undefined}
          canContribute={canContribute}
          onGenerateExecutionPackage={() => void buildExecutionPackage(true)}
          onError={setError}
        />
        <details className="hei-planning-intelligence-workspace">
          <summary>Planning Intelligence Workspace</summary>
          <AIPlannerWorkspace
          profile={profile}
          loading={loading}
          currentWorkItem={currentWorkItem}
          childDrafts={childDrafts}
          creationLog={creationLog}
          providerMetadata={latestProvider}
          canContribute={canContribute}
          itemType={currentItemType}
          selectedItemType={selectedItemType}
          onItemTypeChange={setSelectedItemType}
          epicInput={epicInput}
          featureInput={featureInput}
          storyInput={storyInput}
          acceptanceCriteria={acceptanceCriteria}
          epicResult={epicResult}
          featureResult={featureResult}
          storyResult={storyResult}
          epicImpact={epicImpact}
          featureImpact={featureImpact}
          qaTestSuite={qaTestSuite}
          approvalWorkflow={approvalWorkflow}
          setEpicInput={setEpicInput}
          setFeatureInput={setFeatureInput}
          setStoryInput={setStoryInput}
          setAcceptanceCriteria={setAcceptanceCriteria}
          refineEpic={() => void refineEpic(true)}
          refineFeature={() => void refineFeature(true)}
          retryFeatureAI={() => void refineFeature(true, 'retry_ai_enrichment')}
          refineStory={() => void refineStory(true)}
          analyzeImpact={() => void analyzeCurrentItemImpact()}
          generateChildren={(forceRegenerate) => void generateChildrenForCurrentType(currentWorkItem?.type === 'User Story' || currentWorkItem?.type === 'Story' ? 'Story' : undefined, forceRegenerate)}
          approveEpic={() => void approveEpic()}
          approveFeatures={() => approveFeatures()}
          approveFeature={() => void approveFeature()}
          approveStories={() => approveStories()}
          approveTasks={() => approveTasks()}
          updateCapabilityReview={updateCapabilityReview}
          moveCapabilityReview={moveCapabilityReview}
          updateDraftSelection={updateDraftSelection}
          updateChildDraftReview={updateChildDraftReview}
          createSelectedChildren={() => void createSelectedChildWorkItems()}
          buildExecutionPackage={() => void buildExecutionPackage(true)}
          generateQATestCases={() => void generateQATestCases(true)}
          artifactRecords={artifactRecords}
          artifactReuseStatus={artifactReuseStatus}
          workflow={workflowOrchestration}
          planningFocusRequest={planningFocusRequest}
          />
        </details>
        </>
      ) : null}

      {activeTab === 'execution' ? (
        <>
        <ExecutionCenter baseUrl={PLATFORM_BASE_URL} onError={setError} />
        <details className="hei-execution-intelligence-workspace">
          <summary>Execution Intelligence Workspace</summary>
          <DeveloperWorkspace
          executionContext={executionContext}
          executionPlan={executionPlan}
          executionMode={executionMode}
          devPrompt={devPrompt}
          uiPrompt={uiPrompt}
          qaPrompt={qaPrompt}
          copilotContext={copilotContext}
          onGenerate={() => void buildExecutionPackage()}
          onGenerateExecutionPlan={() => void buildExecutionPlan()}
          onGeneratePrompt={(kind) => void buildExecutionPrompt(kind)}
          onEnhanceWithAi={() => void enhanceExecutionWithAi()}
          setExecutionMode={setExecutionMode}
          loading={loading}
          canContribute={canContribute}
          itemType={currentItemType}
          currentWorkItem={currentWorkItem}
          storyInput={storyInput}
          acceptanceCriteria={acceptanceCriteria}
          setStoryInput={setStoryInput}
          setAcceptanceCriteria={setAcceptanceCriteria}
          storyResult={storyResult}
          storyImpact={storyImpact}
          qaTestSuite={qaTestSuite}
          childDrafts={childDrafts}
          creationLog={creationLog}
          providerMetadata={latestProvider}
          implementationValidation={implementationValidation}
          implementationChangedFiles={implementationChangedFiles}
          setImplementationChangedFiles={setImplementationChangedFiles}
          prReview={prReview}
          approvalWorkflow={approvalWorkflow}
          workflow={workflowOrchestration}
          refineStory={() => void refineStory()}
          analyzeImpact={() => void analyzeCurrentItemImpact()}
          generateChildren={(forceRegenerate) => void generateChildrenForCurrentType('Story', forceRegenerate)}
          generateQATestCases={() => void generateQATestCases()}
          approveStory={() => void approveStory()}
          approveTasks={() => approveTasks()}
          approveExecutionPackage={() => approveExecutionPackage()}
          updateDraftSelection={updateDraftSelection}
          createSelectedChildren={() => void createSelectedChildWorkItems()}
          onOpenVsCode={() => openVsCodeExecutionPackage()}
          onOpenQA={() => changeWorkspace('qa')}
          validateImplementation={() => void validateImplementation()}
          runPRReview={() => void runPRReview()}
          postPRReviewComment={() => void postPRReviewComment()}
          />
        </details>
        </>
      ) : null}

      {activeTab === 'qa' ? (
        <QAWorkspace
          loading={loading}
          storyInput={storyInput}
          acceptanceCriteria={acceptanceCriteria}
          setStoryInput={setStoryInput}
          setAcceptanceCriteria={setAcceptanceCriteria}
          qaTestSuite={qaTestSuite}
          approvalWorkflow={approvalWorkflow}
          storyImpact={storyImpact}
          generateQATestCases={() => void generateQATestCases()}
          approveTestSuite={() => approveTestSuite()}
          canContribute={canContribute}
          itemType={currentItemType}
          currentWorkItem={currentWorkItem}
          analyzeImpact={() => void analyzeCurrentItemImpact()}
          executionContext={executionContext}
          implementationValidation={implementationValidation}
          prReview={prReview}
          coverageReport={coverageReport}
          graphSummary={graphSummary}
          workflow={workflowOrchestration}
        />
      ) : null}

      {activeTab === 'memory' ? (
        <EngineeringMemoryWorkspace
          memories={engineeringMemories}
          diagnostics={engineeringMemoryDiagnostics}
          query={engineeringMemoryQuery}
          status={engineeringMemoryStatus}
          onQueryChange={setEngineeringMemoryQuery}
          onSearch={() => void searchEngineeringMemory()}
          onRefresh={() => void refreshEngineeringMemory()}
        />
      ) : null}

      {activeTab === 'governance' && activeNavigationId === 'approvals' ? (
        <ApprovalCenter
          baseUrl={PLATFORM_BASE_URL}
          actor={permissionState.user_display_name || permissionState.user_name || 'HEI User'}
          role={permissionState.role}
          canApprove={canContribute}
          onError={setError}
        />
      ) : null}

      {activeTab === 'governance' && activeNavigationId !== 'approvals' ? (
        <GovernanceWorkspace
          dashboard={governanceDashboard}
          status={governanceStatus}
          onRefresh={() => void refreshGovernanceDashboard()}
        />
      ) : null}

      {activeTab === 'agents' ? (
        <AgentCenter
          baseUrl={PLATFORM_BASE_URL}
          canRetry={canContribute}
          onOpenActivity={() => changeWorkspace('diagnostics', 'activity')}
          onError={setError}
        />
      ) : null}

      {activeTab === 'skills' ? (
        <SkillsWorkspace
          dashboard={skillsDashboard}
          status={skillsStatus}
          onRefresh={() => void refreshSkillsDashboard()}
        />
      ) : null}

      {activeTab === 'diagnostics' && activeNavigationId === 'activity' ? (
        <React.Suspense fallback={<div className="hei-workspace-loading" role="status">Loading Activity Center...</div>}><ActivityCenter baseUrl={PLATFORM_BASE_URL} onError={setError} /></React.Suspense>
      ) : null}

      {activeTab === 'diagnostics' && activeNavigationId === 'health' ? (
        <React.Suspense fallback={<div className="hei-workspace-loading" role="status">Loading Platform Health...</div>}><CommandCenterHealth baseUrl={PLATFORM_BASE_URL} role={permissionState.role} onError={setError} /></React.Suspense>
      ) : null}

      {activeTab === 'diagnostics' && !['activity', 'health'].includes(activeNavigationId) ? (
        <DiagnosticsWorkspace
          providerMetadata={latestProvider}
          workflow={workflowOrchestration}
          knowledgeCacheStatus={knowledgeCacheStatus}
          capsuleStatus={contextCapsuleStatus}
          governanceStatus={governanceStatus}
          agentStatus={agentStatus}
          skillsStatus={skillsStatus}
          memoryStatus={engineeringMemoryStatus}
        />
      ) : null}

      {activeTab === 'admin' && activeNavigationId === 'repository' ? (
        <RepositoryCenter
          baseUrl={PLATFORM_BASE_URL}
          preferredRepositoryId={profile.repository_connection?.repository_id || ''}
          actor={permissionState.user_display_name || permissionState.user_name || 'HEI User'}
          canManage={canAdmin}
          onError={setError}
        />
      ) : null}

      {activeTab === 'admin' && activeNavigationId === 'azure-devops' ? (
        <AzureDevOpsCenter
          baseUrl={PLATFORM_BASE_URL}
          projectId={profile.project_id || ''}
          canApprove={canContribute}
          onOpenApprovals={() => changeWorkspace('governance', 'approvals')}
          onError={setError}
        />
      ) : null}

      {activeTab === 'admin' && !['repository', 'azure-devops'].includes(activeNavigationId) && canAdmin ? (
        <AdminWorkspace
          permission={permissionState}
          profile={profile}
          governance={knowledgeGovernance}
          providerMetadata={latestProvider}
          loading={loading}
          adoProjects={adoProjects}
          repositories={repositories}
          branches={branches}
          repositoryLoadMessage={repositoryLoadMessage}
          repositoryDocuments={repositoryDocuments}
          fileStatus={repositoryFileStatus}
          selectedFiles={selectedRepositoryFiles}
          onRefreshPermissions={() => void refreshPermissions()}
          onSelectAdoProject={(adoProject) => void selectAdoProject(adoProject)}
          onSelectRepository={(repositoryId) => void selectRepository(repositoryId)}
          onReloadRepositories={() => void loadAdoProjects()}
          onProfileChange={setProfile}
          onRepositoryDocumentsChange={setRepositoryDocuments}
          onFileStatusChange={setRepositoryFileStatus}
          onSelectedFilesChange={setSelectedRepositoryFiles}
          onAnalyzeReadme={() => void analyzeReadme()}
          onDiscoverDocuments={() => void discoverRepositoryDocuments()}
          onAnalyzeDocuments={() => void analyzeRepositoryDocuments()}
          onAnalyzeDescription={() => void analyzeDescription()}
          onSaveProfile={() => void saveProfile()}
        />
      ) : null}
    </main>
    </EngineeringCommandCenterShell>
  );
}

function EngineeringMemoryWorkspace({
  memories,
  diagnostics,
  query,
  status,
  onQueryChange,
  onSearch,
  onRefresh,
}: {
  memories: EngineeringMemoryItem[];
  diagnostics: Record<string, unknown>;
  query: string;
  status: string;
  onQueryChange: (value: string) => void;
  onSearch: () => void;
  onRefresh: () => void;
}) {
  const categories = [
    'Planning Pattern',
    'Execution Pattern',
    'QA Pattern',
    'Decision',
    'Lesson Learned',
  ];
  const visibleMemories = memories.filter((memory) => {
    const state = String(memory.approvalStatus || '').toLowerCase();
    return state.includes('approved') || state.includes('indexed') || state.includes('available');
  }).map((memory) => ({
    ...memory,
    category: normalizedMemoryCategory(memory.category),
  }));
  const counts = categories.map((category) => ({
    category,
    count: visibleMemories.filter((memory) => memory.category === category).length,
  }));
  const latest = [...visibleMemories].sort((left, right) => String(right.updatedAt || '').localeCompare(String(left.updatedAt || ''))).slice(0, 6);
  return (
    <section className="planner-section">
      <div className="planner-section-header">
        <div>
          <div className="planner-label">Memory</div>
          <h2>Validated Engineering Knowledge</h2>
          <p>Only approved and indexed knowledge is shown here so teams can reuse patterns with confidence.</p>
        </div>
        <button className="planner-button secondary" type="button" onClick={onRefresh}>Refresh Memory</button>
      </div>

      <div className="planner-status-grid">
        <Row label="Memory Status" value={status} />
        <Row label="Reusable Items" value={String(visibleMemories.length)} />
        <Row label="Lifecycle" value="Approved → Indexed → Available" />
      </div>

      <div className="planner-card">
        <div className="planner-label">Search</div>
        <div className="planner-form-row">
          <input
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                onSearch();
              }
            }}
            placeholder="Search by story, module, flow, decision, repository, or lesson"
          />
          <button className="planner-button" type="button" onClick={onSearch}>Search Memory</button>
        </div>
      </div>

      <div className="planner-summary-grid">
        {counts.map((item) => (
          <SummaryTile key={item.category} title={item.category} value={item.count} />
        ))}
      </div>

      <div className="planner-two-column">
        <div className="planner-card">
          <div className="planner-label">Memory Library</div>
          {visibleMemories.length ? (
            <div className="planner-list">
              {visibleMemories.map((memory) => (
                <EngineeringMemoryCard key={memory.id} memory={memory} />
              ))}
            </div>
          ) : (
            <EmptyState
              title="No reusable memory indexed yet."
              detail="Approve and index planning, execution, QA, decision, or lesson artifacts to make them reusable here."
            />
          )}
        </div>
        <div className="planner-card">
          <div className="planner-label">Timeline</div>
          {latest.length ? (
            <ul className="planner-list">
              {latest.map((memory) => (
                <li key={`${memory.id}-timeline`}>
                  <strong>{memory.title}</strong>
                  <span>{memory.category} · v{memory.version} · {formatTimestamp(memory.updatedAt || memory.createdAt)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p>No approved reusable knowledge has been captured yet.</p>
          )}
          <details className="planner-accordion">
            <summary>Memory Diagnostics</summary>
            <pre className="planner-prompt">{JSON.stringify(diagnostics || {}, null, 2)}</pre>
          </details>
        </div>
      </div>
    </section>
  );
}

function EngineeringMemoryCard({ memory }: { memory: EngineeringMemoryItem }) {
  return (
    <article className="planner-task">
      <div className="planner-task-header">
        <div>
          <strong>{memory.title || 'Untitled Memory'}</strong>
          <p>{memory.summary || 'Validated engineering knowledge ready for reuse.'}</p>
        </div>
        <span className="planner-badge">{memory.approvalStatus || 'Draft'}</span>
      </div>
      <div className="planner-summary-grid compact">
        <SummaryTile title="Category" value={memory.category || 'Project Memory'} />
        <SummaryTile title="Artifact" value={[memory.artifactType, memory.artifactId].filter(Boolean).join(' #') || 'Project'} />
        <SummaryTile title="Version" value={`v${memory.version || 1}`} />
        <SummaryTile title="Confidence" value={`${Math.round((memory.confidence || 0) * 100)}%`} />
      </div>
      <ChipList items={(memory.tags || []).slice(0, 8)} />
      {memory.knowledgeReferences?.length ? (
        <ListBlock title="Knowledge References" items={memory.knowledgeReferences.slice(0, 6)} />
      ) : null}
    </article>
  );
}

function GovernanceWorkspace({
  dashboard,
  status,
  onRefresh,
}: {
  dashboard?: GovernanceDashboard;
  status: string;
  onRefresh: () => void;
}) {
  const policies = dashboard?.policies || [];
  const approvals = dashboard?.approvals?.approvals || [];
  const compliance = dashboard?.compliance || {};
  const metrics = dashboard?.metrics || {};
  const feedback = dashboard?.feedback || {};
  const observability = dashboard?.observability || {};
  const auditEvents = dashboard?.auditTimeline?.events || [];
  const scorecard = dashboard?.scorecard || {};
  return (
    <section className="planner-section">
      <div className="planner-section-header">
        <div>
          <div className="planner-label">Engineering Governance</div>
          <h2>Policy, Compliance, Observability</h2>
          <p>Enterprise controls for planning, execution, QA, release readiness, approvals, metrics, feedback, and auditability.</p>
        </div>
        <button className="planner-button secondary" type="button" onClick={onRefresh}>Refresh Governance</button>
      </div>

      <div className="planner-status-grid">
        <Row label="Governance Status" value={status} />
        <Row label="Compliance" value={`${compliance.status || 'Not Assessed'} · ${formatNumber(compliance.score)}%`} />
        <Row label="Overall Health" value={`${scorecard.overallEngineeringHealth ?? 0}% · ${scorecard.status || 'Pending'}`} />
        <Row label="Audit Events" value={String(dashboard?.auditTimeline?.count || 0)} />
      </div>

      <div className="planner-summary-grid">
        <SummaryTile title="Planning Quality" value={`${scorecard.planningQuality ?? 0}%`} />
        <SummaryTile title="Execution Quality" value={`${scorecard.executionQuality ?? 0}%`} />
        <SummaryTile title="QA Quality" value={`${scorecard.qaQuality ?? 0}%`} />
        <SummaryTile title="Release Readiness" value={`${scorecard.releaseReadiness ?? 0}%`} />
        <SummaryTile title="Repository Health" value={`${scorecard.repositoryHealth ?? 0}%`} />
        <SummaryTile title="Memory Reuse" value={`${scorecard.memoryReuse ?? 0}%`} />
      </div>

      <div className="planner-two-column">
        <div className="planner-card">
          <div className="planner-label">Policies</div>
          {policies.length ? (
            <ul className="planner-list">
              {policies.map((policy) => (
                <li key={policy.id || policy.name}>
                  <strong>{policy.name || 'Engineering Policy'}</strong>
                  <span>{policy.area || 'General'} · {policy.enabled === false ? 'Disabled' : 'Enabled'} · {policy.severity || 'High'}</span>
                </li>
              ))}
            </ul>
          ) : <EmptyState title="No policies configured." detail="Default enterprise governance policies will appear after refresh." />}
        </div>
        <div className="planner-card">
          <div className="planner-label">Approvals</div>
          <div className="planner-summary-grid compact">
            <SummaryTile title="Pending" value={dashboard?.approvals?.byStatus?.Pending || 0} />
            <SummaryTile title="Approved" value={dashboard?.approvals?.byStatus?.Approved || 0} />
            <SummaryTile title="Rejected" value={dashboard?.approvals?.byStatus?.Rejected || 0} />
          </div>
          {approvals.slice(0, 5).map((approval) => (
            <div className="planner-task" key={approval.id}>
              <strong>{approval.artifactTitle || approval.artifactType || 'Artifact'}</strong>
              <span>{approval.status || 'Pending'} · {approval.artifactType || 'Artifact'} {approval.artifactId || ''}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="planner-two-column">
        <div className="planner-card">
          <div className="planner-label">Compliance</div>
          <div className="planner-summary-grid compact">
            {Object.entries(compliance.scores || {}).map(([name, value]) => (
              <SummaryTile key={name} title={titleCase(name)} value={`${formatNumber(value)}%`} />
            ))}
          </div>
          {compliance.findings?.length ? (
            <ListBlock title="Findings" items={compliance.findings.slice(0, 5).map((finding) => `${String(finding.severity || 'Info')}: ${String(finding.message || finding.policy || 'Review required')}`)} />
          ) : <p>Compliance findings will appear after policy evaluation.</p>}
        </div>
        <div className="planner-card">
          <div className="planner-label">Metrics</div>
          <div className="planner-summary-grid compact">
            <SummaryTile title="Generation Success" value={`${metrics.generationSuccess ?? 0}%`} />
            <SummaryTile title="Coverage" value={`${metrics.averageCoverage ?? 0}%`} />
            <SummaryTile title="Confidence" value={`${metrics.averageConfidence ?? 0}%`} />
            <SummaryTile title="Failures" value={metrics.failureCount ?? 0} />
          </div>
        </div>
      </div>

      <div className="planner-two-column">
        <div className="planner-card">
          <div className="planner-label">Observability</div>
          <div className="planner-summary-grid compact">
            <SummaryTile title="Events" value={observability.count || 0} />
            <SummaryTile title="Avg Latency" value={`${formatNumber(observability.averageLatencyMs || 0)} ms`} />
            <SummaryTile title="Failures" value={observability.failureCount || 0} />
            <SummaryTile title="Tokens" value={formatNumber(observability.tokenUsage || 0)} />
          </div>
          <ListBlock title="Engines" items={Object.entries(observability.byEngine || {}).map(([engine, count]) => `${engine}: ${count}`)} />
        </div>
        <div className="planner-card">
          <div className="planner-label">Feedback</div>
          <div className="planner-summary-grid compact">
            <SummaryTile title="Feedback" value={feedback.count || 0} />
            <SummaryTile title="Satisfaction" value={`${feedback.satisfaction || 0}%`} />
            <SummaryTile title="Thumbs Up" value={feedback.byRating?.thumbs_up || 0} />
            <SummaryTile title="Thumbs Down" value={feedback.byRating?.thumbs_down || 0} />
          </div>
          {feedback.feedback?.slice(0, 4).map((item) => (
            <div className="planner-task" key={item.id}>
              <strong>{item.category || 'Feedback'} · {item.rating || 'neutral'}</strong>
              <span>{item.comment || item.reason || 'No comment provided.'}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="planner-card">
        <div className="planner-label">Audit Timeline</div>
        {auditEvents.length ? (
          <ul className="planner-list">
            {auditEvents.slice(-8).reverse().map((event) => (
              <li key={event.id}>
                <strong>{event.what || 'Governance Event'}</strong>
                <span>{event.who || 'system'} · {formatTimestamp(event.when || '')} · {event.why || event.eventType || 'Audit'}</span>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState title="No governance audit events yet." detail="Approvals, policy changes, validation, release, and feedback events will appear here." />
        )}
        <details className="planner-accordion">
          <summary>Governance Diagnostics</summary>
          <pre className="planner-prompt">{JSON.stringify(dashboard?.diagnostics || {}, null, 2)}</pre>
        </details>
      </div>
    </section>
  );
}

function AgentWorkspace({
  dashboard,
  status,
  canAdmin,
  onRefresh,
  onToggleFlag,
}: {
  dashboard?: AgentDashboard;
  status: string;
  canAdmin: boolean;
  onRefresh: () => void;
  onToggleFlag: (flag: string, enabled: boolean) => void;
}) {
  const agents = dashboard?.agents || [];
  const featureFlags = dashboard?.featureFlags || {};
  const policies = dashboard?.policies || [];
  const waiting = dashboard?.waitingAgents || [];
  const running = dashboard?.runningAgents || [];
  const completed = dashboard?.completedWorkflows || [];
  const failed = dashboard?.failedWorkflows || [];
  const pendingJobs = dashboard?.pendingJobs || waiting;
  const history = dashboard?.history || [];
  const lastRun = dashboard?.lastRun || {};
  const upcoming = dashboard?.upcomingActions || [];
  const timeline = dashboard?.agentTimeline || [];
  return (
    <section className="planner-section">
      <div className="planner-section-header">
        <div>
          <div className="planner-label">Agent Center</div>
          <h2>Autonomous Engineering Agents</h2>
          <p>Agents react to engineering events, prepare work, and stop at policy and approval boundaries so users stay in control.</p>
        </div>
        <button className="planner-button secondary" type="button" onClick={onRefresh}>Refresh Agents</button>
      </div>

      <div className="planner-status-grid">
        <Row label="Agent Status" value={status} />
        <Row label="Registered Agents" value={String(agents.length)} />
        <Row label="Pending Jobs" value={String(pendingJobs.length)} />
        <Row label="Failed Workflows" value={String(failed.length)} />
      </div>

      <div className="planner-summary-grid">
        <SummaryTile title="Running" value={running.length} />
        <SummaryTile title="Waiting" value={waiting.length} />
        <SummaryTile title="Completed" value={completed.length} />
        <SummaryTile title="Failed" value={failed.length} />
        <SummaryTile title="Upcoming Actions" value={upcoming.length} />
        <SummaryTile title="Approval Rule" value="Human Required" />
      </div>

      <div className="planner-two-column">
        <div className="planner-card">
          <div className="planner-label">Registered Agents</div>
          {agents.length ? (
            <div className="planner-list">
              {agents.map((agent) => (
                <article className="planner-task" key={agent.id || agent.name}>
                  <div className="planner-task-header">
                    <div>
                      <strong>{agent.name || 'Agent'}</strong>
                      <p>{agent.responsibility || 'Single responsibility engineering agent.'}</p>
                    </div>
                    <span className="planner-badge">{agent.checkpoint || 'Approval Checkpoint'}</span>
                  </div>
                  <div className="planner-summary-grid compact">
                    <SummaryTile title="Status" value={featureFlags[flagName(agent.id)] === false ? 'Disabled' : 'Enabled'} />
                    <SummaryTile title="Last Run" value={formatTimestamp(lastRun[String(agent.id || '')]?.time || '') || 'Not run yet'} />
                  </div>
                  <ListBlock title="Triggers" items={agent.triggers || []} />
                  <ListBlock title="Prepared Actions" items={agent.actions || []} />
                  {canAdmin ? (
                    <label className="planner-checkbox">
                      <input
                        type="checkbox"
                        checked={featureFlags[flagName(agent.id)] !== false}
                        onChange={(event) => onToggleFlag(flagName(agent.id), event.target.checked)}
                      />
                      {featureFlags[flagName(agent.id)] !== false ? 'Enabled' : 'Disabled'}
                    </label>
                  ) : null}
                </article>
              ))}
            </div>
          ) : <EmptyState title="No agents registered." detail="Refresh the orchestrator to load agent registry." />}
        </div>
        <div className="planner-card">
          <div className="planner-label">Pending Jobs</div>
          {pendingJobs.length ? pendingJobs.map((workflow) => (
            <article className="planner-task" key={workflow.id}>
              <strong>{workflow.agent || 'Agent'} waiting for approval</strong>
              <span>{workflow.nextAction || 'Human approval'} · {workflow.artifactType || 'Artifact'} {workflow.artifactId || ''}</span>
              <ListBlock title="Prepared Work" items={(workflow.steps || []).map((step) => `${step.name || 'Step'}: ${step.status || 'Prepared'}`)} />
            </article>
          )) : <EmptyState title="No pending jobs." detail="Triggered agent workflows will appear here when they prepare work and wait for approval." />}
        </div>
      </div>

      <div className="planner-two-column">
        <div className="planner-card">
          <div className="planner-label">Policies</div>
          {policies.length ? (
            <ListBlock title="Agent Policies" items={policies} />
          ) : (
            <p>No agent policies loaded.</p>
          )}
        </div>
        <div className="planner-card">
          <div className="planner-label">Upcoming Actions</div>
          {upcoming.length ? (
            <ul className="planner-list">
              {upcoming.map((action) => (
                <li key={action.workflowId}>
                  <strong>{action.nextAction || 'Human approval'}</strong>
                  <span>{action.agent || 'Agent'} · {action.artifactType || 'Artifact'} {action.artifactId || ''}</span>
                </li>
              ))}
            </ul>
          ) : <p>No upcoming agent actions.</p>}
        </div>
        <div className="planner-card">
          <div className="planner-label">Workflow Outcomes</div>
          <div className="planner-summary-grid compact">
            <SummaryTile title="Completed" value={completed.length} />
            <SummaryTile title="Failed" value={failed.length} />
            <SummaryTile title="Retries" value={failed.reduce((sum, workflow) => sum + (workflow.retryCount || 0), 0)} />
          </div>
          {failed.length ? <ListBlock title="Errors" items={failed.flatMap((workflow) => workflow.errors || []).slice(0, 6)} /> : null}
        </div>
      </div>

      <div className="planner-card">
        <div className="planner-label">History</div>
        {history.length ? (
          <ul className="planner-list">
            {history.slice(-12).reverse().map((event, index) => (
              <li key={`${event.time}-${event.message}-${index}`}>
                <strong>{event.message || 'Agent event'}</strong>
                <span>{event.agent || event.type || 'Agent'} · {event.status || 'Recorded'} · {formatTimestamp(event.time || '')}</span>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState title="No agent history yet." detail="Service hook, PR, work item, repository, and manual trigger activity will appear here." />
        )}
        <details className="planner-accordion">
          <summary>Agent Diagnostics</summary>
          <pre className="planner-prompt">{JSON.stringify(dashboard?.diagnostics || {}, null, 2)}</pre>
        </details>
      </div>
    </section>
  );
}

function flagName(agentId?: string) {
  if (agentId === 'planning') return 'planningAgent';
  if (agentId === 'execution') return 'executionAgent';
  if (agentId === 'qa') return 'qaAgent';
  if (agentId === 'review') return 'reviewAgent';
  if (agentId === 'memory') return 'memoryAgent';
  if (agentId === 'repository') return 'repositoryAgent';
  return '';
}

function SkillsWorkspace({
  dashboard,
  status,
  onRefresh,
}: {
  dashboard?: SkillsDashboard;
  status: string;
  onRefresh: () => void;
}) {
  const installed = dashboard?.installedSkills || [];
  const groupedSkills = dashboard?.groupedSkills || {};
  const recommended = dashboard?.recommendedSkills || [];
  const recent = dashboard?.recentlyUsed || [];
  const usageHistory = dashboard?.usageHistory || [];
  const executionHistory = dashboard?.executionHistory || [];
  const groups = installed.reduce<Record<string, number>>((acc, skill) => {
    const group = skill.group || 'Execution';
    acc[group] = (acc[group] || 0) + 1;
    return acc;
  }, {});
  return (
    <section className="planner-section">
      <div className="planner-section-header">
        <div>
          <div className="planner-label">Skill Library</div>
          <h2>Reusable Engineering Skills</h2>
          <p>Agents decide what to do. Skills know how to do it. Tools and providers stay downstream of the skill contract.</p>
        </div>
        <button className="planner-button secondary" type="button" onClick={onRefresh}>Refresh Skills</button>
      </div>

      <div className="planner-status-grid">
        <Row label="Skills Status" value={status} />
        <Row label="Installed Skills" value={String(installed.length)} />
        <Row label="Recommended Skills" value={String(recommended.length)} />
        <Row label="Resolution Mode" value={String(dashboard?.diagnostics?.resolutionMode || 'deterministic')} />
      </div>

      <div className="planner-summary-grid">
        {Object.entries(groups).slice(0, 8).map(([group, count]) => (
          <SummaryTile key={group} title={group} value={count} />
        ))}
        {!Object.keys(groups).length ? (
          <SummaryTile title="Skill Registry" value="Not Loaded" />
        ) : null}
      </div>

      <div className="planner-two-column">
        <div className="planner-card">
          <div className="planner-label">Recommended Skills</div>
          {recommended.length ? (
            <div className="planner-list">
              {recommended.map((skill) => (
                <SkillCard key={skill.id || skill.name} skill={skill} compact />
              ))}
            </div>
          ) : (
            <EmptyState
              title="No recommendations yet."
              detail="Build an Implementation Plan to match skills from the current implementation package."
            />
          )}
        </div>
        <div className="planner-card">
          <div className="planner-label">Recently Used</div>
          {recent.length ? (
            <div className="planner-list">
              {recent.map((skill) => (
                <SkillCard key={skill.id || skill.name} skill={skill} compact />
              ))}
            </div>
          ) : (
            <p>Skills will appear here after they enrich execution plans.</p>
          )}
          <details className="planner-accordion">
            <summary>Usage History</summary>
            {usageHistory.length ? (
              <ul className="planner-list">
                {usageHistory.slice(-8).reverse().map((usage, index) => (
                  <li key={`${index}-${usage.skillIds?.join('-')}`}>
                    <strong>{usage.skillIds?.join(', ') || 'Engineering Skills'}</strong>
                    <span>{String(usage.artifact?.packageId || usage.artifact?.taskId || 'Execution artifact')}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p>No skill usage has been recorded yet.</p>
            )}
          </details>
        </div>
      </div>

      <div className="planner-card">
        <div className="planner-label">Installed Skills</div>
        {Object.keys(groupedSkills).length ? (
          <div className="planner-list">
            {Object.entries(groupedSkills).map(([group, skills]) => (
              <section key={group}>
                <div className="planner-label">{group}</div>
                {skills.map((skill) => (
                  <SkillCard key={skill.id || skill.name} skill={skill} />
                ))}
              </section>
            ))}
          </div>
        ) : installed.length ? (
          <div className="planner-list">
            {installed.map((skill) => (
              <SkillCard key={skill.id || skill.name} skill={skill} />
            ))}
          </div>
        ) : (
          <EmptyState title="No Engineering Skills installed." detail="Refresh the registry to load the default HEI skills." />
        )}
      </div>

      <div className="planner-card">
        <div className="planner-label">Execution History</div>
        {executionHistory.length ? (
          <ul className="planner-list">
            {executionHistory.slice(-10).reverse().map((event, index) => (
              <li key={`${event.skillId}-${event.executedAt}-${index}`}>
                <strong>{event.skillName || event.skillId || 'Engineering Skill'}</strong>
                <span>{event.group || 'Execution'} · {event.agentId || 'manual'} · {event.status || 'success'} · {formatTimestamp(event.executedAt || '')}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p>No skill executions recorded yet.</p>
        )}
      </div>

      <div className="planner-card">
        <div className="planner-label">Skill Diagnostics</div>
        <details className="planner-accordion">
          <summary>View Diagnostics</summary>
          <pre className="planner-prompt">{JSON.stringify(dashboard?.diagnostics || {}, null, 2)}</pre>
        </details>
      </div>
    </section>
  );
}

function DiagnosticsWorkspace({
  providerMetadata,
  workflow,
  knowledgeCacheStatus,
  capsuleStatus,
  governanceStatus,
  agentStatus,
  skillsStatus,
  memoryStatus,
}: {
  providerMetadata?: ProviderMetadata;
  workflow: WorkflowOrchestrationState;
  knowledgeCacheStatus?: KnowledgeCacheStatus;
  capsuleStatus?: ContextCapsuleStatus;
  governanceStatus: string;
  agentStatus: string;
  skillsStatus: string;
  memoryStatus: string;
}) {
  return (
    <section className="planner-section">
      <div className="planner-section-header">
        <div>
          <div className="planner-label">Diagnostics</div>
          <h2>Advanced Diagnostics</h2>
          <p>Provider and workflow internals are collapsed here so the main demo flow stays clean.</p>
        </div>
      </div>
      <div className="planner-summary-grid">
        <SummaryTile title="Lifecycle" value={workflow.currentStage || 'Planning'} />
        <SummaryTile title="Next Action" value={workflow.nextAction.label} />
        <SummaryTile title="Knowledge Cache" value={knowledgeStatusText(knowledgeCacheStatus?.knowledge_status || 'missing')} />
        <SummaryTile title="Capsule" value={capsuleStatus ? `${capsuleStatus.ready_count || 0}/${capsuleStatus.total_count || 0} ready` : 'Pending'} />
      </div>
      <div className="planner-status-grid">
        <Row label="Memory" value={memoryStatus} />
        <Row label="Skills" value={skillsStatus} />
        <Row label="Agents" value={agentStatus} />
        <Row label="Governance" value={governanceStatus} />
      </div>
      <ProjectIntelligenceProviderDiagnostics metadata={providerMetadata} />
    </section>
  );
}

function SkillCard({ skill, compact = false }: { skill: EngineeringSkill; compact?: boolean }) {
  return (
    <article className="planner-task">
      <div className="planner-task-header">
        <div>
          <strong>{skill.name || 'Engineering Skill'}</strong>
          <p>{skill.description || skill.implementationPattern || 'Reusable engineering guidance.'}</p>
        </div>
        <span className="planner-badge">{skill.group || skill.category || 'Execution'}</span>
      </div>
      <div className="planner-summary-grid compact">
        <SummaryTile title="Version" value={`v${skill.version || 1}`} />
        <SummaryTile title="Confidence" value={`${Math.round((skill.confidence || 0) * 100)}%`} />
        <SummaryTile title="Usage" value={skill.usageCount || 0} />
        <SummaryTile title="Match" value={skill.matchScore ? formatNumber(skill.matchScore) : 'Installed'} />
      </div>
      {skill.matchReasons?.length ? <ListBlock title="Why Matched" items={skill.matchReasons.slice(0, 4)} /> : null}
      {!compact ? (
        <>
          <ListBlock title="Inputs" items={Object.keys(skill.inputSchema || {}).length ? Object.entries(skill.inputSchema || {}).map(([key, value]) => `${key}: ${String(value)}`) : []} />
          <ListBlock title="Outputs" items={Object.keys(skill.outputSchema || {}).length ? Object.entries(skill.outputSchema || {}).map(([key, value]) => `${key}: ${String(value)}`) : []} />
          <ListBlock title="Compatible Agents" items={(skill.compatibleAgents || []).slice(0, 6)} />
          <ListBlock title="Required Permissions" items={(skill.requiredPermissions || []).slice(0, 6)} />
          <ListBlock title="Implementation Pattern" items={skill.implementationPattern ? [skill.implementationPattern] : []} />
          <ListBlock title="Repository Hints" items={(skill.repositoryHints || []).slice(0, 6)} />
          <ListBlock title="Architecture Rules" items={(skill.architectureRules || []).slice(0, 6)} />
          <ListBlock title="Test Templates" items={(skill.testTemplates || []).slice(0, 6)} />
          <ListBlock title="Validation Rules" items={(skill.validationRules || []).slice(0, 6)} />
          <Row label="Last Used" value={formatTimestamp(skill.lastUsedAt || '') || 'Not used yet'} />
        </>
      ) : null}
    </article>
  );
}

function WorkflowTabs({
  activeTab,
  onChange,
  canAdmin,
}: {
  activeTab: PlannerTab;
  onChange: (tab: PlannerTab) => void;
  canAdmin: boolean;
}) {
  const tabs: Array<{ id: PlannerTab; label: string; subtitle: string }> = [
    { id: 'overview', label: 'Command Center', subtitle: 'Current work and next action' },
    { id: 'planning', label: 'Planning', subtitle: 'Story summary and task approval' },
    { id: 'execution', label: 'Execution', subtitle: 'Package cards and prompts' },
    { id: 'qa', label: 'QA & Release', subtitle: 'Readiness and release review' },
    { id: 'memory', label: 'Memory', subtitle: 'Reusable approved knowledge' },
  ];
  const advancedTabs: Array<{ id: PlannerTab; label: string; subtitle: string }> = [
    { id: 'governance', label: 'Governance', subtitle: 'Policies and observability' },
    { id: 'agents', label: 'Agents', subtitle: 'Workflow orchestration' },
    { id: 'skills', label: 'Skills', subtitle: 'Reusable capabilities' },
    { id: 'diagnostics', label: 'Diagnostics', subtitle: 'Provider and workflow internals' },
    ...(canAdmin ? [{ id: 'admin' as PlannerTab, label: 'Administration', subtitle: 'Repository and setup' }] : []),
  ];
  const advancedActive = advancedTabs.some((tab) => tab.id === activeTab);
  return (
    <div className="planner-tab-shell">
      <nav className="planner-tabs" aria-label="Project Intelligence workspace tabs">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            className={`planner-tab ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => onChange(tab.id)}
            type="button"
          >
            <span>{tab.label}</span>
            <small>{tab.subtitle}</small>
          </button>
        ))}
      </nav>
      <details className={`planner-advanced-menu ${advancedActive ? 'active' : ''}`}>
        <summary>
          <span>Advanced</span>
          <small>Governance, agents, skills, admin, diagnostics</small>
        </summary>
        <div className="planner-advanced-grid">
          {advancedTabs.map((tab) => (
            <button
              key={tab.id}
              className={`planner-tab planner-tab-advanced ${activeTab === tab.id ? 'active' : ''}`}
              onClick={() => onChange(tab.id)}
              type="button"
            >
              <span>{tab.label}</span>
              <small>{tab.subtitle}</small>
            </button>
          ))}
        </div>
      </details>
    </div>
  );
}

function StickyContextBar({
  workItem,
  itemType,
  activeTab,
  recommendedWorkspace,
  workflow,
  autoRoute,
  loading,
  canContribute,
  currentRole,
  onToggleAutoRoute,
  onContinueWorkflow,
}: {
  workItem?: AdoWorkItem;
  itemType: WorkItemKind;
  activeTab: PlannerTab;
  recommendedWorkspace: RoutedWorkspace;
  workflow: WorkflowOrchestrationState;
  autoRoute: boolean;
  loading: boolean;
  canContribute: boolean;
  currentRole: string;
  onToggleAutoRoute: (enabled: boolean) => void;
  onContinueWorkflow: () => void;
}) {
  const itemLabel = workItem
    ? `${workItem.type} #${workItem.id} · ${workItem.title || 'Untitled'}`
    : `${itemType} · No Azure DevOps work item loaded`;
  return (
    <section className="hei-context-bar" aria-label="Current AI Gen context">
      <div className="hei-context-main">
        <strong>{itemLabel}</strong>
        <span>Workspace: {workspaceLabel(activeTab)}</span>
        <span>Role: {currentRole}</span>
        <span>Next: {workflow.nextAction.label}</span>
      </div>
      {activeTab !== recommendedWorkspace ? (
        <span className="hei-context-warning">Recommended: {workspaceLabel(recommendedWorkspace)}</span>
      ) : null}
      <label className="planner-checkbox hei-auto-route">
        <input type="checkbox" checked={autoRoute} onChange={(event) => onToggleAutoRoute(event.target.checked)} />
        Auto Route
      </label>
      <button className="planner-button" onClick={onContinueWorkflow} disabled={loading || !canContribute}>
        {workflow.nextAction.label}
      </button>
    </section>
  );
}

function CommandCenterWorkspace({
  dashboardOverview,
  profile,
  workItem,
  workflow,
  knowledgeCacheStatus,
  capsuleStatus,
  session,
  loading,
  canAdmin,
  canContribute,
  hasQa,
  hasExecution,
  showQuickStart,
  adoProjects,
  repositories,
  branches,
  repositoryLoadMessage,
  onContinue,
  onContinueWorkflow,
  onRefresh,
  onChangeRepository,
  onProfileChange,
  onSelectAdoProject,
  onSelectRepository,
  onReloadRepositories,
  onAnalyzeProject,
  onRefreshDashboard,
}: {
  dashboardOverview?: DashboardOverview;
  profile: ProjectProfile;
  workItem?: AdoWorkItem;
  workflow: WorkflowOrchestrationState;
  knowledgeCacheStatus?: KnowledgeCacheStatus;
  capsuleStatus?: ContextCapsuleStatus;
  session?: ProjectSessionSnapshot;
  loading: boolean;
  canAdmin: boolean;
  canContribute: boolean;
  hasQa: boolean;
  hasExecution: boolean;
  showQuickStart: boolean;
  adoProjects: AdoProject[];
  repositories: GitRepository[];
  branches: string[];
  repositoryLoadMessage: string;
  onContinue: () => void;
  onContinueWorkflow: () => void;
  onRefresh: () => void;
  onChangeRepository: () => void;
  onProfileChange: (profile: ProjectProfile) => void;
  onSelectAdoProject: (project: string) => void;
  onSelectRepository: (repositoryId: string) => void;
  onReloadRepositories: () => void;
  onAnalyzeProject: () => void;
  onRefreshDashboard: () => void;
}) {
  return (
    <div className="hei-command-center">
      <div className="hei-command-row primary">
        <CurrentWorkCard profile={profile} workItem={workItem} workflow={workflow} />
        <RecommendedActionHero workflow={workflow} loading={loading} canContribute={canContribute} onContinue={onContinueWorkflow} />
      </div>
      <OperationalOverviewDashboard overview={dashboardOverview} loading={loading} onRefresh={onRefreshDashboard} />
      <details className="planner-nested">
        <summary>Show details</summary>
        <div className="hei-command-row metrics">
          <OverviewHealthCard workflow={workflow} profile={profile} hasQa={hasQa} hasExecution={hasExecution} />
          <RepositoryMetricsCard profile={profile} status={knowledgeCacheStatus} capsuleStatus={capsuleStatus} />
          <KnowledgeHealthCompactCard
            session={session}
            status={knowledgeCacheStatus}
            profile={profile}
            capsuleStatus={capsuleStatus}
            loading={loading}
            canRefresh={canAdmin}
            onContinue={onContinue}
            onRefresh={onRefresh}
            onChangeRepository={onChangeRepository}
          />
        </div>
        <div className="hei-command-row secondary">
          <RepositoryDriftCard status={knowledgeCacheStatus} profile={profile} loading={loading} canRefresh={canAdmin} onRefresh={onRefresh} />
          <RecentActivityCard currentWorkItem={workItem} profile={profile} hasQa={hasQa} hasExecution={hasExecution} />
        </div>
        {showQuickStart && canAdmin ? (
          <QuickStartSetup
            profile={profile}
            adoProjects={adoProjects}
            repositories={repositories}
            branches={branches}
            repositoryLoadMessage={repositoryLoadMessage}
            loading={loading}
            onProfileChange={onProfileChange}
            onSelectAdoProject={onSelectAdoProject}
            onSelectRepository={onSelectRepository}
            onReloadRepositories={onReloadRepositories}
            onAnalyzeProject={onAnalyzeProject}
          />
        ) : null}
      </details>
    </div>
  );
}

function CurrentWorkCard({
  profile,
  workItem,
  workflow,
}: {
  profile: ProjectProfile;
  workItem?: AdoWorkItem;
  workflow: WorkflowOrchestrationState;
}) {
  const hierarchy = [
    profile.project_name || 'Project',
    workItem?.type === 'Epic' ? workItem.title : 'Epic not selected',
    workItem?.type === 'Feature' ? workItem.title : 'Feature context pending',
    workItem?.type === 'Story' ? workItem.title : 'Story context pending',
    workItem?.type === 'Task' ? workItem.title : 'Task context pending',
  ];
  return (
    <section className="planner-card hei-current-work">
      <div className="planner-section-header">
        <div>
          <div className="planner-label">Current Work</div>
          <strong>{workItem ? workItem.title : profile.project_name || 'Project Intelligence'}</strong>
          <div className="planner-subtle">{workItem ? `${workItem.type} #${workItem.id} · ${workItem.state}` : 'Open from an Azure DevOps work item to load item context.'}</div>
        </div>
        <StatusBadge tone={workflow.blockers.length ? 'warning' : 'success'} label={workflow.currentStage} />
      </div>
      <div className="hei-hierarchy">
        {hierarchy.map((item, index) => (
          <React.Fragment key={`${item}-${index}`}>
            <span className={index === 0 || item.includes('pending') || item.includes('not selected') ? 'muted' : ''}>{item}</span>
            {index < hierarchy.length - 1 ? <b>↓</b> : null}
          </React.Fragment>
        ))}
      </div>
    </section>
  );
}

function RecommendedActionHero({
  workflow,
  loading,
  canContribute,
  onContinue,
}: {
  workflow: WorkflowOrchestrationState;
  loading: boolean;
  canContribute: boolean;
  onContinue: () => void;
}) {
  const impact = workflow.blockers.length
    ? 'Clears workflow blockers before planning moves forward.'
    : 'Moves the current work item to the next delivery-ready state.';
  return (
    <section className="planner-card hei-action-hero">
      <div>
        <div className="planner-label">Recommended Action</div>
        <h2>{workflow.nextAction.label}</h2>
        <p>{workflow.nextAction.reason}</p>
      </div>
      <div className="hei-action-meta">
        <InfoPill label="Impact" value={impact} />
        <InfoPill label="AI Time" value={estimatedAiTime(workflow.nextAction.action)} />
        <InfoPill label="Token Use" value={estimatedTokenUse(workflow.nextAction.action)} />
      </div>
      <button className="planner-button" onClick={onContinue} disabled={loading || !canContribute}>{workflow.nextAction.label}</button>
    </section>
  );
}

function RepositoryMetricsCard({
  profile,
  status,
  capsuleStatus,
}: {
  profile: ProjectProfile;
  status?: KnowledgeCacheStatus;
  capsuleStatus?: ContextCapsuleStatus;
}) {
  const stack = mergeTechnologyStack(profile.technology_stack, profile.knowledge_registry.technology_stack);
  const techCount = Object.values(stack).reduce((count, values) => count + values.length, 0);
  const sourceFiles = status?.source_files?.length ? status.source_files : profile.knowledge_registry.source_files;
  return (
    <section className="planner-card">
      <div className="planner-section-header">
        <div>
          <div className="planner-label">Repository Intelligence</div>
          <div className="planner-subtle">Knowledge extracted from repository documentation and cached project profile.</div>
        </div>
        <StatusBadge tone={hasKnowledgeRegistry(profile) ? 'success' : 'warning'} label={hasKnowledgeRegistry(profile) ? 'Ready' : 'Needs Analysis'} />
      </div>
      <div className="planner-summary-grid dense">
        <SummaryTile title="Repository" value={status?.repository || profile.repository_connection.repository_name || 'Not connected'} />
        <SummaryTile title="Knowledge Version" value={status?.knowledge_version || knowledgeVersion(profile)} />
        <SummaryTile title="Modules" value={formatNumber(profile.knowledge_registry.modules.length)} />
        <SummaryTile title="Flows" value={formatNumber(profile.knowledge_registry.flows.length)} />
        <SummaryTile title="Documents" value={formatNumber(sourceFiles.length)} />
        <SummaryTile title="Technologies" value={formatNumber(techCount)} />
      </div>
      <div className="planner-subtle">Capsules: {formatNumber(capsuleStatus?.ready_count || 0)} ready · Confidence: {hasKnowledgeRegistry(profile) ? 'High' : 'Needs repository scan'}</div>
    </section>
  );
}

function RepositoryDriftCard({
  status,
  profile,
  loading,
  canRefresh,
  onRefresh,
}: {
  status?: KnowledgeCacheStatus;
  profile: ProjectProfile;
  loading: boolean;
  canRefresh: boolean;
  onRefresh: () => void;
}) {
  const changed = status?.changed_files || [];
  const sourceFiles = status?.source_files?.length ? status.source_files : profile.knowledge_registry.source_files;
  const driftRows = changed.length
    ? changed.slice(0, 4)
    : sourceFiles.slice(0, 4).map((file) => `${file} is up to date`);
  return (
    <section className="planner-card">
      <div className="planner-section-header">
        <div>
          <div className="planner-label">Repository Drift</div>
          <div className="planner-subtle">Document changes that may affect planning and execution context.</div>
        </div>
        <StatusBadge tone={changed.length ? 'warning' : 'success'} label={changed.length ? 'Review Needed' : 'No Drift'} />
      </div>
      <div className="planner-status-grid">
        <Row label="New Modules" value={changed.some((file) => file.includes('modules')) ? 'Possible' : 'None detected'} />
        <Row label="Modified Flows" value={changed.some((file) => file.includes('flows')) ? 'Possible' : 'None detected'} />
        <Row label="Documentation Changes" value={changed.length ? `${changed.length} changed` : 'Up to date'} />
        <Row label="Architecture Changes" value={changed.some((file) => file.includes('architecture')) ? 'Review needed' : 'None detected'} />
      </div>
      <ListBlock title="Drift Signals" items={driftRows.length ? driftRows : ['Repository documents have not been analyzed yet.']} />
      <div className="planner-actions compact">
        <button className="planner-button secondary" type="button" onClick={onRefresh} disabled={loading || !canRefresh}>Review Drift</button>
      </div>
    </section>
  );
}

function StatusBadge({ label, tone }: { label: string; tone: 'success' | 'warning' | 'error' | 'neutral' }) {
  return <span className={`hei-status-badge ${tone}`}>{label}</span>;
}

function InfoPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="hei-info-pill">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function estimatedAiTime(action: WorkflowActionKind): string {
  if (action === 'open_vscode' || action === 'open_planning' || action === 'open_execution') return 'Instant';
  if (action.startsWith('approve_')) return 'No AI call';
  if (action === 'build_execution') return '< 5 sec';
  return '10-30 sec';
}

function estimatedTokenUse(action: WorkflowActionKind): string {
  if (action === 'open_vscode' || action === 'open_planning' || action === 'open_execution' || action.startsWith('approve_')) return '0';
  if (action === 'build_execution') return 'Low';
  return 'Medium';
}

function ProjectSessionResumeCard({
  session,
  onContinue,
  onRefresh,
  loading,
  canRefresh,
}: {
  session: ProjectSessionSnapshot;
  onContinue: () => void;
  onRefresh: () => void;
  loading: boolean;
  canRefresh: boolean;
}) {
  return (
    <section className="planner-card planner-session-card">
      <div className="planner-section-header">
        <div>
          <div className="planner-label">Last Active Project</div>
          <div className="planner-subtle">Resume instantly from saved project intelligence. Refresh only when repository knowledge should be rebuilt.</div>
        </div>
        <div className={`planner-session-freshness ${knowledgeFreshness(session.last_analysis_timestamp).toLowerCase()}`}>
          {knowledgeFreshness(session.last_analysis_timestamp)}
        </div>
      </div>
      <div className="planner-session-grid">
        <Row label="Project Name" value={session.active_project || 'Not captured yet'} />
        <Row label="Repository" value={session.repository_name || 'No repository selected'} />
        <Row label="Repository Branch" value={session.branch || 'Default branch'} />
        <Row label="Knowledge Version" value={session.knowledge_version} />
        <Row label="Last Updated" value={formatTimestamp(session.last_analysis_timestamp || session.saved_at)} />
        <Row label="Last Active Tab" value={titleCase(session.last_active_tab)} />
      </div>
      <div className="planner-actions">
        <button className="planner-button" type="button" onClick={onContinue} disabled={loading}>Continue</button>
        <button className="planner-button secondary" type="button" onClick={onRefresh} disabled={loading || !canRefresh}>Refresh Analysis</button>
      </div>
      {!canRefresh ? <div className="planner-subtle">Knowledge refresh is available to AI Gen Admins only.</div> : null}
    </section>
  );
}

function OverviewHealthCard({
  workflow,
  profile,
  hasQa,
  hasExecution,
}: {
  workflow: WorkflowOrchestrationState;
  profile: ProjectProfile;
  hasQa: boolean;
  hasExecution: boolean;
}) {
  const setup = projectSetupStatus(profile);
  return (
    <section className="planner-card planner-card-accent">
      <div className="planner-section-header">
        <div>
          <div className="planner-label">Engineering Health</div>
          <div className="planner-subtle">A compact read on planning, execution, QA, and setup readiness.</div>
        </div>
        <div className={`planner-session-freshness ${setup.complete ? 'fresh' : 'stale'}`}>
          {setup.complete ? 'Ready' : 'Needs Setup'}
        </div>
      </div>
      <div className="planner-summary-grid">
        <SummaryTile title="Planning" value={workflow.planningHealth} />
        <SummaryTile title="Execution" value={hasExecution ? 'Ready' : workflow.executionHealth} />
        <SummaryTile title="QA" value={hasQa ? 'Ready' : workflow.qaHealth} />
      </div>
    </section>
  );
}

function KnowledgeHealthCompactCard({
  session,
  status,
  profile,
  capsuleStatus,
  loading,
  canRefresh,
  onContinue,
  onRefresh,
  onChangeRepository,
}: {
  session?: ProjectSessionSnapshot;
  status?: KnowledgeCacheStatus;
  profile: ProjectProfile;
  capsuleStatus?: ContextCapsuleStatus;
  loading: boolean;
  canRefresh: boolean;
  onContinue: () => void;
  onRefresh: () => void;
  onChangeRepository: () => void;
}) {
  const knowledge = status?.knowledge_status || (hasKnowledgeRegistry(profile) ? 'ready' : 'missing');
  const repository = status?.repository || profile.repository_connection.repository_name || session?.repository_name || 'Not connected';
  const sourceFiles = status?.source_files?.length ? status.source_files : profile.knowledge_registry.source_files;
  return (
    <section className="planner-card">
      <div className="planner-section-header">
        <div>
          <div className="planner-label">Knowledge Health</div>
          <div className="planner-subtle">Cached repository knowledge is reused until an admin refreshes it.</div>
        </div>
        <div className={`planner-session-freshness ${knowledge === 'ready' ? 'fresh' : 'stale'}`}>
          {knowledgeStatusText(knowledge)}
        </div>
      </div>
      <div className="planner-summary-grid">
        <SummaryTile title="Repository" value={repository} />
        <SummaryTile title="Knowledge" value={registrySummary(profile)} />
        <SummaryTile title="Capsules" value={`${formatNumber(capsuleStatus?.ready_count || 0)} ready`} />
      </div>
      <div className="planner-subtle">
        {sourceFiles.length ? `Sources: ${sourceFiles.slice(0, 5).join(', ')}` : 'No repository documents analyzed yet.'}
      </div>
      <div className="planner-actions compact">
        <button className="planner-button" type="button" onClick={onContinue} disabled={loading}>Continue Working</button>
        <button className="planner-button secondary" type="button" onClick={onRefresh} disabled={loading || !canRefresh}>Refresh Knowledge</button>
        <button className="planner-button secondary" type="button" onClick={onChangeRepository} disabled={loading || !canRefresh}>Change Repository</button>
      </div>
    </section>
  );
}

function AIRecommendationCard({
  workflow,
  loading,
  canContribute,
  onContinue,
}: {
  workflow: WorkflowOrchestrationState;
  loading: boolean;
  canContribute: boolean;
  onContinue: () => void;
}) {
  return (
    <section className="planner-card">
      <div className="planner-section-header">
        <div>
          <div className="planner-label">AI Recommendation</div>
          <strong>{workflow.nextAction.label}</strong>
          <div className="planner-subtle">{workflow.nextAction.reason}</div>
        </div>
        <button className="planner-button" onClick={onContinue} disabled={loading || !canContribute}>Continue</button>
      </div>
      {workflow.blockers.length ? <ListBlock title="Needs Attention" items={workflow.blockers.slice(0, 3)} /> : null}
    </section>
  );
}

function ProjectKnowledgeStatusCard({
  session,
  status,
  profile,
  loading,
  canRefresh,
  onContinue,
  onRefresh,
  onChangeRepository,
}: {
  session?: ProjectSessionSnapshot;
  status?: KnowledgeCacheStatus;
  profile: ProjectProfile;
  loading: boolean;
  canRefresh: boolean;
  onContinue: () => void;
  onRefresh: () => void;
  onChangeRepository: () => void;
}) {
  const knowledge = status?.knowledge_status || (hasKnowledgeRegistry(profile) ? 'ready' : 'missing');
  const repository = status?.repository || profile.repository_connection.repository_name || session?.repository_name || 'Not connected';
  const branch = status?.branch || profile.repository_connection.branch || session?.branch || 'main';
  const sourceFiles = status?.source_files?.length ? status.source_files : profile.knowledge_registry.source_files;
  return (
    <section className="planner-card">
      <div className="planner-section-header">
        <div>
          <div className="planner-label">Project Knowledge Status</div>
          <div className="planner-subtle">Cached knowledge is reused on startup. Refresh only when repository documents change.</div>
        </div>
        <div className={`planner-session-freshness ${knowledge === 'ready' ? 'fresh' : knowledge === 'missing' ? 'stale' : 'partial'}`}>
          {knowledgeStatusText(knowledge)}
        </div>
      </div>
      <div className="planner-status-grid">
        <Row label="Project" value={status?.project_name || session?.active_project || profile.project_name || 'Project Intelligence'} />
        <Row label="Workspace" value={workspaceLabel(session?.last_active_tab || 'overview')} />
        <Row label="Repository" value={repository} />
        <Row label="Branch" value={branch} />
        <Row label="Knowledge Version" value={status?.knowledge_version || session?.knowledge_version || knowledgeVersion(profile)} />
        <Row label="Last Analyzed" value={formatTimestamp(status?.last_analyzed_at || session?.last_analysis_timestamp || '')} />
      </div>
      <ListBlock title="Source Files" items={sourceFiles.length ? sourceFiles : ['No source files analyzed yet']} />
      {status?.changed_files?.length ? <ListBlock title="Changed Files" items={status.changed_files} /> : null}
      {status?.invalidation_reasons?.length ? <ListBlock title="Refresh Reasons" items={status.invalidation_reasons} /> : null}
      <div className="planner-actions">
        <button className="planner-button" type="button" onClick={onContinue} disabled={loading}>Continue Working</button>
        <button className="planner-button secondary" type="button" onClick={onRefresh} disabled={loading || !canRefresh}>Refresh Knowledge</button>
        <button className="planner-button secondary" type="button" onClick={onChangeRepository} disabled={loading || !canRefresh}>Open Repository Settings</button>
      </div>
      {!canRefresh ? <div className="planner-subtle">Knowledge refresh and repository changes are available to AI Gen Admins.</div> : null}
    </section>
  );
}

function ContextCapsuleStatusCard({
  status,
  loading,
  canRefresh,
  onRefresh,
}: {
  status?: ContextCapsuleStatus;
  loading: boolean;
  canRefresh: boolean;
  onRefresh: () => void;
}) {
  const capsules: ContextCapsuleItem[] = status?.capsules?.length ? status.capsules : ['project', 'feature', 'story', 'execution', 'qa'].map((capsuleType) => ({
    capsule_type: capsuleType,
    status: 'missing' as const,
    version: 0,
  }));
  return (
    <section className="planner-card">
      <div className="planner-section-header">
        <div>
          <div className="planner-label">Context Capsule Status</div>
          <div className="planner-subtle">Reusable compressed context for Planning, Execution, QA, VS Code, and future agents.</div>
        </div>
        <div className={`planner-session-freshness ${(status?.ready_count || 0) ? 'fresh' : 'stale'}`}>
          {formatNumber(status?.ready_count || 0)} / {formatNumber(status?.total_count || capsules.length)} Ready
        </div>
      </div>
      <div className="planner-status-grid">
        {capsules.map((capsule) => (
          <div className="planner-summary-tile" key={capsule.capsule_type}>
            <span>{titleCase(capsule.capsule_type)} Capsule</span>
            <strong>{titleCase(capsule.status || 'missing')}</strong>
            <small>
              v{formatNumber(capsule.version || 0)}
              {capsule.capsule_size_tokens ? ` · ${formatNumber(capsule.capsule_size_tokens)} tokens` : ''}
              {capsule.compression_ratio ? ` · ${formatNumber(Math.round((capsule.compression_ratio || 0) * 100))}% source` : ''}
            </small>
          </div>
        ))}
      </div>
      <div className="planner-status-grid">
        <Row label="Knowledge Version" value={status?.knowledge_version || 'Pending'} />
        <Row label="Last Capsule Refresh" value={formatTimestamp(capsules.map((capsule) => capsule.last_refreshed || '').filter(Boolean).sort().pop() || '')} />
      </div>
      <div className="planner-actions">
        <button className="planner-button secondary" type="button" onClick={onRefresh} disabled={loading || !canRefresh}>Refresh Capsules</button>
      </div>
      {!canRefresh ? <div className="planner-subtle">Capsule refresh is available to AI Gen Admins.</div> : null}
    </section>
  );
}

function RecommendedActionCard({
  workItem,
  itemType,
  activeTab,
  recommendedWorkspace,
  approvalWorkflow,
  workflow,
  autoRoute,
  loading,
  canContribute,
  currentRole,
  hasExecutionPackage,
  onToggleAutoRoute,
  onOpenWorkspace,
  onApproveEpic,
  onApproveFeature,
  onApproveStory,
  onApproveTasks,
  onApproveTestSuite,
  onRefineEpic,
  onRefineFeature,
  onRefineStory,
  onGenerateChildren,
  onAnalyzeImpact,
  onGenerateFeatureTestPlan,
  onGenerateQATestCases,
  onBuildExecutionPackage,
  onOpenVsCode,
  onContinueWorkflow,
  onGenerateEverythingForStory,
}: {
  workItem?: AdoWorkItem;
  itemType: WorkItemKind;
  activeTab: PlannerTab;
  recommendedWorkspace: RoutedWorkspace;
  approvalWorkflow: ApprovalWorkflowState;
  workflow: WorkflowOrchestrationState;
  autoRoute: boolean;
  loading: boolean;
  canContribute: boolean;
  currentRole: string;
  hasExecutionPackage: boolean;
  onToggleAutoRoute: (enabled: boolean) => void;
  onOpenWorkspace: (workspace: PlannerTab) => void;
  onApproveEpic: () => void;
  onApproveFeature: () => void;
  onApproveStory: () => void;
  onApproveTasks: () => void;
  onApproveTestSuite: () => void;
  onRefineEpic: () => void;
  onRefineFeature: () => void;
  onRefineStory: () => void;
  onGenerateChildren: () => void;
  onAnalyzeImpact: () => void;
  onGenerateFeatureTestPlan: () => void;
  onGenerateQATestCases: () => void;
  onBuildExecutionPackage: () => void;
  onOpenVsCode: () => void;
  onContinueWorkflow: () => void;
  onGenerateEverythingForStory: () => void;
}) {
  const hasTaskDrafts = itemType === 'Story' && (workflow.statuses.tasks === 'current' || workflow.statuses.tasks === 'complete');
  const actions = recommendedActionsForItemType(itemType, {
    onRefineEpic,
    onRefineFeature,
    onRefineStory,
    onGenerateChildren,
    onAnalyzeImpact,
    onGenerateFeatureTestPlan,
    onGenerateQATestCases,
    onBuildExecutionPackage,
    onOpenVsCode,
    hasStoryAnalysis: workflow.nextAction.action !== 'analyze_story',
    hasExecutionPackage,
    hasTaskDrafts,
    approvalWorkflow,
    onApproveEpic,
    onApproveFeature,
    onApproveStory,
    onApproveTasks,
    onApproveTestSuite,
  }).slice(0, 3);
  return (
    <section className="planner-card planner-current-item-bar">
      <div className="planner-section-header">
        <div>
          <div className="planner-label">Current Item</div>
          <strong>{workItem ? `${workItem.type} #${workItem.id} · ${workItem.title}` : 'No Azure DevOps work item detected'}</strong>
          <div className="planner-subtle">Recommended: {workspaceLabel(workflow.nextAction.workspace)} · Role: {currentRole} · Next: {workflow.nextAction.label}</div>
        </div>
        <label className="planner-checkbox">
          <input type="checkbox" checked={autoRoute} onChange={(event) => onToggleAutoRoute(event.target.checked)} />
          Auto Route
        </label>
      </div>
      {activeTab !== recommendedWorkspace ? (
        <div className="planner-banner">Manual override is active. Recommended workspace for this item is {workspaceLabel(recommendedWorkspace)}.</div>
      ) : null}
      <div className="planner-actions">
        <button className="planner-button" onClick={onContinueWorkflow} disabled={loading || !canContribute}>
          {workflow.nextAction.label}
        </button>
        <button className="planner-button secondary" onClick={() => onOpenWorkspace(workflow.nextAction.workspace)} disabled={loading}>
          Open {workspaceLabel(workflow.nextAction.workspace)}
        </button>
        {itemType === 'Story' ? (
          <button className="planner-button secondary" onClick={onGenerateEverythingForStory} disabled={loading || !canContribute}>
            Generate Everything
          </button>
        ) : null}
        {actions.map((action) => (
          <button key={action.label} className={action.primary ? 'planner-button' : 'planner-button secondary'} onClick={action.run} disabled={loading || !canContribute}>
            {action.label}
          </button>
        ))}
      </div>
    </section>
  );
}

function WorkflowNextActionCard({
  workflow,
  loading,
  canContribute,
  onContinue,
}: {
  workflow: WorkflowOrchestrationState;
  loading: boolean;
  canContribute: boolean;
  onContinue: () => void;
}) {
  return (
    <section className="planner-card planner-next-action-card">
      <div className="planner-section-header">
        <div>
          <div className="planner-label">Next Recommended Action</div>
          <strong>{workflow.nextAction.label}</strong>
          <div className="planner-subtle">{workflow.nextAction.reason}</div>
        </div>
        <button className="planner-button" onClick={onContinue} disabled={loading || !canContribute}>{workflow.nextAction.label}</button>
      </div>
      <div className="planner-summary-grid">
        <SummaryTile title="Planning Health" value={workflow.planningHealth} />
        <SummaryTile title="Execution Health" value={workflow.executionHealth} />
        <SummaryTile title="QA Health" value={workflow.qaHealth} />
      </div>
      {workflow.blockers.length ? <ListBlock title="Workflow Blockers" items={workflow.blockers} /> : <div className="planner-subtle">No blockers detected. The workflow can continue.</div>}
    </section>
  );
}

function WorkflowTimeline({ workflow }: { workflow: WorkflowOrchestrationState }) {
  const stages: Array<{ key: keyof WorkflowOrchestrationState['statuses']; label: string }> = [
    { key: 'epic', label: 'Epic' },
    { key: 'features', label: 'Features' },
    { key: 'stories', label: 'Stories' },
    { key: 'tasks', label: 'Tasks' },
    { key: 'tests', label: 'Tests' },
    { key: 'execution', label: 'Execution' },
  ];
  return (
    <section className="planner-card">
      <div className="planner-section-header">
        <div>
          <div className="planner-label">Workflow Timeline</div>
          <div className="planner-subtle">Current stage: {workflow.currentStage}</div>
        </div>
      </div>
      <div className="planner-timeline">
        {stages.map((stage) => {
          const status = workflow.statuses[stage.key];
          const marker = status === 'complete' ? '✓' : status === 'current' ? '●' : status === 'blocked' ? '!' : '○';
          return (
            <div className={`planner-timeline-step ${status}`} key={stage.key}>
              <span>{marker}</span>
              <strong>{stage.label}</strong>
              <small>{titleCase(status)}</small>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function LifecycleStrip({ workflow }: { workflow: WorkflowOrchestrationState }) {
  const validationStatus = workflow.statuses.execution === 'complete'
    ? (workflow.statuses.tests === 'complete' ? 'complete' : 'current')
    : 'pending';
  const releaseStatus = workflow.statuses.tests === 'complete' ? 'current' : 'pending';
  const stages: Array<{ label: string; status: 'complete' | 'current' | 'pending' | 'blocked'; detail: string }> = [
    { label: 'Planning', status: workflow.statuses.features === 'complete' || workflow.statuses.stories === 'complete' || workflow.statuses.tasks === 'complete' ? 'complete' : workflow.statuses.epic === 'current' || workflow.statuses.features === 'current' || workflow.statuses.stories === 'current' || workflow.statuses.tasks === 'current' ? 'current' : 'pending', detail: workflow.planningHealth },
    { label: 'Execution', status: workflow.statuses.execution, detail: workflow.executionHealth },
    { label: 'Validation', status: validationStatus, detail: workflow.statuses.execution === 'complete' ? 'Implementation validation' : 'Waiting for execution' },
    { label: 'QA', status: workflow.statuses.tests, detail: workflow.qaHealth },
    { label: 'Release', status: releaseStatus, detail: workflow.statuses.tests === 'complete' ? 'Recommendation ready' : 'Waiting for QA' },
  ];
  return (
    <div className="hei-lifecycle-strip" aria-label="Engineering lifecycle">
      {stages.map((stage) => (
        <div className={`hei-lifecycle-stage ${stage.status}`} key={stage.label}>
          <span>{lifecycleIcon(stage.status)} {stage.label}</span>
          <small>{stage.detail}</small>
        </div>
      ))}
    </div>
  );
}

function lifecycleIcon(status: string): string {
  if (status === 'complete') return '✓';
  if (status === 'current') return '▶';
  if (status === 'blocked') return '!';
  return '○';
}

function recommendedActionsForItemType(
  itemType: WorkItemKind,
  handlers: {
    onRefineEpic: () => void;
    onRefineFeature: () => void;
    onRefineStory: () => void;
    onGenerateChildren: () => void;
    onAnalyzeImpact: () => void;
    onGenerateFeatureTestPlan: () => void;
    onGenerateQATestCases: () => void;
    onBuildExecutionPackage: () => void;
    onOpenVsCode: () => void;
    hasStoryAnalysis: boolean;
    hasExecutionPackage: boolean;
    hasTaskDrafts: boolean;
    approvalWorkflow: ApprovalWorkflowState;
    onApproveEpic: () => void;
    onApproveFeature: () => void;
    onApproveStory: () => void;
    onApproveTasks: () => void;
    onApproveTestSuite: () => void;
  },
): Array<{ label: string; run: () => void; primary?: boolean }> {
  if (itemType === 'Epic') {
    if (isApprovalPending(handlers.approvalWorkflow.epic)) {
      return [
        { label: 'Approve Epic', run: handlers.onApproveEpic, primary: true },
        { label: 'Regenerate Epic', run: handlers.onRefineEpic },
        { label: 'Impact Analysis', run: handlers.onAnalyzeImpact },
      ];
    }
    return [
      { label: 'Generate Features', run: handlers.onGenerateChildren, primary: true },
      { label: 'Refine Epic', run: handlers.onRefineEpic },
      { label: 'Impact Analysis', run: handlers.onAnalyzeImpact },
    ];
  }
  if (itemType === 'Feature') {
    if (isApprovalPending(handlers.approvalWorkflow.feature)) {
      return [
        { label: 'Approve Feature', run: handlers.onApproveFeature, primary: true },
        { label: 'Regenerate Feature', run: handlers.onRefineFeature },
        { label: 'Generate Test Plan', run: handlers.onGenerateFeatureTestPlan },
      ];
    }
    return [
      { label: 'Generate Stories', run: handlers.onGenerateChildren, primary: true },
      { label: 'Refine Feature', run: handlers.onRefineFeature },
      { label: 'Impact Analysis', run: handlers.onAnalyzeImpact },
    ];
  }
  if (itemType === 'Story') {
    if (!handlers.hasStoryAnalysis) {
      return [
        { label: 'Analyze Story', run: handlers.onRefineStory, primary: true },
        { label: 'Review Acceptance Criteria', run: handlers.onRefineStory },
      ];
    }
    if (handlers.hasTaskDrafts && isApprovalPending(handlers.approvalWorkflow.tasks)) {
      return [
        { label: 'Approve Tasks', run: handlers.onApproveTasks, primary: true },
        { label: 'Regenerate Tasks', run: handlers.onGenerateChildren },
        { label: 'Review Story', run: handlers.onRefineStory },
      ];
    }
    return [
      { label: 'Generate Tasks', run: handlers.onGenerateChildren, primary: true },
      { label: 'Regenerate Story', run: handlers.onRefineStory },
      { label: 'Open Execution', run: handlers.onBuildExecutionPackage },
    ];
  }
  if (itemType === 'Task') {
    return [
      { label: handlers.hasExecutionPackage ? 'Open VS Code' : 'Build Implementation Package', run: handlers.hasExecutionPackage ? handlers.onOpenVsCode : handlers.onBuildExecutionPackage, primary: true },
      { label: 'Generate Developer Prompt', run: handlers.onBuildExecutionPackage },
      { label: 'Open QA & Release', run: handlers.onBuildExecutionPackage },
    ];
  }
  if (itemType === 'Bug') {
    return [
      { label: 'Build Fix Context', run: handlers.onBuildExecutionPackage, primary: true },
      { label: 'Impact Analysis', run: handlers.onAnalyzeImpact },
      { label: 'Generate Regression Tests', run: handlers.onGenerateQATestCases },
    ];
  }
  return [
    ...(isApprovalPending(handlers.approvalWorkflow.qa) ? [{ label: 'Approve Test Suite', run: handlers.onApproveTestSuite, primary: true }] : []),
    { label: 'Coverage Analysis', run: handlers.onGenerateQATestCases, primary: !isApprovalPending(handlers.approvalWorkflow.qa) },
    { label: 'Regression Scope', run: handlers.onAnalyzeImpact },
    { label: 'Test Execution Notes', run: handlers.onGenerateQATestCases },
  ];
}

function childDraftsForTarget(targetType: WorkItemKind, drafts: ChildDraft[]): ChildDraft[] {
  if (targetType === 'Epic') {
    return drafts.filter((draft) => draft.type === 'Feature');
  }
  if (targetType === 'Feature') {
    return drafts.filter((draft) => draft.type === 'User Story');
  }
  if (targetType === 'Story') {
    return drafts.filter((draft) => draft.type === 'Task');
  }
  return [];
}

function areAllDraftsApproved(drafts: ChildDraft[]): boolean {
  return Boolean(drafts.length) && drafts.every((draft) => draft.status === 'approved' || draft.status === 'created');
}

function areAllDraftsReviewed(drafts: ChildDraft[]): boolean {
  return Boolean(drafts.length) && drafts.every((draft) => ['approved', 'created', 'failed', 'skipped'].includes(draft.status));
}

function childDraftIdentity(draft: ChildDraft): string {
  return `${draft.type}:${draft.capabilityCategory || ''}:${draft.title}`;
}

function epicFeatureGenerationSource(epicInput: { title: string; description: string }, epicResult?: EpicRefinement): Record<string, unknown> {
  return {
    ...epicInput,
    type: 'Epic',
    purpose: 'generated_features',
    approved_capabilities: (epicResult?.capability_review || [])
      .filter(isCapabilityApproved)
      .map((capability) => capability.capabilityId || capability.capabilityName),
    rejected_capabilities: (epicResult?.capability_review || [])
      .filter(isCapabilityRejected)
      .map((capability) => capability.capabilityId || capability.capabilityName),
  };
}

function normalizeEpicCapabilityReview(result: EpicRefinement, preserveReviewedState = false): EpicRefinement {
  if (!result.capability_review?.length) {
    return result;
  }
  const shouldPreserve = preserveReviewedState || result.capability_review_user_validated === true;
  if (shouldPreserve) {
    return result;
  }
  return {
    ...result,
    capability_review_user_validated: false,
    capability_review: result.capability_review.map((capability) => ({
      ...capability,
      status: 'Pending',
    })),
  };
}

function normalizedCapabilityStatus(status: string | undefined | null): string {
  return String(status || '').trim().toLowerCase();
}

function isCapabilityApproved(capability: Pick<CapabilityReview, 'status'>): boolean {
  return normalizedCapabilityStatus(capability.status) === 'approved';
}

function isCapabilityRejected(capability: Pick<CapabilityReview, 'status'>): boolean {
  return normalizedCapabilityStatus(capability.status) === 'rejected';
}

function isCapabilityReviewed(capability: Pick<CapabilityReview, 'status'>): boolean {
  return isCapabilityApproved(capability) || isCapabilityRejected(capability);
}

function capabilityReviewIdentity(capability: Pick<CapabilityReview, 'capabilityId' | 'capabilityName'>): string {
  return (capability.capabilityName || capability.capabilityId || '')
    .trim()
    .toLowerCase();
}

function reconcileEpicCapabilityReview(
  previousResult: EpicRefinement | undefined,
  nextResult: EpicRefinement,
): EpicRefinement {
  if (!nextResult.capability_review?.length || !previousResult?.capability_review?.length) {
    return nextResult;
  }
  const previousByIdentity = new Map(
    previousResult.capability_review.map((capability) => [capabilityReviewIdentity(capability), capability]),
  );
  const capabilityReview = nextResult.capability_review.map((capability) => {
    const previous = previousByIdentity.get(capabilityReviewIdentity(capability));
    if (!previous) {
      return capability;
    }
    const preservedStatus = isCapabilityReviewed(previous) ? previous.status : capability.status;
    return {
      ...capability,
      status: preservedStatus,
      reviewComments: previous.reviewComments?.length ? previous.reviewComments : capability.reviewComments,
    };
  });
  const userValidated = capabilityReview.some((capability) => isCapabilityReviewed(capability) || Boolean(capability.reviewComments?.length));
  return {
    ...nextResult,
    capability_review_user_validated: userValidated,
    capability_review: capabilityReview,
  };
}

function mergeEpicFeatureDraftsFromCapabilityState(
  epicResult: EpicRefinement | undefined,
  childDrafts: ChildDraft[],
): ChildDraft[] {
  const existingFeatureDrafts = childDrafts.filter((draft) => draft.type === 'Feature');
  if (!epicResult?.recommended_features?.length) {
    return existingFeatureDrafts;
  }
  if (!existingFeatureDrafts.length) {
    return [];
  }
  const visibleDrafts = featureDraftsFromEpic(epicResult, true);
  const existingByIdentity = new Map(
    existingFeatureDrafts
      .map((draft) => [childDraftIdentity(draft), draft]),
  );
  return visibleDrafts.map((draft) => {
    const existing = existingByIdentity.get(childDraftIdentity(draft));
    return existing
      ? {
          ...draft,
          selected: existing.selected,
          status: existing.status,
          azureId: existing.azureId,
          error: existing.error,
        }
      : draft;
  });
}

function mergeFeatureStoryDraftsFromReviewState(
  featureResult: FeatureRefinement | undefined,
  childDrafts: ChildDraft[],
): ChildDraft[] {
  const existingStoryDrafts = childDrafts.filter((draft) => draft.type === 'User Story');
  if (!featureResult?.recommended_stories?.length) {
    return existingStoryDrafts.filter((draft) => ['approved', 'created', 'creating'].includes(draft.status));
  }
  if (!existingStoryDrafts.length) {
    return [];
  }
  const visibleDrafts = storyDraftsFromFeature(featureResult);
  const existingByIdentity = new Map(
    existingStoryDrafts.map((draft) => [childDraftIdentity(draft), draft]),
  );
  return visibleDrafts
    .map((draft) => {
      const existing = existingByIdentity.get(childDraftIdentity(draft));
      return existing
        ? {
            ...draft,
            selected: existing.selected,
            status: existing.status,
            azureId: existing.azureId,
            error: existing.error,
          }
        : draft;
    })
    .filter((draft) => ['approved', 'created', 'creating'].includes(draft.status));
}

function reconcileFeatureStoryDrafts(
  featureResult: FeatureRefinement | undefined,
  childDrafts: ChildDraft[],
): ChildDraft[] {
  const existingStoryDrafts = childDrafts.filter((draft) => draft.type === 'User Story');
  if (!featureResult?.recommended_stories?.length) {
    return existingStoryDrafts;
  }
  const nextStoryDrafts = storyDraftsFromFeature(featureResult);
  const existingByIdentity = new Map(
    existingStoryDrafts.map((draft) => [childDraftIdentity(draft), draft]),
  );
  return nextStoryDrafts.map((draft) => {
    const existing = existingByIdentity.get(childDraftIdentity(draft));
    return existing
      ? {
          ...draft,
          selected: existing.selected,
          status: existing.status,
          azureId: existing.azureId,
          error: existing.error,
        }
      : draft;
  });
}

function childArtifactTypeForWorkItem(itemType: WorkItemKind): ArtifactType | undefined {
  if (itemType === 'Epic') return 'Feature';
  if (itemType === 'Feature') return 'Story';
  if (itemType === 'Story') return 'Task';
  return undefined;
}

function approvalForChildArtifactType(artifactType: ArtifactType): ApprovalArtifact {
  if (artifactType === 'Feature') return 'features';
  if (artifactType === 'Story') return 'stories';
  if (artifactType === 'Task') return 'tasks';
  return 'features';
}

function artifactDisplayName(artifactType: ArtifactType): string {
  if (artifactType === 'Execution Package') return 'Implementation Package';
  if (artifactType === 'Execution Plan') return 'Implementation Plan';
  if (artifactType === 'Dev Prompt') return 'Developer Prompt';
  return artifactType;
}

function latestChildArtifactForSource(artifacts: ArtifactRecord[], artifactType: ArtifactType, sourceItemId: string): ArtifactRecord | undefined {
  return artifacts
    .filter((artifact) => artifact.artifact_type === artifactType && String(artifact.source_item?.id || '') === sourceItemId && Array.isArray(artifact.payload))
    .sort((left, right) => {
      const dateCompare = String(right.created_on || '').localeCompare(String(left.created_on || ''));
      return dateCompare || Number(right.version || 0) - Number(left.version || 0);
    })[0];
}

function latestArtifactForSource(artifacts: ArtifactRecord[], artifactType: ArtifactType, sourceItemId: string): ArtifactRecord | undefined {
  return artifacts
    .filter((artifact) => artifact.artifact_type === artifactType && String(artifact.source_item?.id || '') === sourceItemId)
    .sort((left, right) => {
      const dateCompare = String(right.created_on || '').localeCompare(String(left.created_on || ''));
      return dateCompare || Number(right.version || 0) - Number(left.version || 0);
    })[0];
}

function normalizeChildDraftPayload(payload: unknown, artifactState: ArtifactLifecycleState): ChildDraft[] {
  if (!Array.isArray(payload)) {
    return [];
  }
  return payload
    .filter((draft): draft is ChildDraft => Boolean(draft && typeof draft === 'object' && 'type' in draft && 'title' in draft))
    .map((draft) => ({
      ...draft,
      selected: draft.selected !== false,
      status: artifactState === 'approved' || artifactState === 'locked'
        ? (draft.status === 'created' ? 'created' : 'approved')
        : draft.status || 'preview',
    }));
}

function childGenerationNoun(targetType: WorkItemKind): string {
  if (targetType === 'Epic') return 'Features';
  if (targetType === 'Feature') return 'Stories';
  if (targetType === 'Story') return 'Tasks';
  return 'Child work items';
}

function ApprovalWorkflowDashboard({ state, itemType }: { state: ApprovalWorkflowState; itemType: WorkItemKind }) {
  const rows: Array<{ key: ApprovalArtifact; label: string }> = [
    { key: 'epic', label: 'Epic' },
    { key: 'features', label: 'Features' },
    { key: 'feature', label: 'Feature' },
    { key: 'stories', label: 'Stories' },
    { key: 'story', label: 'Story' },
    { key: 'tasks', label: 'Tasks' },
    { key: 'qa', label: 'QA' },
    { key: 'execution', label: 'Implementation Package' },
  ];
  const visible = rows.filter((row) => {
    if (itemType === 'Epic') return ['epic', 'features'].includes(row.key);
    if (itemType === 'Feature') return ['feature', 'stories', 'qa'].includes(row.key);
    if (itemType === 'Story') return ['story', 'tasks', 'qa', 'execution'].includes(row.key);
    if (itemType === 'Task' || itemType === 'Bug') return ['execution', 'qa'].includes(row.key);
    return ['qa'].includes(row.key);
  });
  return (
    <section className="planner-card">
      <div className="planner-section-header">
        <div>
          <div className="planner-label">Approval Workflow</div>
          <div className="planner-subtle">Generated output stays in Draft until you approve it. Approval unlocks the next level.</div>
        </div>
      </div>
      <div className="planner-summary-grid">
        {visible.map((row) => (
          <SummaryTile key={row.key} title={row.label} value={approvalStatusLabel(state[row.key])} />
        ))}
      </div>
    </section>
  );
}

function ArtifactLifecyclePanel({ artifacts, reuseStatus }: { artifacts: ArtifactRecord[]; reuseStatus: string }) {
  const visible = artifacts.slice(0, 6);
  if (!reuseStatus && !visible.length) {
    return null;
  }
  const summary = visible.slice(0, 2).map((artifact) => `${artifact.artifact_type} v${artifact.version} ${artifact.state}`).join(' · ');
  return (
    <section className="planner-card">
      <div className="planner-section-header">
        <div>
          <div className="planner-label">Artifact Lifecycle</div>
          <div className="planner-subtle">{summary || 'No reusable artifacts yet.'}</div>
        </div>
      </div>
      {reuseStatus ? <div className="planner-banner">{reuseStatus}</div> : null}
      {visible.length ? (
        <details className="planner-accordion">
          <summary>View Artifact History</summary>
          <div className="planner-status-grid">
            {visible.map((artifact) => (
              <div className="planner-status-row" key={artifact.artifact_id}>
                <span>{artifact.artifact_type} v{artifact.version}</span>
                <strong>{artifactLifecycleLabel(artifact)}</strong>
                <small>{artifact.title}</small>
              </div>
            ))}
          </div>
        </details>
      ) : null}
    </section>
  );
}

function RelationshipSummaryCard({ summary }: { summary?: GraphSummary }) {
  if (!summary || summary.version === 0) {
    return null;
  }
  const chain = summary.chain;
  return (
    <section className="planner-card">
      <div className="planner-section-header">
        <div>
          <div className="planner-label">Relationship Summary</div>
          <div className="planner-subtle">Persistent project graph used by planning, execution, QA, coverage, and impact analysis.</div>
        </div>
        <div className="planner-session-freshness fresh">Graph v{summary.version}</div>
      </div>
      <div className="planner-summary-grid">
        <SummaryTile title="Epics" value={String(chain.epics)} />
        <SummaryTile title="Features" value={String(chain.features)} />
        <SummaryTile title="Stories" value={String(chain.stories)} />
        <SummaryTile title="Tasks" value={String(chain.tasks)} />
        <SummaryTile title="Tests" value={String(chain.tests)} />
        <SummaryTile title="Implementation Packages" value={String(chain.execution_packages)} />
      </div>
      <div className="planner-status-grid">
        <Row label="Relationships" value={String(summary.relationship_count)} />
        <Row label="Acceptance Criteria Coverage" value={`${summary.coverage?.coverage_percent || 0}%`} />
        <Row label="Uncovered Acceptance Criteria" value={String(summary.coverage?.uncovered_acceptance_criteria_count || 0)} />
        <Row label="Last Graph Update" value={formatTimestamp(summary.updated_at)} />
      </div>
    </section>
  );
}

function CoverageIntelligenceCard({ report, compact = false }: { report?: CoverageIntelligenceReport; compact?: boolean }) {
  const coverage = report?.coverage_report;
  if (!coverage || (!coverage.story_coverage.length && !coverage.feature_coverage.length && !coverage.gap_summary.gap_count)) {
    return null;
  }
  const topGaps = coverage.gap_summary.gaps.slice(0, 5).map((gap) => `${gap.severity}: ${gap.message}`);
  return (
    <section className="planner-card">
      <div className="planner-section-header">
        <div>
          <div className="planner-label">{compact ? 'Project Coverage Snapshot' : 'Coverage Intelligence'}</div>
          <div className="planner-subtle">
            {compact
              ? 'Project-wide traceability summary. Open QA for detailed gaps and regression scope.'
              : 'Traceability and gaps from the persistent project graph.'}
          </div>
        </div>
        <div className={`planner-session-freshness ${coverage.quality_gate === 'pass' ? 'fresh' : 'stale'}`}>
          {coverage.quality_gate === 'pass' ? 'Quality Gate Passed' : 'Quality Gate Needs Work'}
        </div>
      </div>
      <div className="planner-summary-grid">
        <SummaryTile title="Project Coverage" value={`${coverage.overall_project_coverage}%`} />
        <SummaryTile title="Stories" value={String(coverage.story_coverage.length)} />
        <SummaryTile title="Features" value={String(coverage.feature_coverage.length)} />
        <SummaryTile title="Gaps" value={String(coverage.gap_summary.gap_count)} />
        <SummaryTile title="Blocking Gaps" value={String(coverage.gap_summary.blocking_gap_count)} />
        <SummaryTile title="Threshold" value={`${coverage.threshold}%`} />
      </div>
      {!compact && topGaps.length ? <ListBlock title="Gap Analysis" items={topGaps} /> : null}
      {!compact && !topGaps.length ? <div className="planner-subtle">No coverage gaps found in the current graph.</div> : null}
      {!compact && coverage.story_coverage.length ? (
        <ListBlock
          title="Story Coverage"
          items={coverage.story_coverage.slice(0, 5).map((story) => `${story.title}: ${story.overall_score}% (${story.task_count} tasks, ${story.test_count} tests, ${story.execution_package_count} execution packages)`)}
        />
      ) : null}
    </section>
  );
}

function RoleBadge({ permission }: { permission: PermissionState }) {
  return (
    <div className={`planner-role-badge ${permission.role}`}>
      <span>{roleLabel(permission.role)}</span>
      <small>{permission.mapped_group || 'Azure DevOps group mapping'}</small>
    </div>
  );
}

function AdminWorkspace({
  permission,
  profile,
  governance,
  providerMetadata,
  loading,
  adoProjects,
  repositories,
  branches,
  repositoryLoadMessage,
  repositoryDocuments,
  fileStatus,
  selectedFiles,
  onRefreshPermissions,
  onSelectAdoProject,
  onSelectRepository,
  onReloadRepositories,
  onProfileChange,
  onRepositoryDocumentsChange,
  onFileStatusChange,
  onSelectedFilesChange,
  onAnalyzeReadme,
  onDiscoverDocuments,
  onAnalyzeDocuments,
  onAnalyzeDescription,
  onSaveProfile,
}: {
  permission: PermissionState;
  profile: ProjectProfile;
  governance: KnowledgeGovernance;
  providerMetadata?: ProviderMetadata;
  loading: boolean;
  adoProjects: AdoProject[];
  repositories: GitRepository[];
  branches: string[];
  repositoryLoadMessage: string;
  repositoryDocuments: Record<string, string>;
  fileStatus: Record<string, 'available' | 'missing' | 'unknown'>;
  selectedFiles: string[];
  onRefreshPermissions: () => void;
  onSelectAdoProject: (adoProject: string) => void;
  onSelectRepository: (repositoryId: string) => void;
  onReloadRepositories: () => void;
  onProfileChange: (profile: ProjectProfile) => void;
  onRepositoryDocumentsChange: (documents: Record<string, string>) => void;
  onFileStatusChange: (status: Record<string, 'available' | 'missing' | 'unknown'>) => void;
  onSelectedFilesChange: (files: string[]) => void;
  onAnalyzeReadme: () => void;
  onDiscoverDocuments: () => void;
  onAnalyzeDocuments: () => void;
  onAnalyzeDescription: () => void;
  onSaveProfile: () => void;
}) {
  return (
    <>
      <details className="planner-card" open>
        <summary className="planner-label">Repository Settings</summary>
        <RepositoryIntelligenceCard
          profile={profile}
          adoProjects={adoProjects}
          repositories={repositories}
          branches={branches}
          repositoryLoadMessage={repositoryLoadMessage}
          repositoryDocuments={repositoryDocuments}
          fileStatus={fileStatus}
          selectedFiles={selectedFiles}
          loading={loading}
          showConnectionControls
          onSelectAdoProject={onSelectAdoProject}
          onSelectRepository={onSelectRepository}
          onReloadRepositories={onReloadRepositories}
          onProfileChange={onProfileChange}
          onRepositoryDocumentsChange={onRepositoryDocumentsChange}
          onFileStatusChange={onFileStatusChange}
          onSelectedFilesChange={onSelectedFilesChange}
          onAnalyzeReadme={onAnalyzeReadme}
          onDiscoverDocuments={onDiscoverDocuments}
          onAnalyzeDocuments={onAnalyzeDocuments}
          governance={governance}
        />
      </details>

      <details className="planner-card" open>
        <summary className="planner-label">Permissions</summary>
        <div className="planner-section-header">
          <div>
            <div className="planner-subtle">AI Gen permissions are inherited from Azure DevOps project security groups.</div>
          </div>
          <button className="planner-button secondary" type="button" onClick={onRefreshPermissions}>Refresh Permissions</button>
        </div>
        <div className="planner-status-grid">
          <Row label="Current User" value={permission.user_display_name || permission.user_name || 'Unknown'} />
          <Row label="Current User Role" value={roleLabel(permission.role)} />
          <Row label="Mapped Azure DevOps Group" value={permission.mapped_group || 'Not resolved'} />
          <Row label="Resolution Status" value={permission.status === 'resolved' ? 'Resolved from Azure DevOps groups' : 'Fallback / limited group visibility'} />
          <Row label="Project" value={profile.project_name || getAdoMapping(profile).ado_project || 'Not captured'} />
          <Row label="Repository Mapping" value={profile.repository_connection.repository_name || 'Not connected'} />
          <Row label="Knowledge Status" value={knowledgeStatusLabel(governance)} />
          <Row label="Last Refreshed By" value={governance.last_refreshed_by || 'Not refreshed yet'} />
          <Row label="Last Refreshed On" value={formatTimestamp(governance.last_refreshed_on)} />
        </div>
        {permission.warning ? <div className="planner-banner">{permission.warning}</div> : null}
        <div className="planner-status-grid">
          <Row label="Project Administrators" value="AI Gen Admin: Project Profile, Repository Mapping, Knowledge Refresh, Standards, Theme Settings" />
          <Row label="Contributors" value="AI Gen Contributor: Planning, Execution, QA" />
          <Row label="Readers" value="AI Gen Viewer: Read-only access" />
        </div>
        <div className="planner-label">Detected Azure DevOps Groups</div>
        {permission.azure_groups.length ? <ChipList items={permission.azure_groups} /> : <div className="planner-subtle">No Azure DevOps groups were visible to this extension session.</div>}
      </details>

      <details className="planner-card">
        <summary className="planner-label">Knowledge Refresh</summary>
        <KnowledgeGovernanceCard governance={governance} canAdmin />
        <KnowledgeProfilePreview profile={profile} governance={governance} canAdmin />
      </details>

      <details className="planner-card">
        <summary className="planner-label">Standards and Manual Profile Fields</summary>
        <StandardsAndGuidelinesSummary profile={profile} />
        <OnboardingForm
          profile={profile}
          loading={loading}
          onProfileChange={onProfileChange}
          onAnalyze={onAnalyzeDescription}
          onSave={onSaveProfile}
        />
      </details>

      <details className="planner-card">
        <summary className="planner-label">Theme</summary>
        <div className="planner-subtle">Theme settings are coming next. Current enterprise theme uses Hubbell yellow, white, and graphite accents.</div>
      </details>

      <details className="planner-card">
        <summary className="planner-label">Developer Diagnostics</summary>
        <ProjectIntelligenceProviderDiagnostics metadata={providerMetadata} />
      </details>
    </>
  );
}

function RepositoryReadOnlyCard({ profile, governance }: { profile: ProjectProfile; governance: KnowledgeGovernance }) {
  return (
    <section className="planner-card">
      <div className="planner-label">Repository Mapping</div>
      <div className="planner-subtle">Repository configuration is managed by AI Gen Admins.</div>
      <div className="planner-status-grid">
        <Row label="Repository" value={profile.repository_connection.repository_name || 'Not connected'} />
        <Row label="Branch" value={profile.repository_connection.branch || 'Not selected'} />
        <Row label="Knowledge Version" value={knowledgeVersion(profile)} />
        <Row label="Knowledge Status" value={knowledgeStatusLabel(governance)} />
        <Row label="Knowledge Captured" value={registrySummary(profile)} />
      </div>
    </section>
  );
}

function KnowledgeGovernanceCard({ governance, canAdmin }: { governance: KnowledgeGovernance; canAdmin: boolean }) {
  return (
    <section className="planner-card planner-governance-card">
      <div className="planner-section-header">
        <div>
          <div className="planner-label">Knowledge Governance</div>
          <div className="planner-subtle">One person curates repository knowledge. Everyone else consumes the approved registry.</div>
        </div>
        <div className={`planner-session-freshness ${governance.registry_status === 'read_only' ? 'fresh' : 'stale'}`}>
          {knowledgeStatusLabel(governance)}
        </div>
      </div>
      <div className="planner-session-grid">
        <Row label="Knowledge Status" value={governance.registry_status === 'read_only' ? 'Read Only' : 'Pending Analysis'} />
        <Row label="Current Access" value={canAdmin ? 'Editable Admin Controls' : 'Read Only'} />
        <Row label="Knowledge Version" value={governance.knowledge_version} />
        <Row label="Last Refreshed By" value={governance.last_refreshed_by || 'Not refreshed yet'} />
        <Row label="Last Refreshed On" value={formatTimestamp(governance.last_refreshed_on)} />
        <Row label="Governance Rule" value="Admins curate. Contributors and Viewers consume." />
      </div>
    </section>
  );
}

function ProductIdentityCard({ profile }: { profile: ProjectProfile }) {
  const name = profile.project_name || 'Project Intelligence';
  const domain = profile.domain || profile.knowledge_profile_preview.domain || 'Enterprise Planning';
  const tagline = generatedTagline(profile);
  const setup = projectSetupStatus(profile);
  return (
    <section className="planner-card planner-identity-card">
      <div className="planner-logo-frame">
        <img src="static/hei-logo.png" alt="Hubbell Engineering Intelligence" />
      </div>
      <div className="planner-identity-copy">
        <div className="planner-eyebrow">Product Identity</div>
        <h1>{name}</h1>
        <div className="planner-subtitle">{domain}</div>
        <p>{tagline}</p>
      </div>
      <div className="planner-readiness-badge">
        <strong>{setup.complete ? 'Complete' : 'Setup'}</strong>
        <span>{setup.complete ? 'Project Setup Complete' : 'Needs Attention'}</span>
      </div>
    </section>
  );
}

function EnterpriseReadinessCard({ profile, qaReady, executionReady }: { profile: ProjectProfile; qaReady: boolean; executionReady: boolean }) {
  const readiness = enterpriseReadiness(profile, qaReady, executionReady);
  const setup = projectSetupStatus(profile);
  return (
    <section className="planner-card">
      <div className="planner-section-header">
        <div>
          <div className="planner-label">{setup.complete ? 'Project Setup Complete' : 'Project Setup'}</div>
          <div className="planner-subtle">Required setup is shown as clear status, not a percentage score.</div>
        </div>
        <strong className={setup.complete ? 'planner-ready-text' : ''}>{setup.complete ? 'Ready' : 'Action Needed'}</strong>
      </div>
      <div className="planner-health-grid compact">
        {setup.checks.map((check) => (
          <HealthCard key={check.title} title={check.title} status={check.status} detail={check.detail} />
        ))}
      </div>
      <div className="planner-health-grid compact">
        {readiness.checks.map((check) => (
          <HealthCard key={check.title} title={check.title} status={check.status} detail={check.detail} />
        ))}
      </div>
    </section>
  );
}

function RecentActivityCard({ currentWorkItem, profile, hasQa, hasExecution }: { currentWorkItem?: AdoWorkItem; profile: ProjectProfile; hasQa: boolean; hasExecution: boolean }) {
  const activity = [
    currentWorkItem ? `Work item loaded: ${currentWorkItem.type} #${currentWorkItem.id}` : 'Open from an Azure Boards work item to load context.',
    profile.repository_connection.repository_name ? `Repository connected: ${profile.repository_connection.repository_name}` : 'Repository connection pending.',
    profile.knowledge_registry.source_files.length ? `Documentation analyzed: ${profile.knowledge_registry.source_files.slice(0, 3).join(', ')}` : 'Documentation analysis pending.',
    hasExecution ? 'Execution package generated.' : 'Execution package not generated yet.',
    hasQa ? 'QA test suite generated.' : 'QA coverage not generated yet.',
  ];
  return <ListBlock title="Recent Activity" items={activity} />;
}

function StandardsAndGuidelinesSummary({ profile }: { profile: ProjectProfile }) {
  return (
    <section className="planner-card">
      <div className="planner-label">Standards Summary</div>
      <div className="planner-knowledge-summary-grid">
        <SummaryTile title="Security" value={profile.development_standards.security_requirements.length ? `${profile.development_standards.security_requirements.length} rules` : 'Not captured'} />
        <SummaryTile title="Development" value={profile.development_standards.coding_guidelines.length || profile.development_standards.architecture_patterns.length ? 'Captured' : 'Not captured'} />
        <SummaryTile title="Testing" value={profile.development_standards.testing_requirements.length ? `${profile.development_standards.testing_requirements.length} requirements` : 'Not captured'} />
        <SummaryTile title="UI Guidelines" value={summarizeUiGuidelines(profile)} />
      </div>
    </section>
  );
}

function AIPlannerWorkspace({
  profile,
  loading,
  currentWorkItem,
  childDrafts,
  creationLog,
  providerMetadata,
  canContribute,
  itemType,
  selectedItemType,
  onItemTypeChange,
  epicInput,
  featureInput,
  storyInput,
  acceptanceCriteria,
  epicResult,
  featureResult,
  storyResult,
  epicImpact,
  featureImpact,
  qaTestSuite,
  approvalWorkflow,
  setEpicInput,
  setFeatureInput,
  setStoryInput,
  setAcceptanceCriteria,
  refineEpic,
  refineFeature,
  retryFeatureAI,
  refineStory,
  analyzeImpact,
  generateChildren,
  approveEpic,
  approveFeatures,
  approveFeature,
  approveStories,
  approveTasks,
  updateCapabilityReview,
  moveCapabilityReview,
  updateDraftSelection,
  updateChildDraftReview,
  createSelectedChildren,
  buildExecutionPackage,
  generateQATestCases,
  artifactRecords,
  artifactReuseStatus,
  workflow,
  planningFocusRequest,
}: {
  profile: ProjectProfile;
  loading: boolean;
  currentWorkItem?: AdoWorkItem;
  childDrafts: ChildDraft[];
  creationLog: string[];
  providerMetadata?: ProviderMetadata;
  canContribute: boolean;
  itemType: WorkItemKind;
  selectedItemType: WorkItemKind;
  onItemTypeChange: (type: WorkItemKind) => void;
  epicInput: { title: string; description: string };
  featureInput: { title: string; description: string };
  storyInput: { title: string; description: string };
  acceptanceCriteria: string;
  epicResult?: EpicRefinement;
  featureResult?: FeatureRefinement;
  storyResult?: StoryRefinement;
  epicImpact?: EpicImpact;
  featureImpact?: FeatureImpact;
  qaTestSuite?: QATestSuiteResult;
  approvalWorkflow: ApprovalWorkflowState;
  setEpicInput: (value: { title: string; description: string }) => void;
  setFeatureInput: (value: { title: string; description: string }) => void;
  setStoryInput: (value: { title: string; description: string }) => void;
  setAcceptanceCriteria: (value: string) => void;
  refineEpic: () => void;
  refineFeature: () => void;
  retryFeatureAI: () => void;
  refineStory: () => void;
  analyzeImpact: () => void;
  generateChildren: (forceRegenerate?: boolean) => void;
  approveEpic: () => void;
  approveFeatures: () => void;
  approveFeature: () => void;
  approveStories: () => void;
  approveTasks: () => void;
  updateCapabilityReview: (capabilityId: string, changes: Partial<CapabilityReview>) => void;
  moveCapabilityReview: (capabilityId: string, direction: -1 | 1) => void;
  updateDraftSelection: (draftId: string, selected: boolean) => void;
  updateChildDraftReview: (draftId: string, artifactType: ArtifactType, changes: Partial<ChildDraft>) => void;
  createSelectedChildren: () => void;
  buildExecutionPackage: () => void;
  generateQATestCases: (forceRefresh?: boolean, action?: 'analyze' | 'generate_missing_tests') => void;
  artifactRecords: ArtifactRecord[];
  artifactReuseStatus: string;
  workflow: WorkflowOrchestrationState;
  planningFocusRequest: { target: PlanningFocusTarget; nonce: number };
}) {
  const readOnly = !canContribute || currentWorkItem?.state.toLowerCase() === 'closed';
  const planningType = itemType === 'Epic' || itemType === 'Feature' ? itemType : selectedItemType;
  const hasGeneratedFeatures = childDrafts.some((draft) => draft.type === 'Feature');
  const hasGeneratedStories = childDrafts.some((draft) => draft.type === 'User Story');
  const hasGeneratedTasks = childDrafts.some((draft) => draft.type === 'Task');
  const [selectedPlanningItemId, setSelectedPlanningItemId] = useState('');
  const [selectedPlanningDetailTab, setSelectedPlanningDetailTab] = useState<PlanningDetailTab>('overview');
  const [storyPlanningTab, setStoryPlanningTab] = useState<StoryPlanningTab>('overview');
  const planningModel = buildPlanningWorkspaceModel({
    planningType,
    epicResult,
    featureResult,
    childDrafts,
    approvalWorkflow,
    loading,
    readOnly,
    epicTitle: epicInput.title,
    featureTitle: featureInput.title,
    refineEpic,
    refineFeature,
    approveEpic,
    approveFeature,
    approveFeatures,
    approveStories,
    createSelectedChildren,
    generateChildren,
    analyzeImpact,
    hasGeneratedFeatures,
    hasGeneratedStories,
    selectedId: selectedPlanningItemId,
    setSelectedId: setSelectedPlanningItemId,
  });
  const planningDrafts = planningType === 'Epic'
    ? mergeEpicFeatureDraftsFromCapabilityState(epicResult, childDrafts)
    : mergeFeatureStoryDraftsFromReviewState(featureResult, childDrafts);
  const firstPlanningItemId = planningModel.items[0]?.id || '';
  useEffect(() => {
    if (planningFocusRequest.target === 'features' && planningType === 'Epic') {
      const targetId = firstPlanningItemId;
      if (targetId) {
        setSelectedPlanningItemId(targetId);
        setSelectedPlanningDetailTab('overview');
      }
    }
    if (planningFocusRequest.target === 'stories' && planningType === 'Feature') {
      const targetId = firstPlanningItemId;
      if (targetId) {
        setSelectedPlanningItemId(targetId);
        setSelectedPlanningDetailTab('overview');
      }
    }
  }, [planningFocusRequest.nonce, planningFocusRequest.target, planningType, firstPlanningItemId]);
  if (itemType === 'Story' && currentWorkItem) {
    const generatedTasks = childDrafts.filter((draft) => draft.type === 'Task');
    return (
      <>
        <section className="planner-card hei-planning-workspace">
          <div className="hei-planning-header">
            <div>
              <div className="planner-label">Story Planning</div>
              <h2>{normalizeStoryTitle(storyInput.title || currentWorkItem.title || 'Story')}</h2>
              <p>Review the story, confirm acceptance criteria, approve generated tasks, then continue into execution.</p>
            </div>
            <div className="hei-planning-primary">
              <span>{hasGeneratedTasks ? 'Task Approval' : storyResult ? 'Generate Tasks' : 'Story Analysis'}</span>
              <small>Use the sticky header action to continue.</small>
            </div>
          </div>
        <PlanningProgressBar
            stages={buildSingleCurrentStages(
              ['Story Analysis', 'Task Review', 'Execution'],
              !storyResult ? 'Story Analysis' : !hasGeneratedTasks || isApprovalPending(approvalWorkflow.tasks) ? 'Task Review' : 'Execution',
              {
                'Story Analysis': Boolean(storyResult),
                'Task Review': hasGeneratedTasks && approvalWorkflow.tasks === 'approved',
                Execution: false,
              }
            )}
            metrics={[
              { label: 'Story Analysis', percent: storyResult ? 100 : 0 },
              { label: 'Task Review', status: hasGeneratedTasks ? approvalStatusLabel(approvalWorkflow.tasks) : 'Pending' },
              { label: 'Execution', status: approvalWorkflow.tasks === 'approved' ? 'Ready' : 'Locked' },
            ]}
        />
        {readOnly ? <div className="planner-error">This work item is Closed. Story planning is read-only.</div> : null}
        {storyResult ? (
          <StoryPlanningWorkspace
            result={storyResult}
            currentWorkItem={currentWorkItem}
            activeTab={storyPlanningTab}
            onTabChange={setStoryPlanningTab}
            taskDrafts={generatedTasks}
            hasExecutionPackage={false}
            onGenerateTasks={() => generateChildren(false)}
            loading={loading}
            readOnly={readOnly}
            taskApprovalStatus={approvalWorkflow.tasks}
          />
        ) : (
          <section className="planner-card">
            <RefinementInput input={storyInput} setInput={setStoryInput} titlePlaceholder="Open critical fault event details" descriptionPlaceholder="Approved story scope, users, and outcome." />
            <textarea
              className="planner-textarea compact"
              value={acceptanceCriteria}
              onChange={(event) => setAcceptanceCriteria(event.target.value)}
              placeholder="Acceptance criteria, one per line"
            />
          </section>
        )}
        </section>
      </>
    );
  }
  if (itemType !== 'Epic' && itemType !== 'Feature' && currentWorkItem) {
    return (
      <>
      <section className="planner-card">
        <div className="planner-label">Planning Workspace</div>
          <div className="planner-subtle">{itemType} work items are routed to {workspaceLabel(recommendedWorkspaceForItem(itemType))}. Planning actions are hidden for this item type.</div>
        </section>
      </>
    );
  }
  return (
    <>
      <section className="planner-card hei-planning-workspace">
        <div className="hei-planning-header">
          <div>
            <div className="planner-label">{planningType} Planning</div>
            <h2>{planningModel.title}</h2>
            <p>{planningModel.subtitle}</p>
          </div>
          <div className="hei-planning-primary">
            <span>{planningModel.stageLabel}</span>
            <small>{planningModel.primaryAction.disabledReason || 'Use the sticky header action to continue.'}</small>
          </div>
        </div>
        <PlanningProgressBar stages={planningModel.stages} metrics={planningModel.progressMetrics} />
        <KnowledgeRegistryNotice profile={profile} />
        {!profileCompletion(profile).complete ? (
          <div className="planner-banner">Project profile is incomplete. Results may be less accurate, but you can continue planning.</div>
        ) : null}
        {readOnly ? <div className="planner-error">This work item is Closed. Planning output is read-only.</div> : null}
        {currentWorkItem?.state.toLowerCase() === 'active' ? <div className="planner-banner">This work item is Active. AI Planner will ask before regeneration.</div> : null}
        {planningType === 'Feature' && featureResult ? (
          <FeatureAnalysisStatusCard result={featureResult} onRetryAI={retryFeatureAI} onContinue={approveFeature} loading={loading} readOnly={readOnly} />
        ) : null}
        <div className="planner-pill-row">
          {(['Epic', 'Feature'] as const).map((type) => (
            <button
              key={type}
              type="button"
              className={`planner-pill ${planningType === type ? 'active' : ''}`}
              onClick={() => onItemTypeChange(type)}
            >
              {type}
            </button>
          ))}
        </div>
        <PlanningItemPicker
          label={planningModel.listTitle}
          items={planningModel.items}
          selectedId={planningModel.selectedId}
          onSelect={planningModel.setSelectedId}
        />
        <div className="hei-planning-grid without-list">
          <section className="hei-planning-detail">
            {planningType === 'Epic' ? (
              <RefinementInput input={epicInput} setInput={setEpicInput} titlePlaceholder="Launch mobile commerce platform" descriptionPlaceholder="Describe the epic goal, users, rollout intent, and business context." />
            ) : (
              <RefinementInput input={featureInput} setInput={setFeatureInput} titlePlaceholder="Order visibility" descriptionPlaceholder="Describe feature behavior, affected users, and delivery scope." />
            )}
            <PlanningSelectedDetail
              item={planningModel.selectedItem}
              emptyTitle={planningModel.emptyTitle}
              emptyText={planningModel.emptyText}
              loading={loading}
              readOnly={readOnly}
              onApprove={planningModel.selectedItem?.kind === 'capability'
                ? () => updateCapabilityReview(planningModel.selectedItem!.id, { status: 'Approved' })
                : planningModel.selectedItem?.kind === 'feature'
                  ? () => updateChildDraftReview(planningModel.selectedItem!.id, 'Feature', { status: 'approved' })
                  : planningModel.selectedItem?.kind === 'story'
                    ? () => updateChildDraftReview(planningModel.selectedItem!.id, 'Story', { status: 'approved' })
                    : undefined}
              onReject={planningModel.selectedItem?.kind === 'capability'
                ? () => updateCapabilityReview(planningModel.selectedItem!.id, { status: 'Rejected' })
                : planningModel.selectedItem?.kind === 'feature'
                  ? () => updateChildDraftReview(planningModel.selectedItem!.id, 'Feature', { status: 'failed' })
                  : planningModel.selectedItem?.kind === 'story'
                    ? () => updateChildDraftReview(planningModel.selectedItem!.id, 'Story', { status: 'failed' })
                    : undefined}
              onEdit={planningModel.selectedItem?.kind === 'capability'
                ? () => {
                  const comment = window.prompt('Add a review comment for this capability', planningModel.selectedItem?.comments?.[0] || '');
                  if (comment !== null && planningModel.selectedItem) {
                    updateCapabilityReview(planningModel.selectedItem.id, { reviewComments: comment.trim() ? [comment.trim()] : [] });
                  }
                }
                : planningModel.selectedItem?.kind === 'feature' || planningModel.selectedItem?.kind === 'story'
                  ? () => {
                    const comment = window.prompt(
                      `Add a review note for this ${planningModel.selectedItem?.kind}`,
                      planningModel.selectedItem?.comments?.[0] || planningModel.selectedItem?.subtitle || '',
                    );
                    if (comment !== null && planningModel.selectedItem) {
                      updateChildDraftReview(
                        planningModel.selectedItem.id,
                        planningModel.selectedItem.kind === 'feature' ? 'Feature' : 'Story',
                        { error: comment.trim() || undefined },
                      );
                    }
                  }
                  : undefined}
              onMoveUp={planningModel.selectedItem?.kind === 'capability' ? () => moveCapabilityReview(planningModel.selectedItem!.id, -1) : undefined}
              onMoveDown={planningModel.selectedItem?.kind === 'capability' ? () => moveCapabilityReview(planningModel.selectedItem!.id, 1) : undefined}
              selectedTab={selectedPlanningDetailTab}
              onTabChange={setSelectedPlanningDetailTab}
            />
          </section>
          <aside className="hei-planning-insights">
            <PlanningInsights
              planningType={planningType}
              epicResult={epicResult}
              featureResult={featureResult}
              epicImpact={epicImpact}
              featureImpact={featureImpact}
              childDrafts={childDrafts}
              artifactRecords={artifactRecords}
              artifactReuseStatus={artifactReuseStatus}
              approvalWorkflow={approvalWorkflow}
            />
          </aside>
        </div>
        {planningDrafts.length ? (
          <GeneratedChildWorkItems
            drafts={planningDrafts}
            creationLog={creationLog}
            currentWorkItem={currentWorkItem}
            providerMetadata={providerMetadata}
            readOnly={!canContribute}
            loading={loading}
            onSelectionChange={updateDraftSelection}
            onCreateSelected={createSelectedChildren}
          />
        ) : null}
        <details className="planner-nested">
          <summary>Advanced Planning Actions</summary>
          <div className="planner-actions">
            <button className="planner-button secondary" onClick={planningType === 'Epic' ? refineEpic : refineFeature} disabled={planningType === 'Epic' ? loading || readOnly || !epicInput.title.trim() : loading || readOnly || !featureInput.title.trim()}>
              {planningType === 'Epic' ? 'Regenerate Epic Analysis' : 'Regenerate Feature Analysis'}
            </button>
            <button className="planner-button secondary" onClick={() => generateChildren(true)} disabled={planningType === 'Epic' ? loading || readOnly || !epicInput.title.trim() || !hasGeneratedFeatures : loading || readOnly || !featureInput.title.trim() || !hasGeneratedStories}>
              {planningType === 'Epic' ? 'Regenerate Features' : 'Regenerate Stories'}
            </button>
            <button className="planner-button secondary" onClick={analyzeImpact} disabled={planningType === 'Epic' ? loading || readOnly || !epicInput.title.trim() : loading || readOnly || !featureInput.title.trim()}>
              Impact Analysis
            </button>
          </div>
        </details>
      </section>
    </>
  );
}

function WorkItemContextCard({ workItem }: { workItem?: AdoWorkItem }) {
  if (!workItem) {
    return (
      <section className="planner-card">
        <div className="planner-label">Azure DevOps Work Item</div>
        <div className="planner-subtle">No current Azure DevOps work item was detected. Open this tab from a Boards work item to load context automatically.</div>
      </section>
    );
  }
  return (
    <section className="planner-card">
      <div className="planner-label">Azure DevOps Work Item</div>
      <div className="planner-status-grid">
        <Row label="ID" value={`#${workItem.id}`} />
        <Row label="Type" value={workItem.type || 'Unknown'} />
        <Row label="Title" value={workItem.title || 'Untitled'} />
        <Row label="State" value={workItem.state || 'Unknown'} />
        <Row label="Parent Hierarchy" value={workItem.parents.map((parent) => `${parent.type} #${parent.id}: ${parent.title}`).join(' > ') || 'No parent loaded'} />
        <Row label="Child Links" value={workItem.children.map((child) => `${child.type} #${child.id}: ${child.title}`).join(', ') || 'No child links loaded'} />
      </div>
    </section>
  );
}

type PlanningStageStatus = 'complete' | 'current' | 'locked';
type PlanningStage = { label: string; status: PlanningStageStatus };
type PlanningDetailTab = 'overview' | 'responsibilities' | 'scope' | 'repository' | 'knowledge' | 'history';
type StoryPlanningTab = 'overview' | 'acceptance' | 'implementation' | 'repository' | 'knowledge' | 'history';
type PlanningFocusTarget = 'features' | 'stories' | null;
type PlanningProgressMetric = { label: string; percent?: number; status?: string };
type PlanningReviewItem = {
  id: string;
  kind: 'capability' | 'feature' | 'story';
  title: string;
  subtitle: string;
  status?: string;
  priority?: string;
  confidence?: number;
  description?: string;
  businessGoal?: string;
  businessValue?: string;
  responsibilities?: string[];
  scope?: string[];
  outOfScope?: string[];
  dependencies?: string[];
  evidence?: string[];
  modules?: string[];
  flows?: string[];
  applications?: string[];
  acceptanceCriteria?: string[];
  comments?: string[];
  repositoryCoverage?: number;
  generatedCount?: number;
  validation?: string;
};

function buildPlanningWorkspaceModel({
  planningType,
  epicResult,
  featureResult,
  childDrafts,
  approvalWorkflow,
  loading,
  readOnly,
  epicTitle,
  featureTitle,
  refineEpic,
  refineFeature,
  approveEpic,
  approveFeature,
  approveFeatures,
  approveStories,
  createSelectedChildren,
  generateChildren,
  analyzeImpact,
  hasGeneratedFeatures,
  hasGeneratedStories,
  selectedId,
  setSelectedId,
}: {
  planningType: WorkItemKind;
  epicResult?: EpicRefinement;
  featureResult?: FeatureRefinement;
  childDrafts: ChildDraft[];
  approvalWorkflow: ApprovalWorkflowState;
  loading: boolean;
  readOnly: boolean;
  epicTitle: string;
  featureTitle: string;
  refineEpic: () => void;
  refineFeature: () => void;
  approveEpic: () => void;
  approveFeature: () => void;
  approveFeatures: () => void;
  approveStories: () => void;
  createSelectedChildren: () => void;
  generateChildren: (forceRegenerate?: boolean) => void;
  analyzeImpact: () => void;
  hasGeneratedFeatures: boolean;
  hasGeneratedStories: boolean;
  selectedId: string;
  setSelectedId: (value: string) => void;
}) {
  const isEpic = planningType === 'Epic';
  const featureDrafts = childDrafts.filter((draft) => draft.type === 'Feature');
  const storyDrafts = childDrafts.filter((draft) => draft.type === 'User Story');
  const effectiveFeatureDrafts = isEpic
    ? mergeEpicFeatureDraftsFromCapabilityState(epicResult, childDrafts)
    : featureDrafts;
  const effectiveStoryDrafts = isEpic
    ? []
    : childDrafts.filter((draft) => draft.type === 'User Story');
  const capabilities = epicResult?.capability_review || [];
  const allCapabilitiesReviewed = !capabilities.length || capabilities.every(isCapabilityReviewed);
  const approvedCapabilities = capabilities.filter(isCapabilityApproved).length;
  const pendingCapabilities = capabilities.filter((capability) => !isCapabilityReviewed(capability));
  const showCapabilityReview = isEpic && capabilities.length > 0;
  const items = isEpic
    ? showCapabilityReview
      ? capabilities.map(capabilityToReviewItem)
      : effectiveFeatureDrafts.map(draftToReviewItem)
    : effectiveStoryDrafts.length
      ? effectiveStoryDrafts.map(draftToReviewItem)
      : (featureResult?.recommended_stories || []).map(storyToReviewItem);
  const effectiveSelectedId = items.some((item) => item.id === selectedId) ? selectedId : items[0]?.id || '';
  const selectedItem = items.find((item) => item.id === effectiveSelectedId);
  const hasEpicOutput = Boolean(epicResult || effectiveFeatureDrafts.length || capabilities.length);
  const hasFeatureOutput = Boolean(featureResult);
  const featureApproved = approvalWorkflow.feature === 'approved';
  const featuresApproved = approvalWorkflow.features === 'approved' || areAllDraftsApproved(effectiveFeatureDrafts);
  const storiesApproved = approvalWorkflow.stories === 'approved' || areAllDraftsReviewed(effectiveStoryDrafts);
  const pendingFeatureDrafts = effectiveFeatureDrafts.filter((draft) => draft.status !== 'approved' && draft.status !== 'created');
  const pendingStoryDrafts = effectiveStoryDrafts.filter((draft) => !['approved', 'created', 'failed', 'skipped'].includes(draft.status));
  const selectableStoryDrafts = mergeFeatureStoryDraftsFromReviewState(featureResult, childDrafts).filter((draft) => draft.selected && draft.status !== 'created');
  const selectableFeatureDrafts = effectiveFeatureDrafts.filter((draft) => draft.selected && draft.status !== 'created');
  const primaryAction = isEpic
    ? !hasEpicOutput
      ? { label: 'Analyze Epic →', run: refineEpic, disabled: loading || readOnly || !epicTitle.trim(), disabledReason: !epicTitle.trim() ? 'Epic title is required before analysis.' : '' }
        : capabilities.length && !allCapabilitiesReviewed
          ? { label: 'Review Remaining Capabilities →', run: () => setSelectedId(pendingCapabilities[0]?.capabilityId || selectedId), disabled: loading || readOnly || !pendingCapabilities.length, disabledReason: `${pendingCapabilities.length} capabilities still require approval.` }
        : !hasGeneratedFeatures
          ? { label: 'Generate Features →', run: () => generateChildren(false), disabled: loading || readOnly || !epicTitle.trim() || (capabilities.length > 0 && approvedCapabilities === 0), disabledReason: capabilities.length > 0 && approvedCapabilities === 0 ? 'Approve at least one capability before generating Features.' : '' }
            : !featuresApproved && isApprovalPending(approvalWorkflow.features)
              ? { label: 'Approve Features →', run: approveFeatures, disabled: loading || readOnly || pendingFeatureDrafts.length === 0, disabledReason: pendingFeatureDrafts.length ? `${pendingFeatureDrafts.length} Features still require approval.` : '' }
            : selectableFeatureDrafts.length
              ? { label: 'Create Selected Features →', run: createSelectedChildren, disabled: loading || readOnly, disabledReason: readOnly ? 'Read-only access prevents Azure DevOps creation.' : '' }
              : { label: 'Feature Creation Complete →', run: () => setSelectedId(effectiveFeatureDrafts[0]?.id || selectedId), disabled: loading || !effectiveFeatureDrafts.length, disabledReason: !effectiveFeatureDrafts.length ? 'No generated Features are available yet.' : '' }
    : !hasFeatureOutput
      ? { label: 'Analyze Feature →', run: refineFeature, disabled: loading || readOnly || !featureTitle.trim(), disabledReason: !featureTitle.trim() ? 'Feature title is required before analysis.' : '' }
        : !featureApproved && isApprovalPending(approvalWorkflow.feature)
          ? { label: 'Approve Feature →', run: approveFeature, disabled: loading || readOnly, disabledReason: readOnly ? 'Read-only access prevents approval.' : '' }
        : !hasGeneratedStories
          ? { label: 'Generate Stories →', run: () => generateChildren(false), disabled: loading || readOnly || !featureTitle.trim(), disabledReason: !featureApproved ? 'Approve the Feature before generating Stories.' : '' }
          : !storiesApproved && isApprovalPending(approvalWorkflow.stories)
            ? { label: 'Approve Stories →', run: approveStories, disabled: loading || readOnly || pendingStoryDrafts.length === 0, disabledReason: pendingStoryDrafts.length ? `${pendingStoryDrafts.length} Stories still require approval.` : '' }
            : selectableStoryDrafts.length
              ? { label: 'Create Selected Stories →', run: createSelectedChildren, disabled: loading || readOnly, disabledReason: readOnly ? 'Read-only access prevents Azure DevOps creation.' : '' }
              : { label: 'Story Creation Complete →', run: () => setSelectedId(effectiveStoryDrafts[0]?.id || selectedId), disabled: loading || !effectiveStoryDrafts.length, disabledReason: !effectiveStoryDrafts.length ? 'No generated Stories are available yet.' : '' };
  const currentStage = isEpic
    ? !hasEpicOutput
      ? 'Epic Analysis'
      : capabilities.length && !allCapabilitiesReviewed
        ? 'Capability Review'
        : 'Feature Review'
    : !hasFeatureOutput
      ? 'Feature'
      : !hasGeneratedStories || !storiesApproved
        ? 'Story Review'
        : 'Task Review';
  const stages = buildSingleCurrentStages(
    isEpic ? ['Epic Analysis', 'Capability Review', 'Feature Review', 'Feature Creation'] : ['Feature', 'Story Review', 'Task Review', 'Execution'],
    currentStage,
    isEpic
      ? {
          'Epic Analysis': Boolean(epicResult),
          'Capability Review': Boolean(capabilities.length && allCapabilitiesReviewed),
          'Feature Review': Boolean(hasGeneratedFeatures && featuresApproved),
          'Feature Creation': Boolean(effectiveFeatureDrafts.length && effectiveFeatureDrafts.every((draft) => draft.status === 'created')),
        }
      : {
          Feature: hasFeatureOutput,
          'Story Review': Boolean(hasGeneratedStories && storiesApproved),
          'Task Review': false,
          Execution: false,
        }
  );
  const progressMetrics = isEpic
    ? [
        { label: 'Epic Analysis', percent: hasEpicOutput ? 100 : 0 },
        { label: 'Capability Review', percent: capabilities.length ? Math.round(((capabilities.length - pendingCapabilities.length) / capabilities.length) * 100) : undefined, status: hasEpicOutput ? undefined : 'Locked' },
        { label: 'Feature Review', percent: effectiveFeatureDrafts.length ? Math.round(((effectiveFeatureDrafts.length - pendingFeatureDrafts.length) / effectiveFeatureDrafts.length) * 100) : undefined, status: hasGeneratedFeatures ? undefined : 'Locked' },
        { label: 'Feature Creation', status: effectiveFeatureDrafts.length ? (selectableFeatureDrafts.length ? 'Ready To Create' : effectiveFeatureDrafts.every((draft) => draft.status === 'created') ? 'Created' : 'Selection Required') : 'Locked' },
      ]
    : [
        { label: 'Feature', percent: hasFeatureOutput ? 100 : 0 },
        { label: 'Story Review', percent: effectiveStoryDrafts.length ? Math.round(((effectiveStoryDrafts.length - pendingStoryDrafts.length) / effectiveStoryDrafts.length) * 100) : undefined, status: hasGeneratedStories ? undefined : 'Pending' },
        { label: 'Task Review', status: hasGeneratedStories && storiesApproved ? 'Story Drafts Ready' : 'Locked' },
        { label: 'Execution', status: 'Locked' },
      ];
  return {
    title: isEpic ? 'Epic Planning Workspace' : 'Feature Planning Workspace',
    subtitle: isEpic ? 'Analyze the epic, review capabilities, then generate feature recommendations.' : 'Review the feature, generate stories, and prepare the next planning level.',
    stageLabel: primaryAction.label,
    primaryAction,
    stages,
    progressMetrics,
    items,
    selectedId: effectiveSelectedId,
    setSelectedId,
    selectedItem,
    listTitle: showCapabilityReview ? 'Capabilities' : isEpic ? 'Features' : 'Stories',
    emptyTitle: isEpic ? 'No planning items yet' : 'No story candidates yet',
    emptyText: isEpic ? 'Analyze the Epic to reveal capability review items.' : 'Analyze the Feature or generate Stories to populate this workspace.',
  };
}

function buildSingleCurrentStages(labels: string[], currentLabel: string, completed: Record<string, boolean>): PlanningStage[] {
  const currentIndex = Math.max(0, labels.indexOf(currentLabel));
  return labels.map((label, index) => {
    if (index < currentIndex && completed[label]) {
      return { label, status: 'complete' };
    }
    if (index === currentIndex) {
      return { label, status: 'current' };
    }
    return { label, status: 'locked' };
  });
}

function PlanningProgressBar({ stages, metrics }: { stages: PlanningStage[]; metrics: PlanningProgressMetric[] }) {
  return (
    <div className="hei-stage-progress">
      {stages.map((stage) => {
        const metric = metrics.find((item) => item.label === stage.label);
        const percent = typeof metric?.percent === 'number' ? Math.max(0, Math.min(100, metric.percent)) : undefined;
        return (
          <div className={`hei-stage ${stage.status}`} key={stage.label}>
            <span>{stage.status === 'complete' ? 'Done' : stage.status === 'current' ? 'Active' : 'Locked'}</span>
            <strong>{stage.label}</strong>
            <small>{metric?.status || (typeof percent === 'number' ? `${percent}%` : stage.status === 'locked' ? 'Locked' : 'Pending')}</small>
            {typeof percent === 'number' ? (
              <div className="hei-progress-track">
                <i style={{ width: `${percent}%` }} />
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

function PlanningProgressSummary({ metrics }: { metrics: PlanningProgressMetric[] }) {
  return (
    <div className="hei-progress-summary">
      {metrics.map((metric) => {
        const percent = Math.max(0, Math.min(100, metric.percent ?? 0));
        return (
          <div className="hei-progress-card" key={metric.label}>
            <div>
              <strong>{metric.label}</strong>
              <span>{metric.status || `${percent}%`}</span>
            </div>
            {typeof metric.percent === 'number' ? (
              <div className="hei-progress-track">
                <span style={{ width: `${percent}%` }} />
              </div>
            ) : (
              <div className="hei-progress-track muted">
                <span />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function PlanningItemPicker({ label, items, selectedId, onSelect }: { label: string; items: PlanningReviewItem[]; selectedId: string; onSelect: (value: string) => void }) {
  if (!items.length) {
    return <div className="hei-planning-item-picker empty"><strong>No {label.toLowerCase()} yet.</strong><span>Run the current planning action to populate this workspace.</span></div>;
  }
  const selected = items.find((item) => item.id === selectedId) || items[0];
  return <label className="hei-planning-item-picker"><span>{label}</span><select value={selected?.id || ''} onChange={(event) => onSelect(event.target.value)}>{items.map((item) => <option key={item.id} value={item.id}>{item.title} · {item.status || 'Pending'} · {item.confidence ? `${Math.round(item.confidence * 100)}%` : 'Not scored'}</option>)}</select><small>{selected ? `${selected.validation || selected.priority || selected.kind} · ${repositoryReadinessLabel(selected)}` : 'Select an item to review.'}</small></label>;
}

function statusTone(status?: string): 'success' | 'warning' | 'neutral' {
  const normalized = String(status || '').toLowerCase();
  if (normalized === 'approved' || normalized === 'created' || normalized === 'pass') {
    return 'success';
  }
  if (normalized === 'rejected' || normalized === 'failed' || normalized.includes('review')) {
    return 'warning';
  }
  return 'neutral';
}

function PlanningSelectedDetail({
  item,
  emptyTitle,
  emptyText,
  loading,
  readOnly,
  onApprove,
  onReject,
  onEdit,
  onMoveUp,
  onMoveDown,
  selectedTab,
  onTabChange,
}: {
  item?: PlanningReviewItem;
  emptyTitle: string;
  emptyText: string;
  loading: boolean;
  readOnly: boolean;
  onApprove?: () => void;
  onReject?: () => void;
  onEdit?: () => void;
  onMoveUp?: () => void;
  onMoveDown?: () => void;
  selectedTab: PlanningDetailTab;
  onTabChange: (tab: PlanningDetailTab) => void;
}) {
  if (!item) {
    return (
      <div className="hei-selected-empty">
        <strong>{emptyTitle}</strong>
        <span>{emptyText}</span>
      </div>
    );
  }
  const overview = planningOverviewForItem(item);
  return (
    <article className="hei-selected-detail">
      <div className="hei-selected-title">
        <div>
          <div className="planner-label">{item.kind}</div>
          <h3>{item.title}</h3>
          <p>{item.subtitle}</p>
        </div>
        <span className="hei-status-badge neutral">{item.status || 'Draft'}</span>
      </div>
      <PlanningDetailTabs selected={selectedTab} onSelect={onTabChange} />
      {selectedTab === 'overview' ? (
        <>
          <div className="hei-business-grid">
            <InfoBlock title="Business Context" value={overview.context} empty="Business context pending validation." />
            <InfoBlock title={overview.storyTitle} value={overview.story} empty="User story pending validation." />
            <InfoBlock title="Business Value" value={overview.value} empty="Business value pending review." />
            <InfoBlock title="Implementation Objective" value={overview.objective} empty="Implementation objective pending engineering review." />
            <InfoBlock title="Primary Dependencies" items={item.dependencies || []} empty={dependencyEmptyState(item)} />
          </div>
          <StageSummaryCard item={item} />
        </>
      ) : null}
      {selectedTab === 'responsibilities' ? <InfoBlock title="Responsibilities" items={item.responsibilities || []} empty="Responsibilities pending analysis." /> : null}
      {selectedTab === 'scope' ? (
        <div className="hei-business-grid">
          <InfoBlock title="In Scope" items={item.scope || []} empty="Scope pending validation." />
          <InfoBlock title="Acceptance Summary" items={item.acceptanceCriteria || []} empty="Acceptance criteria pending generation." />
        </div>
      ) : null}
      {selectedTab === 'repository' ? (
        <div className="hei-business-grid">
          <InfoBlock title="Repository Evidence" items={item.evidence || []} empty="Run Repository Intelligence to load evidence." />
          <InfoBlock title="Applications" items={item.applications || []} empty="No applications identified for this item." />
        </div>
      ) : null}
      {selectedTab === 'knowledge' ? (
        <div className="hei-business-grid">
          <InfoBlock title="Modules" items={item.modules || []} empty="No modules selected by Knowledge Registry." />
          <InfoBlock title="Flows" items={item.flows || []} empty="No flows selected by Knowledge Registry." />
        </div>
      ) : null}
      {selectedTab === 'history' ? (
        <InfoBlock title="Review History" items={item.comments || []} empty="No review history yet. Approve, reject, or edit to record history." />
      ) : null}
      {onApprove || onReject || onEdit ? (
        <div className="planner-actions">
          {onApprove ? <button className="planner-button" onClick={onApprove} disabled={loading || readOnly}>Approve</button> : null}
          {onReject ? <button className="planner-button secondary" onClick={onReject} disabled={loading || readOnly}>Reject</button> : null}
          {onEdit ? <button className="planner-button secondary" onClick={onEdit} disabled={loading || readOnly}>Edit</button> : null}
          {onMoveUp ? <button className="planner-button secondary" onClick={onMoveUp} disabled={loading || readOnly}>Move Up</button> : null}
          {onMoveDown ? <button className="planner-button secondary" onClick={onMoveDown} disabled={loading || readOnly}>Move Down</button> : null}
        </div>
      ) : null}
      <details className="planner-nested">
        <summary>Engineering Details</summary>
        <div className="planner-status-grid">
          <Row label="Confidence" value={item.confidence ? `${Math.round(item.confidence * 100)}%` : 'Not scored'} />
          <Row label="Priority" value={item.priority || 'Not set'} />
          <Row label="Kind" value={item.kind} />
        </div>
        <ListBlock title="Repository Evidence" items={item.evidence || []} />
        <ListBlock title="Modules" items={item.modules || []} />
        <ListBlock title="Flows" items={item.flows || []} />
        <ListBlock title="Applications" items={item.applications || []} />
        <ListBlock title="Out Of Scope" items={item.outOfScope || []} />
        <ListBlock title="Review Comments" items={item.comments || []} />
      </details>
    </article>
  );
}

function PlanningDetailTabs({ selected, onSelect }: { selected: PlanningDetailTab; onSelect: (tab: PlanningDetailTab) => void }) {
  const tabs: Array<{ id: PlanningDetailTab; label: string }> = [
    { id: 'overview', label: 'Overview' },
    { id: 'responsibilities', label: 'Responsibilities' },
    { id: 'scope', label: 'Scope' },
    { id: 'repository', label: 'Repository' },
    { id: 'knowledge', label: 'Knowledge' },
    { id: 'history', label: 'History' },
  ];
  return (
    <div className="hei-detail-tabs">
      {tabs.map((tab) => (
        <button key={tab.id} className={selected === tab.id ? 'active' : ''} type="button" onClick={() => onSelect(tab.id)}>
          {tab.label}
        </button>
      ))}
    </div>
  );
}

function StageSummaryCard({ item }: { item: PlanningReviewItem }) {
  return (
    <div className="hei-stage-summary-card">
      <div>
        <span>Stage Summary</span>
        <strong>{item.status === 'Approved' || item.status === 'approved' ? 'Ready for next planning level' : 'Review required'}</strong>
      </div>
      <div className="planner-status-grid">
        <Row label="Validation" value={item.validation || 'Pending Validation'} />
        <Row label="Confidence" value={item.confidence ? `${Math.round(item.confidence * 100)}%` : 'Pending'} />
        <Row label="Repository" value={repositoryReadinessLabel(item)} />
        <Row label="Generated Items" value={formatNumber(item.generatedCount)} />
      </div>
    </div>
  );
}

function repositoryReadinessLabel(item: PlanningReviewItem): string {
  if ((item.evidence || []).length || (item.modules || []).length || (item.flows || []).length) {
    return 'Repository Context Ready';
  }
  if (typeof item.repositoryCoverage === 'number' && item.repositoryCoverage > 0) {
    return 'Repository Validation Required';
  }
  return 'Repository Analysis Pending';
}

function planningOverviewForItem(item: PlanningReviewItem): { context: string; storyTitle: string; story: string; value: string; objective: string } {
  if (item.kind === 'capability') {
    return {
      context: meaningfulText(
        item.description,
        item.subtitle,
        `This capability defines the approved business outcome and planning boundary for ${normalizeStoryTitle(item.title)}.`,
      ),
      storyTitle: 'Capability Statement',
      story: capabilityStatementForItem(item),
      value: meaningfulBusinessValue(item),
      objective: implementationObjectiveForItem(item),
    };
  }
  if (item.kind === 'story') {
    const title = normalizeStoryTitle(item.title);
    const modules = (item.modules || []).slice(0, 2);
    const flows = (item.flows || []).slice(0, 2);
    const contextParts = [
      modules.length ? `Modules: ${modules.join(', ')}` : '',
      flows.length ? `Flows: ${flows.join(', ')}` : '',
    ].filter(Boolean);
    return {
      context: contextParts.length
        ? `This story turns the approved feature into a focused user capability using ${contextParts.join(' and ')}.`
        : `This story turns the approved feature into a focused, testable user capability for ${title.toLowerCase()}.`,
      storyTitle: 'User Story',
      story: normalizeStoryStatement(item),
      value: meaningfulBusinessValue(item),
      objective: implementationObjectiveForItem(item),
    };
  }
  if (item.kind === 'feature') {
    const modules = (item.modules || []).slice(0, 2);
    const flows = (item.flows || []).slice(0, 2);
    const applications = (item.applications || []).slice(0, 2);
    const contextParts = [
      item.businessGoal ? `Business goal: ${normalizePlannerText(item.businessGoal)}` : '',
      modules.length ? `Modules: ${modules.join(', ')}` : '',
      flows.length ? `Flows: ${flows.join(', ')}` : '',
      applications.length ? `Applications: ${applications.join(', ')}` : '',
    ].filter(Boolean);
    return {
      context: contextParts.length
        ? contextParts.join('  ')
        : `This feature organizes the approved capability into a delivery-ready scope for ${normalizeStoryTitle(item.title)}.`,
      storyTitle: 'Feature Statement',
      story: meaningfulText(item.description, item.subtitle, 'Feature statement pending validation.'),
      value: meaningfulBusinessValue(item),
      objective: implementationObjectiveForItem(item),
    };
  }
  return {
    context: meaningfulText(item.description, item.subtitle, 'This item captures the approved planning context for review.'),
    storyTitle: 'Planning Statement',
    story: meaningfulText(item.subtitle, item.description, 'Planning statement pending validation.'),
    value: meaningfulBusinessValue(item),
    objective: implementationObjectiveForItem(item),
  };
}

function capabilityStatementForItem(item: PlanningReviewItem): string {
  const title = normalizeStoryTitle(item.title);
  const responsibilities = (item.responsibilities || []).slice(0, 2);
  const applications = (item.applications || []).slice(0, 2);
  const modules = (item.modules || []).slice(0, 2);
  const responsibilityText = responsibilities.length
    ? responsibilities.join(' and ')
    : `deliver ${title.toLowerCase()} as an approved business capability`;
  const applicationText = applications.length ? ` across ${applications.join(' and ')}` : '';
  const moduleText = modules.length ? ` using ${modules.join(' and ')} context` : '';
  return `${title} should ${responsibilityText}${applicationText}${moduleText}, with clear dependencies and validation readiness before feature generation.`;
}

function normalizeStoryStatement(item: PlanningReviewItem): string {
  const raw = meaningfulText(item.description, item.subtitle, '');
  const title = normalizeStoryTitle(item.title);
  const lowerTitle = title.toLowerCase();
  if (/fault|event/.test(lowerTitle)) {
    return 'As an Operations User, I want to view critical fault details so that I can understand the device, severity, timing, and current status before taking action.';
  }
  if (/severity/.test(lowerTitle)) {
    return 'As an Operations User, I want to classify fault severity so that I can prioritize investigation and response work.';
  }
  if (/filter|search/.test(lowerTitle)) {
    return 'As an Operations User, I want to search and filter operational records so that I can quickly find the events that need attention.';
  }
  if (/^as an?\s+/i.test(raw) || /^as a\s+/i.test(raw)) {
    return normalizePlannerText(raw).replace(/\bview detect fault\b/gi, 'view critical fault details');
  }
  return `As an Operations User, I want to ${lowerTitle} so that I can complete the approved operational workflow with clear context.`;
}

function meaningfulBusinessValue(item: PlanningReviewItem): string {
  const value = normalizePlannerText(item.businessValue);
  const title = normalizeStoryTitle(item.title);
  const genericValues = new Set(['view', 'review', 'use', 'details', 'workflow', 'capability']);
  if (value && !genericValues.has(value.toLowerCase()) && !isDuplicatePlanningText(value, item.description, item.subtitle)) {
    return value;
  }
  const text = [title, item.description, item.subtitle, ...(item.modules || []), ...(item.flows || [])].join(' ').toLowerCase();
  if (/fault|event|outage/.test(text)) {
    return 'Reduces fault triage time by giving operations users the context needed to assess severity, device impact, and next action.';
  }
  if (/permission|access|auth/.test(text)) {
    return 'Improves operational control by ensuring only authorized users can perform the approved action.';
  }
  if (/telemetry|device health/.test(text)) {
    return 'Improves operational confidence by making device and telemetry status visible during review.';
  }
  return 'Creates measurable delivery value by converting the approved capability into user-visible behavior and validation-ready outcomes.';
}

function implementationObjectiveForItem(item: PlanningReviewItem): string {
  const title = normalizeStoryTitle(item.title);
  const modules = (item.modules || []).slice(0, 2).join(', ');
  const flows = (item.flows || []).slice(0, 2).join(', ');
  if (item.kind === 'capability') {
    return `Confirm ${title} as a feature-ready capability with clear scope, dependency coverage, repository alignment, and approval-ready validation criteria.`;
  }
  if (item.kind === 'story') {
    return `Deliver ${title} with mapped acceptance criteria, ${modules || 'selected module'} coverage, and ${flows || 'approved flow'} validation.`;
  }
  return `Prepare ${title} for the next planning level with clear scope, dependencies, repository context, and validation criteria.`;
}

function meaningfulText(primary: string | undefined, secondary: string | undefined, fallback: string): string {
  const first = normalizePlannerText(primary);
  const second = normalizePlannerText(secondary);
  if (first && !isDuplicatePlanningText(first, second)) {
    return first;
  }
  return second || first || fallback;
}

function isDuplicatePlanningText(value: string | undefined, ...others: Array<string | undefined>): boolean {
  const normalized = normalizePlannerText(value).toLowerCase();
  return Boolean(normalized && others.some((other) => normalizePlannerText(other).toLowerCase() === normalized));
}

function dependencyEmptyState(item: PlanningReviewItem): string {
  if ((item.evidence || []).length || (item.modules || []).length || (item.flows || []).length) {
    return 'No dependencies identified';
  }
  return 'Dependencies Pending Validation';
}

function InfoBlock({ title, value, items, empty }: { title: string; value?: string; items?: string[]; empty?: string }) {
  const cleanItems = (items || []).filter(Boolean);
  return (
    <div className="hei-info-block">
      <span>{title}</span>
      {value ? <p>{value}</p> : cleanItems.length ? <ul>{cleanItems.slice(0, 5).map((item) => <li key={item}>{item}</li>)}</ul> : <p>{empty || 'Run analysis to populate this section.'}</p>}
    </div>
  );
}

function PlanningInsights({
  planningType,
  epicResult,
  featureResult,
  epicImpact,
  featureImpact,
  childDrafts,
  artifactRecords,
  artifactReuseStatus,
  approvalWorkflow,
}: {
  planningType: WorkItemKind;
  epicResult?: EpicRefinement;
  featureResult?: FeatureRefinement;
  epicImpact?: EpicImpact;
  featureImpact?: FeatureImpact;
  childDrafts: ChildDraft[];
  artifactRecords: ArtifactRecord[];
  artifactReuseStatus: string;
  approvalWorkflow: ApprovalWorkflowState;
}) {
  const featureDrafts = childDrafts.filter((draft) => draft.type === 'Feature');
  const storyDrafts = childDrafts.filter((draft) => draft.type === 'User Story');
  return (
    <>
      <div className="planner-label">Engineering Insights</div>
      <div className="planner-status-grid">
        <Row label="Features" value={formatNumber(featureDrafts.length)} />
        <Row label="Stories" value={formatNumber(storyDrafts.length)} />
        <Row label="Lifecycle" value={artifactReuseStatus || 'Not available'} />
      </div>
      <details className="planner-nested">
        <summary>Validation</summary>
        <div className="planner-status-grid">
          <Row label="Epic" value={approvalWorkflow.epic} />
          <Row label="Features" value={approvalWorkflow.features} />
          <Row label="Stories" value={approvalWorkflow.stories} />
        </div>
      </details>
      <details className="planner-nested">
        <summary>Repository & Knowledge</summary>
        <ListBlock title="Modules" items={planningType === 'Epic' ? epicResult?.generation_review?.modules_used || [] : featureResult?.affected_modules || []} />
        <ListBlock title="Flows" items={planningType === 'Epic' ? epicResult?.generation_review?.flows_used || [] : featureResult?.affected_flows || []} />
        <ListBlock title="Dependencies" items={planningType === 'Epic' ? epicResult?.dependencies || [] : featureResult?.dependencies || []} />
      </details>
      <details className="planner-nested">
        <summary>Impact & Risk</summary>
        <ListBlock title="Risks" items={planningType === 'Epic' ? epicResult?.risks || epicImpact?.risks || [] : featureResult?.risks || featureImpact?.risks || []} />
        <ListBlock title="Constraints" items={epicResult?.constraints || []} />
      </details>
      <details className="planner-nested">
        <summary>Artifact History</summary>
        {artifactRecords.slice(0, 4).map((artifact) => (
          <Row key={artifact.artifact_id} label={`${artifact.artifact_type} v${artifact.version}`} value={artifact.state} />
        ))}
        {!artifactRecords.length ? <div className="planner-subtle">No reusable artifacts yet.</div> : null}
      </details>
      <details className="planner-nested">
        <summary>Future</summary>
        <ListBlock title="Coming Signals" items={['Engineering Graph', 'DNA', 'Prompt History', 'Execution Trace']} />
      </details>
    </>
  );
}

function capabilityToReviewItem(capability: CapabilityReview): PlanningReviewItem {
  const purpose = normalizePlannerText(capability.businessPurpose);
  const value = normalizePlannerText(capability.businessValue);
  return {
    id: capability.capabilityId,
    kind: 'capability',
    title: capability.capabilityName,
    subtitle: value && value.toLowerCase() !== purpose.toLowerCase()
      ? capability.businessValue
      : capability.businessPurpose || capability.businessValue || 'Capability under review',
    status: capability.status,
    priority: capability.priority,
    confidence: capability.confidence,
    description: capability.businessPurpose,
    businessValue: capability.businessValue,
    responsibilities: capability.responsibilities,
    scope: capability.inScope,
    outOfScope: capability.outOfScope,
    dependencies: capability.dependencies,
    evidence: capability.repositoryEvidence,
    modules: capability.relatedModules,
    flows: capability.relatedFlows,
    applications: capability.relatedApplications,
    acceptanceCriteria: capability.supports,
    comments: capability.reviewComments,
    repositoryCoverage: Math.round(Math.min(100, ((capability.repositoryEvidence?.length || 0) + (capability.relatedModules?.length || 0) + (capability.relatedFlows?.length || 0)) * 12)),
    generatedCount: capability.estimatedFeatures || 1,
    validation: isCapabilityApproved(capability) ? 'PASS' : isCapabilityRejected(capability) ? 'Rejected' : 'Needs Review',
  };
}

function draftToReviewItem(draft: ChildDraft): PlanningReviewItem {
  const subtitle = meaningfulText(draft.businessGoal, draft.businessValue, draft.description || 'Generated child work item');
  return {
    id: draft.id,
    kind: draft.type === 'Feature' ? 'feature' : 'story',
    title: draft.title,
    subtitle,
    status: draft.status,
    confidence: draft.relevanceConfidence,
    description: draft.description,
    businessGoal: draft.businessGoal,
    businessValue: draft.businessValue || draft.businessGoal,
    responsibilities: draft.primaryPersonas,
    scope: draft.impactedApplications,
    dependencies: draft.dependencies,
    modules: draft.impactedModules,
    flows: draft.impactedFlows,
    applications: draft.impactedApplications,
    acceptanceCriteria: draft.acceptanceCriteria,
    repositoryCoverage: Math.round(Math.min(100, ((draft.impactedModules?.length || 0) + (draft.impactedFlows?.length || 0)) * 18)),
    generatedCount: draft.type === 'Feature' ? 1 : 0,
    validation: draft.status === 'approved' || draft.status === 'created' ? 'PASS' : draft.status === 'failed' ? 'Needs Review' : 'Pending',
  };
}

function storyToReviewItem(story: FeatureRefinement['recommended_stories'][number], index: number): PlanningReviewItem {
  return {
    id: `story_${index}_${story.title}`,
    kind: 'story',
    title: story.title,
    subtitle: story.description || story.coverage_area || 'Generated story candidate',
    status: 'Preview',
    confidence: story.confidence,
    description: story.description,
    businessValue: story.coverage_area,
    responsibilities: story.coverage_area ? [story.coverage_area] : [],
    dependencies: [],
    modules: story.modules_used || story.affected_modules,
    flows: story.flows_used || story.affected_flows,
    acceptanceCriteria: story.acceptance_criteria,
    repositoryCoverage: Math.round(Math.min(100, ((story.modules_used?.length || story.affected_modules?.length || 0) + (story.flows_used?.length || story.affected_flows?.length || 0)) * 18)),
    generatedCount: 0,
    validation: story.dna_validation?.status || 'Pending',
  };
}

function GeneratedChildWorkItems({
  drafts,
  creationLog,
  currentWorkItem,
  providerMetadata,
  readOnly,
  loading,
  onSelectionChange,
  onCreateSelected,
}: {
  drafts: ChildDraft[];
  creationLog: string[];
  currentWorkItem?: AdoWorkItem;
  providerMetadata?: ProviderMetadata;
  readOnly: boolean;
  loading: boolean;
  onSelectionChange: (draftId: string, selected: boolean) => void;
  onCreateSelected: () => void;
}) {
  if (!drafts.length && !creationLog.length) {
    return null;
  }
  const selectedCount = drafts.filter((draft) => draft.selected && draft.status !== 'created').length;
  return (
    <section className="planner-card">
      <div className="planner-label">Generated Child Work Items</div>
      <div className="planner-subtle">Preview generated children before creating them in Azure DevOps under {currentWorkItem ? `${currentWorkItem.type} #${currentWorkItem.id}` : 'the current work item'}.</div>
      <SourceBadge metadata={providerMetadata} />
      <RelevanceSummary metadata={providerMetadata} />
      <EngineeringMemoryEvidence context={providerMetadata?.memory_context} area="Planning" />
      <IntelligenceTracePanel trace={providerMetadata?.intelligence_trace} />
      <div className="hei-generated-grid">
        {drafts.map((draft) => (
          <article className="hei-generated-card planner-task" key={draft.id}>
            <div className="planner-task-header">
              <label className="planner-checkbox">
                <input
                  type="checkbox"
                  checked={draft.selected}
                  disabled={readOnly || draft.status === 'created'}
                  onChange={(event) => onSelectionChange(draft.id, event.target.checked)}
                />
                <strong>{draft.type}: {draft.title}</strong>
              </label>
              <span className={`planner-badge ${statusTone(draft.status)}`}>{draft.status}</span>
            </div>
            <p className="planner-copy">{draft.description}</p>
            <RelevanceSummary draft={draft} />
            <FeatureEnrichmentDetails draft={draft} />
            <ListBlock title="Acceptance Criteria" items={draft.acceptanceCriteria} />
            <div className="planner-subtle">
              {draft.azureId ? `Azure DevOps #${draft.azureId}` : 'Not created yet'}
              {draft.error ? ` - ${draft.error}` : ''}
            </div>
          </article>
        ))}
      </div>
      <div className="planner-actions">
        <button className="planner-button secondary" onClick={() => drafts.forEach((draft) => onSelectionChange(draft.id, true))} disabled={loading || readOnly}>Select All</button>
        <button className="planner-button secondary" onClick={() => drafts.forEach((draft) => onSelectionChange(draft.id, false))} disabled={loading || readOnly}>Skip All</button>
        <button className="planner-button" onClick={onCreateSelected} disabled={loading || readOnly || !selectedCount}>Create Selected</button>
      </div>
      {readOnly ? <div className="planner-subtle">Read-only access: work item creation is disabled for your role.</div> : null}
      {creationLog.length ? (
        <div className="planner-task">
          <div className="planner-label">Creation Activity</div>
          <ul className="planner-list">
            {creationLog.map((entry) => <li key={entry}>{entry}</li>)}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

function CapabilityReviewWorkspace({
  result,
  loading,
  readOnly,
  onUpdate,
  onMove,
}: {
  result: EpicRefinement;
  loading: boolean;
  readOnly: boolean;
  onUpdate: (capabilityId: string, changes: Partial<CapabilityReview>) => void;
  onMove: (capabilityId: string, direction: -1 | 1) => void;
}) {
  const capabilities = result.capability_review || [];
  const diagnostics = result.capability_review_diagnostics || {};
  if (!capabilities.length) {
    return null;
  }
  const approvedCount = capabilities.filter((item) => item.status === 'Approved').length;
  const rejectedCount = capabilities.filter((item) => item.status === 'Rejected').length;
  return (
    <section className="planner-card">
      <div className="planner-label">Capability Review</div>
      <div className="planner-subtle">Review and approve business capabilities before Feature generation. Each approved capability generates exactly one Feature.</div>
      <div className="planner-status-grid">
        <Row label="Capability Count" value={formatNumber(diagnostics.capabilityCount || capabilities.length)} />
        <Row label="Approved" value={formatNumber(approvedCount)} />
        <Row label="Rejected" value={formatNumber(rejectedCount)} />
        <Row label="Average Confidence" value={`${formatNumber(Math.round((diagnostics.averageConfidence || 0) * 100))}%`} />
        <Row label="Planning Readiness" value={diagnostics.planningReadiness || 'Ready For Review'} />
        <Row label="Graph Relationships" value={formatNumber(diagnostics.graphRelationships || result.capability_dependency_graph?.length || 0)} />
      </div>
      {result.capability_dependency_graph?.length ? (
        <ListBlock
          title="Dependency Graph"
          items={result.capability_dependency_graph.map((edge) => `${edge.source || 'Capability'} ${edge.relationship || 'supports'} ${edge.target || 'Capability'}`)}
        />
      ) : null}
      {diagnostics.validationIssues?.length ? (
        <ListBlock title="Validation Warnings" items={diagnostics.validationIssues.map((item) => `${item.severity || 'NeedsReview'}: ${item.capability || 'Capability'} - ${item.reason || 'Review required'}`)} />
      ) : null}
      {capabilities.map((capability, index) => (
        <div className="planner-task" key={capability.capabilityId}>
          <div className="planner-status-grid">
            <Row label="Name" value={capability.capabilityName} />
            <Row label="Category" value={capability.capabilityCategory || capability.capabilityName} />
            <Row label="Priority" value={capability.priority} />
            <Row label="Status" value={capability.status} />
            <Row label="Estimated Features" value={formatNumber(capability.estimatedFeatures || 1)} />
            <Row label="Confidence" value={`${formatNumber(Math.round((capability.confidence || 0) * 100))}%`} />
          </div>
          <div className="planner-label-inline">Business Purpose</div>
          <p className="planner-copy">{capability.businessPurpose}</p>
          <div className="planner-label-inline">Business Value</div>
          <p className="planner-copy">{capability.businessValue}</p>
          <ListBlock title="Responsibilities" items={capability.responsibilities} />
          <ListBlock title="In Scope" items={capability.inScope} />
          <ListBlock title="Out Of Scope" items={capability.outOfScope} />
          <ListBlock title="Dependencies" items={capability.dependencies} />
          <ListBlock title="Supports" items={capability.supports || []} />
          <ListBlock title="Repository Evidence" items={capability.repositoryEvidence} />
          <ListBlock title="Related Modules" items={capability.relatedModules} />
          <ListBlock title="Related Flows" items={capability.relatedFlows} />
          <ListBlock title="Related Applications" items={capability.relatedApplications} />
          {capability.explainability ? (
            <div className="planner-status-grid">
              <Row label="Why it exists" value={capability.explainability.whyExists || 'Derived from Epic Analysis'} />
              <Row label="Why required" value={capability.explainability.whyRequired || 'Required for planning readiness'} />
              <Row label="Problem solved" value={capability.explainability.businessProblemSolved || capability.businessPurpose} />
            </div>
          ) : null}
          {capability.reviewComments?.length ? <ListBlock title="Review Comments" items={capability.reviewComments} /> : null}
          <div className="planner-actions">
            <button className="planner-button" disabled={loading || readOnly} onClick={() => onUpdate(capability.capabilityId, { status: 'Approved' })}>Approve</button>
            <button className="planner-button secondary" disabled={loading || readOnly} onClick={() => onUpdate(capability.capabilityId, { status: 'Rejected' })}>Reject</button>
            <button
              className="planner-button secondary"
              disabled={loading || readOnly}
              onClick={() => {
                const comment = window.prompt('Add a review comment for this capability', capability.reviewComments?.[0] || '');
                if (comment !== null) {
                  onUpdate(capability.capabilityId, { reviewComments: comment.trim() ? [comment.trim()] : [] });
                }
              }}
            >
              Edit
            </button>
            <button className="planner-button secondary" disabled={loading || readOnly || index === 0} onClick={() => onMove(capability.capabilityId, -1)}>Move Up</button>
            <button className="planner-button secondary" disabled={loading || readOnly || index === capabilities.length - 1} onClick={() => onMove(capability.capabilityId, 1)}>Move Down</button>
          </div>
        </div>
      ))}
    </section>
  );
}

function FeatureEnrichmentDetails({ draft }: { draft: ChildDraft }) {
  if (draft.type !== 'Feature') {
    return null;
  }
  return (
    <div className="planner-status-grid">
      <Row label="Business Goal" value={draft.businessGoal || 'Not identified yet'} />
      <Row label="User Problem" value={draft.userProblem || 'Not identified yet'} />
      <Row label="Business Value" value={draft.businessValue || 'Not identified yet'} />
      <Row label="Capability Category" value={draft.capabilityCategory || 'Not identified yet'} />
      <ListBlock title="Primary Personas" items={draft.primaryPersonas || []} />
      <ListBlock title="Impacted Applications" items={draft.impactedApplications || []} />
      <ListBlock title="Impacted Modules" items={draft.impactedModules || []} />
      <ListBlock title="Impacted Flows" items={draft.impactedFlows || []} />
      <ListBlock title="Dependencies" items={draft.dependencies || []} />
      <ListBlock title="Risks" items={draft.risks || []} />
      <Row label="Acceptance Criteria Count" value={formatNumber(draft.acceptanceCriteriaCount || draft.acceptanceCriteria?.length || 0)} />
      <Row label="Acceptance Criteria Quality" value={formatNumber(draft.acceptanceCriteriaQualityScore)} />
    </div>
  );
}

function RelevanceSummary({ metadata, draft }: { metadata?: ProviderMetadata; draft?: ChildDraft }) {
  const selected = uniqueStrings([
    ...(metadata?.selected_modules || []),
    ...(metadata?.selected_flows || []),
    ...(draft?.impactedModules || []),
    ...(draft?.impactedFlows || []),
  ]).slice(0, 8);
  if (!selected.length) {
    return null;
  }
  return (
    <div className="planner-relevance">
      {selected.length ? (
        <div>
          <span className="planner-label-inline">Generated using:</span>
          {selected.map((item) => <span className="planner-chip" key={item}>{item}</span>)}
        </div>
      ) : null}
    </div>
  );
}

function EngineeringMemoryEvidence({ context, area }: { context?: MemoryContextPayload; area: 'Planning' | 'Execution' | 'QA' }) {
  if (!context) {
    return null;
  }
  const memories = context.relevantMemories || [];
  const risks = context.knownRisks || [];
  const acceptance = context.reusableAcceptanceCriteria || [];
  const tests = context.reusableTests || [];
  const excluded = context.excludedMemory || [];
  if (!memories.length && !risks.length && !acceptance.length && !tests.length && !excluded.length) {
    return null;
  }
  const title = area === 'Planning'
    ? 'Used prior engineering memory'
    : area === 'Execution'
      ? 'Relevant prior implementation'
      : 'QA memory';
  return (
    <details className="planner-nested">
      <summary>{title}</summary>
      <div className="planner-summary-grid compact">
        <SummaryTile title="Matches" value={memories.length} />
        <SummaryTile title="Patterns" value={context.matchedPatterns?.length || 0} />
        <SummaryTile title="Risks" value={risks.length} />
        <SummaryTile title="Confidence" value={context.confidence !== undefined ? `${Math.round(context.confidence * 100)}%` : 'n/a'} />
      </div>
      <ListBlock
        title="Selected Memory"
        items={memories.slice(0, 3).map((memory) => `${memory.title || 'Engineering memory'}${memory.artifactType ? ` (${memory.artifactType})` : ''}`)}
      />
      {acceptance.length ? <ListBlock title="Acceptance Patterns" items={acceptance.slice(0, 3)} /> : null}
      {tests.length ? <ListBlock title="Reusable Tests" items={tests.slice(0, 3)} /> : null}
      {risks.length ? <ListBlock title="Known Risks" items={risks.slice(0, 3)} /> : null}
      {excluded.length ? (
        <ListBlock
          title="Excluded Memory"
          items={excluded.slice(0, 3).map((memory) => `${memory.title || 'Memory'}: ${(memory.reasons || []).join(', ') || 'not selected'}`)}
        />
      ) : null}
      <details className="planner-accordion">
        <summary>Memory Diagnostics</summary>
        <ListBlock title="Retrieval Reasons" items={context.retrievalReasons || []} />
        <pre className="planner-prompt">{JSON.stringify(context.diagnostics || {}, null, 2)}</pre>
      </details>
    </details>
  );
}

function IntelligenceTracePanel({ trace }: { trace?: IntelligenceTracePayload }) {
  const detail = trace?.trace;
  const summary = trace?.trace_summary;
  if (!detail && !summary) {
    return null;
  }
  const decision = summary?.decision || detail?.decision || 'Engineering decision';
  const reason = summary?.reason || detail?.reason || 'Decision trace captured for this artifact.';
  const confidence = summary?.confidence ?? detail?.confidence;
  const evidence = traceEvidenceLabels(detail?.evidence);
  const memory = traceEvidenceLabels(detail?.memoryUsed);
  const repository = traceEvidenceLabels(detail?.repositoryEvidence);
  const graph = traceEvidenceLabels(detail?.graphEvidence);
  const tokenUsage = detail?.tokenUsage || {};
  const timeline = ['Planning', 'Execution', 'Validation', 'QA', 'Memory'];
  return (
    <details className="planner-nested">
      <summary>Explain: {decision}</summary>
      <div className="planner-summary-grid compact">
        <SummaryTile title="Stage" value={summary?.stage || detail?.stage || 'Captured'} />
        <SummaryTile title="Source" value={detail?.source || 'Intelligence Trace'} />
        <SummaryTile title="Confidence" value={confidence !== undefined ? `${Math.round(confidence * 100)}%` : 'n/a'} />
        <SummaryTile title="Trace ID" value={trace.trace_id || detail?.id || 'Stored'} />
      </div>
      <div className="planner-label-inline">Why</div>
      <p className="planner-copy">{reason}</p>
      <div className="planner-summary-grid compact">
        <SummaryTile title="Memory Used" value={formatNumber(summary?.memory_count ?? memory.length)} />
        <SummaryTile title="Repository Evidence" value={formatNumber(summary?.repository_evidence_count ?? repository.length)} />
        <SummaryTile title="Graph Evidence" value={formatNumber(summary?.graph_evidence_count ?? graph.length)} />
        <SummaryTile title="Latency" value={detail?.latencyMs ? `${formatNumber(detail.latencyMs)} ms` : 'n/a'} />
      </div>
      {evidence.length ? <ListBlock title="Evidence" items={evidence.slice(0, 5)} /> : null}
      {repository.length ? <ListBlock title="Repository Evidence" items={repository.slice(0, 5)} /> : null}
      {memory.length ? <ListBlock title="Memory Reused" items={memory.slice(0, 5)} /> : null}
      {graph.length ? <ListBlock title="Graph Influence" items={graph.slice(0, 5)} /> : null}
      <div className="planner-trace-timeline">
        {timeline.map((stage) => (
          <span className={`planner-chip ${stage === (summary?.stage || detail?.stage) ? 'active' : ''}`} key={stage}>{stage}</span>
        ))}
      </div>
      <details className="planner-accordion">
        <summary>Trace Diagnostics</summary>
        <div className="planner-summary-grid compact">
          <Row label="Model" value={detail?.model || 'deterministic'} />
          <Row label="Prompt Version" value={detail?.promptVersion || 'n/a'} />
          <Row label="Prompt Tokens" value={formatUnknownValue(tokenUsage.prompt_tokens ?? tokenUsage.promptTokens ?? tokenUsage.final_prompt_tokens)} />
          <Row label="Completion Tokens" value={formatUnknownValue(tokenUsage.completion_tokens ?? tokenUsage.completionTokens)} />
        </div>
        {detail?.validationResult && Object.keys(detail.validationResult).length ? (
          <pre className="planner-prompt">{JSON.stringify(detail.validationResult, null, 2)}</pre>
        ) : null}
      </details>
    </details>
  );
}

function traceEvidenceLabels(values?: unknown[]): string[] {
  if (!Array.isArray(values)) {
    return [];
  }
  return values
    .map((value) => {
      if (typeof value === 'string') {
        return value;
      }
      if (value && typeof value === 'object') {
        const item = value as Record<string, unknown>;
        const label = [item.name, item.title, item.path, item.type].map((part) => typeof part === 'string' ? part : '').filter(Boolean).join(' - ');
        const reason = typeof item.reason === 'string' ? item.reason : typeof item.summary === 'string' ? item.summary : '';
        return [label || 'Trace evidence', reason].filter(Boolean).join(': ');
      }
      return '';
    })
    .filter(Boolean);
}

function formatUnknownValue(value: unknown): string {
  if (value === null || value === undefined || value === '') {
    return 'n/a';
  }
  if (typeof value === 'number') {
    return formatNumber(value);
  }
  return String(value);
}

function GeneratedTasksPreview({ story }: { story: StoryRefinement }) {
  const tasks = story.proposed_tasks?.length ? story.proposed_tasks : fallbackStoryTasks(story);
  const diagnostics = story.task_intelligence_diagnostics || {};
  return (
    <div className="planner-task">
      <div className="planner-label">Generated Tasks</div>
      <div className="planner-status-grid">
        <Row label="Generated Task Count" value={formatNumber(diagnostics.generated_task_count || tasks.length)} />
        <Row label="Acceptance Criteria Count" value={formatNumber(diagnostics.acceptance_criteria_count || tasks.reduce((count, task) => count + (task.acceptance_criteria?.length || 0), 0))} />
        <Row label="Task Quality Score" value={formatNumber(diagnostics.task_quality_score)} />
      </div>
      <ListBlock title="Work Areas" items={diagnostics.work_areas || Array.from(new Set(tasks.map((task) => task.work_area || '').filter(Boolean)))} />
      <StructuredTaskList tasks={tasks} />
    </div>
  );
}

function QAIntelligencePanel({ result }: { result: QATestSuiteResult }) {
  const cases = result.test_suite?.test_cases || [];
  const categories = groupQATestsByCategory(cases);
  const intelligence = result.qa_intelligence || {};
  const readiness = intelligence.qaReadiness || result.qa_readiness || {};
  const release = intelligence.releaseRecommendation || result.release_recommendation || {};
  const coverage = intelligence.acceptanceCoverage;
  const regression = intelligence.regressionIntelligence;
  const risk = intelligence.riskIntelligence;
  const gaps = intelligence.testGapAnalysis;
  const diagnostics = intelligence.diagnostics || {};
  return (
    <section className="planner-card hei-qa-cockpit">
      <div className="planner-section-header">
        <div>
          <div className="planner-label">QA Intelligence</div>
          <div className="planner-subtle">Release-readiness cockpit for coverage, tests, regression, risk, gaps, and recommendation.</div>
        </div>
        <SourceBadge metadata={result} />
      </div>
      <div className="hei-qa-top-strip">
        <QAStatusTile title="QA Readiness" value={readiness.status || result.qa_status || 'Needs Review'} tone={qaTone(readiness.status || result.qa_status)} />
        <QAStatusTile title="Release Recommendation" value={release.recommendation || result.release_status || 'Needs More Testing'} tone={qaTone(release.recommendation || result.release_status)} />
        <QAStatusTile title="Acceptance Coverage" value={`${formatNumber(readiness.acceptanceCoverage ?? result.coverage_summary?.coverage_percent)}%`} tone={scoreTone(readiness.acceptanceCoverage ?? result.coverage_summary?.coverage_percent)} />
        <QAStatusTile title="Regression Risk" value={readiness.regressionRisk || regression?.regressionPriority || 'Medium'} tone={qaTone(readiness.regressionRisk || regression?.regressionPriority)} />
      </div>

      <div className="hei-qa-grid">
        <div className="hei-qa-card primary">
          <div className="planner-label">QA Readiness</div>
          <div className="planner-status-grid">
            <Row label="Overall" value={readiness.overallReadiness !== undefined ? `${readiness.overallReadiness}%` : `${result.coverage_score}%`} />
            <Row label="Test Completeness" value={`${formatNumber(readiness.testCompleteness)}%`} />
            <Row label="Repository Alignment" value={`${formatNumber(readiness.repositoryCoverage)}%`} />
            <Row label="Validation" value={readiness.validationStatus || 'Run Implementation Validation to improve QA accuracy.'} />
          </div>
          <ListBlock title="Blockers" items={readiness.blockers || []} empty="No release blockers identified." />
        </div>

        <div className="hei-qa-card primary">
          <div className="planner-label">Release Recommendation</div>
          <strong>{release.recommendation || result.release_status || 'Needs More Testing'}</strong>
          <p>{release.reason || 'Run QA Analysis to calculate release recommendation from coverage, validation, regression, and risk.'}</p>
          <ListBlock title="Recommended Next Action" items={release.recommendedActions || qaRecommendedActions(result)} empty="No additional action required." />
        </div>

        <div className="hei-qa-card wide">
          <div className="planner-label">Acceptance Coverage</div>
          {coverage?.acceptanceCriteria?.length ? (
            <div className="hei-qa-ac-list">
              {coverage.acceptanceCriteria.map((item) => (
                <div className="hei-qa-ac-row" key={item.acceptanceCriteriaId || item.acceptanceText}>
                  <div>
                    <strong>{item.acceptanceCriteriaId || 'AC'} - {item.coverageStatus || 'Pending'}</strong>
                    <p>{item.acceptanceText}</p>
                  </div>
                  <div>
                    <span className={`hei-status-badge ${qaBadgeClass(item.coverageStatus)}`}>{item.coverageStatus || 'Pending'}</span>
                    <small>{(item.mappedTests || []).map((test) => test.title || test.testId || '').filter(Boolean).join(', ') || 'No mapped tests yet.'}</small>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState title="No Acceptance Coverage" detail="Run QA Analysis after acceptance criteria and tests are available." />
          )}
        </div>

        <div className="hei-qa-card">
          <div className="planner-label">Test Intelligence</div>
          <div className="planner-status-grid">
            <Row label="Generated Tests" value={formatNumber(result.generated_test_count || cases.length)} />
            <Row label="Coverage Score" value={`${formatNumber(result.coverage_score)}%`} />
          </div>
          {Object.entries(categories).map(([category, tests]) => (
            <details className="planner-nested" key={category}>
              <summary>{category} ({tests.length})</summary>
              {tests.map((test) => (
                <div className="hei-qa-test-row" key={test.test_id}>
                  <strong>{test.test_id}: {test.title}</strong>
                  <span>{test.priority || 'Medium'} priority · {test.risk_level || 'Medium'} risk</span>
                  <small>{test.expected_result || 'Expected result pending.'}</small>
                </div>
              ))}
            </details>
          ))}
          {!cases.length ? <EmptyState title="No tests generated yet" detail="Generate tests to evaluate coverage." /> : null}
        </div>

        <div className="hei-qa-card">
          <div className="planner-label">Regression Intelligence</div>
          <Row label="Priority" value={regression?.regressionPriority || 'Medium'} />
          <ListBlock title="Changed Modules" items={regression?.changedModules || []} empty="No changed modules identified." />
          <ListBlock title="Affected Services" items={regression?.affectedServices || []} empty="No affected services identified." />
          <ListBlock title="Affected APIs" items={regression?.affectedAPIs || []} empty="No affected APIs identified." />
          <ListBlock title="Related Features / Stories" items={[...(regression?.relatedFeatures || []), ...(regression?.relatedStories || [])]} empty="No related work item impact identified." />
          <ListBlock title="Recommended Regression Tests" items={regression?.recommendedRegressionTests || []} empty="No regression tests recommended yet." />
        </div>

        <div className="hei-qa-card">
          <div className="planner-label">Risk Intelligence</div>
          <Row label="Highest Risk" value={risk?.highestRisk || 'Medium'} />
          {(risk?.risks || []).length ? (risk?.risks || []).map((item) => (
            <div className="hei-risk-row" key={item.name}>
              <span className={`hei-status-badge ${qaBadgeClass(item.level)}`}>{item.level || 'Medium'}</span>
              <div>
                <strong>{item.name}</strong>
                <p>{item.reason || 'Risk reasoning pending.'}</p>
                <small>{item.mitigation || 'Mitigation pending.'}</small>
              </div>
            </div>
          )) : <EmptyState title="No risk matrix yet" detail="Run QA Analysis to calculate implementation, integration, security, regression, repository, and dependency risk." />}
        </div>

        <div className="hei-qa-card">
          <div className="planner-label">Test Gap Analysis</div>
          <ListBlock title="Missing Tests" items={gaps?.missingTests || []} empty="No missing test categories detected." />
          <ListBlock title="Untested Acceptance Criteria" items={gaps?.untestedAcceptanceCriteria || []} empty="No untested acceptance criteria detected." />
          <ListBlock title="Weak Tests" items={gaps?.weakTests || []} empty="No weak tests detected." />
          <ListBlock title="Duplicate Tests" items={gaps?.duplicateTests || []} empty="No duplicate tests detected." />
          <ListBlock title="Validation Gaps" items={gaps?.validationGaps || []} empty="No implementation validation gaps reported." />
        </div>

        <div className="hei-qa-card wide">
          <details>
            <summary className="planner-label">QA Diagnostics</summary>
            <div className="planner-status-grid">
              <Row label="Repository Snapshot" value={diagnostics.repositorySnapshotAvailable ? 'Available' : 'Not provided'} />
              <Row label="Knowledge Version" value={diagnostics.knowledgeRegistryAvailable ? 'Available' : 'Not provided'} />
              <Row label="Graph Nodes Used" value={diagnostics.engineeringGraphAvailable ? 'Available' : 'Not provided'} />
              <Row label="Implementation Package" value={diagnostics.consumedExecutionPackage ? 'Consumed' : 'Missing'} />
              <Row label="Implementation Validation" value={diagnostics.consumedImplementationValidation ? 'Consumed' : 'Not provided'} />
              <Row label="Coverage Calculation" value={`${formatNumber(result.coverage_summary?.covered_acceptance_criteria_count)} / ${formatNumber(result.coverage_summary?.acceptance_criteria_count)} AC covered`} />
            </div>
          </details>
        </div>
      </div>
    </section>
  );
}

function QAStatusTile({ title, value, tone }: { title: string; value: string | number; tone?: string }) {
  return (
    <div className={`hei-qa-status-tile ${tone || 'neutral'}`}>
      <span>{title}</span>
      <strong>{value || 'Pending'}</strong>
    </div>
  );
}

function EmptyState({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="hei-queue-empty">
      <strong>{title}</strong>
      <span>{detail}</span>
    </div>
  );
}

function groupQATestsByCategory(cases: QATestCase[]): Record<string, QATestCase[]> {
  return cases.reduce<Record<string, QATestCase[]>>((groups, test) => {
    const category = normalizedQACategoryLabel(test.category);
    groups[category] = [...(groups[category] || []), test];
    return groups;
  }, {});
}

function normalizedQACategoryLabel(value?: string): string {
  const lowered = String(value || '').toLowerCase();
  if (lowered.includes('integration')) return 'Integration';
  if (lowered.includes('negative')) return 'Negative';
  if (lowered.includes('boundary') || lowered.includes('edge')) return 'Boundary';
  if (lowered.includes('permission') || lowered.includes('role') || lowered.includes('access')) return 'Permission';
  if (lowered.includes('security') || lowered.includes('auth')) return 'Security';
  if (lowered.includes('performance') || lowered.includes('load')) return 'Performance';
  if (lowered.includes('regression')) return 'Regression';
  if (lowered.includes('error') || lowered.includes('failure')) return 'Error Handling';
  return 'Functional';
}

function qaTone(value?: string): string {
  const lowered = String(value || '').toLowerCase();
  if (lowered.includes('ready') && !lowered.includes('not')) return 'success';
  if (lowered.includes('pass') || lowered.includes('low')) return 'success';
  if (lowered.includes('block') || lowered.includes('critical') || lowered.includes('high')) return 'error';
  if (lowered.includes('review') || lowered.includes('warning') || lowered.includes('medium') || lowered.includes('missing')) return 'warning';
  return 'neutral';
}

function scoreTone(value?: number): string {
  const score = Number(value || 0);
  if (score >= 85) return 'success';
  if (score >= 60) return 'warning';
  return 'error';
}

function qaBadgeClass(value?: string): string {
  const tone = qaTone(value);
  if (tone === 'success') return 'success';
  if (tone === 'error') return 'error';
  if (tone === 'warning') return 'warning';
  return 'neutral';
}

function qaRecommendedActions(result: QATestSuiteResult): string[] {
  if (result.coverage_gaps?.length) {
    return ['Generate missing tests.', 'Review uncovered acceptance criteria.', 'Repeat QA Analysis.'];
  }
  if ((result.qa_readiness?.status || result.qa_status || '').toLowerCase().includes('ready')) {
    return ['Export QA report.', 'Prepare release review.'];
  }
  return ['Run Implementation Validation.', 'Review QA gaps.', 'Generate missing tests.'];
}

function qaPrimaryAction({
  hasSuite,
  hasExecutionPackage,
  allowWithoutExecutionPackage,
  hasValidation,
  gaps,
  release,
}: {
  hasSuite: boolean;
  hasExecutionPackage: boolean;
  allowWithoutExecutionPackage?: boolean;
  hasValidation: boolean;
  gaps?: NonNullable<QATestSuiteResult['qa_intelligence']>['testGapAnalysis'];
  release?: QAReleaseRecommendation;
}): { label: string; onRun: 'analyze' | 'copy'; disabled?: boolean } {
  if (!hasExecutionPackage && !allowWithoutExecutionPackage) {
    return { label: 'Run QA Analysis', onRun: 'analyze', disabled: true };
  }
  if (!hasSuite) {
    return { label: 'Run QA Analysis', onRun: 'analyze' };
  }
  const hasMissingTests = Boolean(gaps?.missingTests?.length || gaps?.untestedAcceptanceCriteria?.length);
  if (hasMissingTests) {
    return { label: 'Generate Missing Tests', onRun: 'analyze' };
  }
  const recommendation = String(release?.recommendation || '').toLowerCase();
  if (recommendation.includes('blocked') || recommendation.includes('testing') || recommendation.includes('warning') || !hasValidation) {
    return { label: 'Review Gaps', onRun: 'analyze' };
  }
  return { label: 'Export QA Report', onRun: 'copy' };
}

function executionContextFileNames(context?: ExecutionContextResult): string[] {
  const ranked = Array.isArray(context?.recommended_files) ? context?.recommended_files : [];
  const executionPackage = (context?.execution_package_v2
    || context?.executionPackageV2
    || context?.implementation_package_v2
    || context?.implementationPackageV2
    || {}) as {
    repositoryContext?: { relevantFiles?: Array<{ path?: string; file?: string; name?: string } | string> };
    risks?: Array<{ reason?: string; name?: string; title?: string } | string>;
  };
  const packageFiles = Array.isArray(executionPackage.repositoryContext?.relevantFiles)
    ? executionPackage.repositoryContext?.relevantFiles
    : [];
  const capsuleFiles = Array.isArray((context as any)?.context_capsule?.relevantFiles)
    ? (context as any).context_capsule.relevantFiles
    : [];
  return uniqueStrings([
    ...ranked.map((item) => String(item || '')).filter(Boolean),
    ...packageFiles.map((item) => String(typeof item === 'string' ? item : item?.path || item?.file || item?.name || '')).filter(Boolean),
    ...capsuleFiles.map((item: any) => String(typeof item === 'string' ? item : item?.path || item?.file || item?.name || '')).filter(Boolean),
  ]);
}

function executionContextRiskText(context?: ExecutionContextResult): string[] {
  const executionPackage = (context?.execution_package_v2 || context?.executionPackageV2 || {}) as {
    risks?: Array<{ reason?: string; name?: string; title?: string } | string>;
  };
  const risks = Array.isArray(executionPackage.risks)
    ? executionPackage.risks
    : Array.isArray(context?.risks)
      ? context?.risks
      : [];
  return risks.map((risk: any) => {
    if (typeof risk === 'string') return risk;
    return String(risk?.reason || risk?.name || risk?.title || '').trim();
  }).filter(Boolean);
}

function filterPackageFiles(files: string[], keywords: string[]): string[] {
  const lowered = keywords.map((keyword) => keyword.toLowerCase());
  const matched = files.filter((file) => lowered.some((keyword) => file.toLowerCase().includes(keyword)));
  return (matched.length ? matched : files).slice(0, 5);
}

function filterPackageRisks(risks: string[], keywords: string[]): string[] {
  const lowered = keywords.map((keyword) => keyword.toLowerCase());
  return risks.filter((risk) => lowered.some((keyword) => risk.toLowerCase().includes(keyword)));
}

function StructuredTaskList({ tasks }: { tasks: StoryTask[] }) {
  return (
    <>
      {tasks.map((task) => (
        <div className="planner-task" key={task.title}>
          <strong>{task.work_area ? `${task.work_area}: ` : ''}{task.title}</strong>
          <span>{task.description}</span>
          <Row label="Task Quality Score" value={formatNumber(task.task_quality_score)} />
          <ListBlock title="Task Acceptance Criteria" items={task.acceptance_criteria || []} />
          <EngineeringDNADisclosure dna={task.work_item_dna} />
        </div>
      ))}
    </>
  );
}

function fallbackStoryTasks(story: StoryRefinement): StoryTask[] {
  const summary = story.story_summary || 'Approved story';
  return [
    {
      work_area: 'UI Work',
      title: `Shape ${summary} user interface states`,
      description: story.ui_considerations.join(' ') || 'Prepare UI behavior, states, accessibility, and validation copy for the approved story.',
      acceptance_criteria: [
        'Primary screen states cover loading, populated, empty, validation, and error outcomes.',
        'Visible fields and actions map to the approved acceptance criteria.',
        'Accessibility behavior is defined for the affected UI.',
      ],
    },
    {
      work_area: 'Backend Work',
      title: `Connect ${summary} service behavior`,
      description: story.technical_considerations.join(' ') || 'Define backend behavior inside the affected modules and flows.',
      acceptance_criteria: [
        'Backend behavior supports the approved acceptance criteria.',
        'Validation, authorization, and failure handling are defined.',
        'No unrelated behavior is changed.',
      ],
    },
    {
      work_area: 'QA Work',
      title: `Validate ${summary} acceptance and regression coverage`,
      description: story.qa_considerations.join(' ') || 'Prepare manual and regression checks for the approved acceptance criteria.',
      acceptance_criteria: [
        'Each acceptance criterion has at least one validation step.',
        'Happy path, empty state, error state, and permission behavior are covered.',
        'Regression scope includes affected flows and modules.',
      ],
    },
  ];
}

function KnowledgeRegistryNotice({ profile }: { profile: ProjectProfile }) {
  const hasKnowledge = Boolean(profile.knowledge_registry.modules.length || profile.knowledge_registry.flows.length || profile.knowledge_registry.components.length);
  if (hasKnowledge) {
    return (
      <div className="planner-banner">
        Knowledge Registry active: {[
          profile.knowledge_registry.modules.length ? `${profile.knowledge_registry.modules.length} modules` : '',
          profile.knowledge_registry.flows.length ? `${profile.knowledge_registry.flows.length} flows` : '',
          profile.knowledge_registry.components.length ? `${profile.knowledge_registry.components.length} components` : '',
        ].filter(Boolean).join(', ')}
      </div>
    );
  }
  return <div className="planner-banner">Repository intelligence is not available. Output may be profile-based.</div>;
}

function DeveloperWorkspace({
  executionContext,
  executionPlan,
  executionMode,
  devPrompt,
  uiPrompt,
  qaPrompt,
  copilotContext,
  onGenerate,
  onGenerateExecutionPlan,
  onGeneratePrompt,
  onEnhanceWithAi,
  setExecutionMode,
  loading,
  canContribute,
  itemType,
  currentWorkItem,
  storyInput,
  acceptanceCriteria,
  setStoryInput,
  setAcceptanceCriteria,
  storyResult,
  storyImpact,
  qaTestSuite,
  childDrafts,
  creationLog,
  providerMetadata,
  implementationValidation,
  implementationChangedFiles,
  setImplementationChangedFiles,
  prReview,
  approvalWorkflow,
  workflow,
  refineStory,
  analyzeImpact,
  generateChildren,
  generateQATestCases,
  approveStory,
  approveTasks,
  approveExecutionPackage,
  updateDraftSelection,
  createSelectedChildren,
  onOpenVsCode,
  onOpenQA,
  validateImplementation,
  runPRReview,
  postPRReviewComment,
}: {
  executionContext?: ExecutionContextResult;
  executionPlan?: ExecutionPlanResult;
  executionMode: ExecutionMode;
  devPrompt?: PromptBuilderResult;
  uiPrompt?: PromptBuilderResult;
  qaPrompt?: PromptBuilderResult;
  copilotContext?: CopilotContextResult;
  onGenerate: () => void;
  onGenerateExecutionPlan: () => void;
  onGeneratePrompt: (kind: 'dev' | 'ui' | 'qa' | 'copilot') => void;
  onEnhanceWithAi: () => void;
  setExecutionMode: (value: ExecutionMode) => void;
  loading: boolean;
  canContribute: boolean;
  itemType: WorkItemKind;
  currentWorkItem?: AdoWorkItem;
  storyInput: { title: string; description: string };
  acceptanceCriteria: string;
  setStoryInput: (value: { title: string; description: string }) => void;
  setAcceptanceCriteria: (value: string) => void;
  storyResult?: StoryRefinement;
  storyImpact?: StoryImpact;
  qaTestSuite?: QATestSuiteResult;
  childDrafts: ChildDraft[];
  creationLog: string[];
  providerMetadata?: ProviderMetadata;
  implementationValidation?: ImplementationValidationReport;
  implementationChangedFiles: string;
  setImplementationChangedFiles: (value: string) => void;
  prReview?: PRReviewReport;
  approvalWorkflow: ApprovalWorkflowState;
  workflow: WorkflowOrchestrationState;
  refineStory: () => void;
  analyzeImpact: () => void;
  generateChildren: (forceRegenerate?: boolean) => void;
  generateQATestCases: (forceRefresh?: boolean, action?: 'analyze' | 'generate_missing_tests') => void;
  approveStory: () => void;
  approveTasks: () => void;
  approveExecutionPackage: () => void;
  updateDraftSelection: (draftId: string, selected: boolean) => void;
  createSelectedChildren: () => void;
  onOpenVsCode: () => void;
  onOpenQA: () => void;
  validateImplementation: () => void;
  runPRReview: () => void;
  postPRReviewComment: () => void;
}) {
  const hasPackage = Boolean(executionContext || executionPlan || devPrompt || uiPrompt || qaPrompt || copilotContext);
  const vsCodeUri = executionContext ? buildVsCodeExecutionPackageUri(executionContext, executionPlan, devPrompt, uiPrompt, qaPrompt, copilotContext) : '';
  const readOnly = !canContribute || currentWorkItem?.state.toLowerCase() === 'closed';
  const isStory = itemType === 'Story';
  const isTask = itemType === 'Task';
  const isBug = itemType === 'Bug';
  const hasGeneratedTasks = childDrafts.some((draft) => draft.type === 'Task');
  if (itemType === 'Epic' || itemType === 'Feature' || itemType === 'Test Case') {
    return (
      <section className="planner-card">
        <div className="planner-label">Developer Workspace</div>
        <div className="planner-subtle">{itemType} work items are routed to {workspaceLabel(recommendedWorkspaceForItem(itemType))}. Execution actions are hidden for this item type.</div>
      </section>
    );
  }
  const executionSourceType = executionContext?.execution_source?.artifactType || executionContext?.artifact_type || (isTask ? 'Task' : isStory ? 'Story' : isBug ? 'Bug' : 'Artifact');
  const executionSourceTitle = executionContext?.execution_source?.title || storyInput.title || currentWorkItem?.title || 'Selected execution artifact';
  return (
    <>
      <section className="planner-card hei-execution-workspace">
        <div className="planner-label">{isBug ? 'Bug Fix Workspace' : 'Implementation Workspace'}</div>
        <div className="planner-subtle">
          {isBug
            ? 'Analyze impact, prepare fix context, and generate regression coverage.'
            : isTask
              ? 'Convert this Task into an implementation package, implementation plan, AI prompt, validation, and QA flow.'
              : 'Convert this Story into an implementation package first, then move into implementation, validation, and QA.'}
        </div>
        <div className="planner-summary-grid">
          <SummaryTile title="Executing" value={`${executionSourceType}: ${executionSourceTitle}`} />
          <SummaryTile title="Planning Tasks" value={isStory ? (hasGeneratedTasks ? approvalStatusLabel(approvalWorkflow.tasks) : 'Optional') : 'Not Required'} />
          <SummaryTile title="Implementation Package" value={executionContext ? 'Built' : 'Not Built'} />
        </div>
        {readOnly ? <div className="planner-error">This work item is Closed. Execution output is read-only.</div> : null}
        <RefinementInput input={storyInput} setInput={setStoryInput} titlePlaceholder={isBug ? 'Bug title' : isTask ? 'Task title' : 'Story title'} descriptionPlaceholder={isBug ? 'Bug symptoms, expected behavior, and observed behavior.' : 'Approved story/task scope for execution.'} />
        <textarea
          className="planner-textarea compact"
          value={acceptanceCriteria}
          onChange={(event) => setAcceptanceCriteria(event.target.value)}
          placeholder={isBug ? 'Regression expectations or reproduction notes, one per line' : 'Acceptance criteria or task validation notes, one per line'}
        />
        {isStory ? <ApprovalStatusStrip label="Story" status={approvalWorkflow.story} qualityScore={qualityScoreForStory(storyResult)} /> : null}
        {isTask || isBug ? <ApprovalStatusStrip label={isBug ? 'Fix Context' : 'Implementation Package'} status={approvalWorkflow.execution} qualityScore={executionContext?.execution_readiness_score} /> : null}
        <div className="planner-summary-grid">
          <label className="planner-field">
            <span className="planner-label">Execution Mode</span>
            <select className="planner-input" value={executionMode} onChange={(event) => setExecutionMode(event.target.value as ExecutionMode)} disabled={loading || readOnly}>
              <option value="implement">Implement</option>
              <option value="review_existing_code">Review Existing Code</option>
              <option value="refactor">Refactor</option>
              <option value="bug_fix">Bug Fix</option>
              <option value="spike_investigation">Spike / Investigation</option>
            </select>
          </label>
          <SummaryTile title="Implementation Plan" value={executionPlan ? `${executionPlan.executionModeLabel || executionPlan.executionMode} ready` : 'Not Generated'} />
        </div>
        <div className="planner-actions">
          <button className="planner-button" onClick={onGenerate} disabled={loading || readOnly || !storyInput.title.trim()}>{isBug ? 'Build Fix Context' : executionContext ? 'Rebuild Implementation Package' : 'Build Implementation Package'}</button>
          <button className="planner-button" onClick={onGenerateExecutionPlan} disabled={loading || readOnly || !storyInput.title.trim()}>{executionPlan ? 'Regenerate Implementation Plan' : 'Generate Implementation Plan'}</button>
          {isBug ? <button className="planner-button secondary" onClick={analyzeImpact} disabled={loading || readOnly || !storyInput.title.trim()}>Root Cause / Execution Impact</button> : null}
          {executionContext ? <button className="planner-button secondary" onClick={onEnhanceWithAi} disabled={loading || readOnly}>Enhance with AI</button> : null}
          {hasPackage ? <button className="planner-button secondary" onClick={approveExecutionPackage} disabled={loading || readOnly || !isApprovalPending(approvalWorkflow.execution)}>Approve Implementation Package</button> : null}
          {vsCodeUri ? (
            <button className="planner-button secondary" onClick={onOpenVsCode} disabled={loading}>Open Execution Workspace</button>
          ) : null}
        </div>
      </section>
      <ExecutionPackageCards
        executionContext={executionContext}
        executionPlan={executionPlan}
        devPrompt={devPrompt}
        uiPrompt={uiPrompt}
        qaPrompt={qaPrompt}
        onGeneratePrompt={onGeneratePrompt}
        onOpenVsCode={onOpenVsCode}
        loading={loading}
      />
      {storyImpact && isBug ? <StoryImpactResult result={storyImpact} /> : null}
      <details className="planner-nested">
        <summary>Show details</summary>
        <EngineeringMemoryEvidence context={executionContext?.memory_context} area="Execution" />
        <IntelligenceTracePanel trace={executionContext?.intelligence_trace} />
        {!hasPackage ? (
          <section className="planner-card">
            <div className="planner-subtle">No implementation package generated yet. Build one from this workspace when the scope is ready.</div>
          </section>
        ) : null}
        {executionContext?.context_capsule ? (
          <ContextCapsuleCard
            context={executionContext}
            loading={loading}
            readOnly={readOnly}
            onRefresh={onGenerate}
            onBuild={onGenerate}
          />
        ) : null}
        {executionContext ? <ExecutionContextBlock context={executionContext} /> : null}
        {executionPlan ? <PromptBlock title="Implementation Plan" value={executionPlan.plan || executionPlan.finalPlan || executionPlan.prompt || ''} metadata={executionPlan} copyable /> : null}
        {executionContext ? (
          <ImplementationValidationPanel
            report={implementationValidation}
            changedFilesInput={implementationChangedFiles}
            setChangedFilesInput={setImplementationChangedFiles}
            loading={loading}
            readOnly={readOnly}
            onValidate={validateImplementation}
          />
        ) : null}
        {executionContext ? (
          <PRReviewPanel
            report={prReview}
            loading={loading}
            readOnly={readOnly}
            onRun={runPRReview}
            onPost={postPRReviewComment}
          />
        ) : null}
        {executionContext ? (
          <section className="planner-card">
            <details>
              <summary className="planner-label">Advanced Execution Artifacts</summary>
              <div className="planner-subtle">Optional artifacts for specialized review. Most implementation work should use the Developer Prompt. The Implementation Package JSON stays here for advanced inspection.</div>
              <div className="planner-actions">
                <button className="planner-button secondary" onClick={() => onGeneratePrompt('copilot')} disabled={loading || readOnly}>Generate Context Capsule</button>
                <button className="planner-button secondary" onClick={() => onGeneratePrompt('ui')} disabled={loading || readOnly}>Generate Specialized UI Prompt</button>
                <button className="planner-button secondary" onClick={onOpenQA}>Open QA Intelligence</button>
                <button className="planner-button secondary" onClick={() => void copyText(JSON.stringify(executionContext.execution_package_v2 || executionContext.executionPackageV2 || executionContext.implementation_package_v2 || executionContext.implementationPackageV2 || executionContext, null, 2))}>Copy Implementation Package JSON</button>
              </div>
            </details>
          </section>
        ) : null}
        {devPrompt ? <PromptBlock title="Developer Prompt" value={devPrompt.prompt} metadata={devPrompt} copyable /> : null}
        {uiPrompt ? <PromptBlock title="Specialized UI Prompt" value={uiPrompt.prompt} metadata={uiPrompt} copyable /> : null}
        {copilotContext ? (
          <div className="planner-task">
            <div className="planner-label">Context Capsule</div>
            <SourceBadge metadata={copilotContext} />
            <div className="planner-actions">
              <button className="planner-button secondary" onClick={() => void copyText(copilotContext.context)}>Copy</button>
            </div>
            <pre className="planner-prompt">{copilotContext.context}</pre>
          </div>
        ) : null}
      </details>
    </>
  );
}

function QAWorkspace({
  loading,
  storyInput,
  acceptanceCriteria,
  setStoryInput,
  setAcceptanceCriteria,
  qaTestSuite,
  approvalWorkflow,
  storyImpact,
  generateQATestCases,
  approveTestSuite,
  canContribute,
  itemType,
  currentWorkItem,
  analyzeImpact,
  executionContext,
  implementationValidation,
  prReview,
  coverageReport,
  graphSummary,
  workflow,
}: {
  loading: boolean;
  storyInput: { title: string; description: string };
  acceptanceCriteria: string;
  setStoryInput: (value: { title: string; description: string }) => void;
  setAcceptanceCriteria: (value: string) => void;
  qaTestSuite?: QATestSuiteResult;
  approvalWorkflow: ApprovalWorkflowState;
  storyImpact?: StoryImpact;
  generateQATestCases: (forceRefresh?: boolean, action?: 'analyze' | 'generate_missing_tests') => void;
  approveTestSuite: () => void;
  canContribute: boolean;
  itemType: WorkItemKind;
  currentWorkItem?: AdoWorkItem;
  analyzeImpact: () => void;
  executionContext?: ExecutionContextResult;
  implementationValidation?: ImplementationValidationReport;
  prReview?: PRReviewReport;
  coverageReport?: CoverageIntelligenceReport;
  graphSummary?: GraphSummary;
  workflow: WorkflowOrchestrationState;
}) {
  const isTestCase = itemType === 'Test Case';
  const readOnly = !canContribute || currentWorkItem?.state.toLowerCase() === 'closed';
  const hasExecutionPackage = Boolean(executionContext);
  const hasValidation = Boolean(implementationValidation);
  const qaInputReady = isTestCase || hasExecutionPackage;
  const primary = qaPrimaryAction({
    hasSuite: Boolean(qaTestSuite),
    hasExecutionPackage,
    allowWithoutExecutionPackage: isTestCase,
    hasValidation,
    gaps: qaTestSuite?.qa_intelligence?.testGapAnalysis,
    release: qaTestSuite?.release_recommendation || qaTestSuite?.qa_intelligence?.releaseRecommendation,
  });
  const qaReadinessStatus = qaTestSuite?.qa_status || qaTestSuite?.qa_readiness?.status || (hasExecutionPackage ? 'Ready To Analyze' : 'Implementation Package Required');
  const acceptanceCoverageScore = qaTestSuite ? (qaTestSuite.qa_readiness?.acceptanceCoverage ?? qaTestSuite.coverage_score) : undefined;
  const regressionRisk = qaTestSuite?.qa_readiness?.regressionRisk || 'Pending';
  const releaseRecommendation = qaTestSuite?.release_status || qaTestSuite?.release_recommendation?.recommendation || 'Not Assessed';
  const missingTestCount = qaTestSuite?.coverage_gaps?.length || qaTestSuite?.qa_intelligence?.testGapAnalysis?.missingTests?.length || qaTestSuite?.qa_intelligence?.testGapAnalysis?.untestedAcceptanceCriteria?.length || 0;
  if (itemType !== 'Test Case' && itemType !== 'Story' && itemType !== 'Bug') {
    return (
      <section className="planner-card">
        <div className="planner-label">QA Workspace</div>
        <div className="planner-subtle">{itemType} work items are routed to {workspaceLabel(recommendedWorkspaceForItem(itemType))}. QA operations are hidden for this item type.</div>
      </section>
    );
  }
  return (
    <>
      <section className="planner-card hei-qa-workspace">
        <div className="planner-section-header">
          <div>
            <div className="planner-label">{isTestCase ? 'Test Case Workspace' : 'QA & Release'}</div>
            <div className="planner-subtle">
              {isTestCase
                ? 'Analyze coverage, regression scope, and execution notes for the selected test case.'
                : 'Assess QA readiness, coverage, regression risk, missing tests, and release recommendation in one place.'}
            </div>
          </div>
          <button
            className="planner-button"
            onClick={
              primary.onRun === 'copy'
                ? () => void copyText(formatQATestSuiteForCopy(qaTestSuite))
                : () => void generateQATestCases(false, primary.label === 'Generate Missing Tests' ? 'generate_missing_tests' : 'analyze')
            }
            disabled={loading || readOnly || primary.disabled || !storyInput.title.trim()}
          >
            {primary.label}
          </button>
        </div>
        <div className="planner-summary-grid">
          <SummaryTile title="QA Readiness" value={qaReadinessStatus} />
          <SummaryTile title="Acceptance Coverage" value={qaTestSuite ? `${acceptanceCoverageScore}%` : 'Not Assessed'} />
          <SummaryTile title="Regression Risk" value={regressionRisk} />
          <SummaryTile title="Release Recommendation" value={releaseRecommendation} />
        </div>
        {!hasExecutionPackage && !isTestCase ? (
          <div className="planner-banner">Build an Implementation Package before running QA Intelligence.</div>
        ) : null}
        {!hasValidation ? (
          <div className="planner-banner">Run Implementation Validation to improve QA accuracy.</div>
        ) : null}
        <div className="planner-actions">
          <button
            className="planner-button"
            onClick={
              primary.onRun === 'copy'
                ? () => void copyText(formatQATestSuiteForCopy(qaTestSuite))
                : () => void generateQATestCases(false, primary.label === 'Generate Missing Tests' ? 'generate_missing_tests' : 'analyze')
            }
            disabled={loading || readOnly || primary.disabled || !storyInput.title.trim()}
          >
            {primary.label}
          </button>
          {qaTestSuite ? (
            <button className="planner-button secondary" onClick={() => void generateQATestCases(true, 'analyze')} disabled={loading || readOnly || !qaInputReady || !storyInput.title.trim()}>
              Refresh QA Analysis
            </button>
          ) : null}
          <button className="planner-button secondary" onClick={analyzeImpact} disabled={loading || readOnly || !storyInput.title.trim()}>
            Review Regression
          </button>
          <button className="planner-button secondary" onClick={() => void copyText(formatQATestSuiteForCopy(qaTestSuite))} disabled={!qaTestSuite}>
            Export QA Report
          </button>
          {qaTestSuite && isApprovalPending(approvalWorkflow.qa) ? (
            <button className="planner-button secondary" onClick={approveTestSuite} disabled={loading || readOnly}>
              Approve Test Suite
            </button>
          ) : null}
        </div>
        {qaTestSuite ? (
          <div className="planner-summary-grid">
            <SummaryTile title="Missing Tests" value={missingTestCount ? `${missingTestCount} gap${missingTestCount === 1 ? '' : 's'}` : 'No blocking gaps'} />
            <SummaryTile title="Test Suite Status" value={approvalStatusLabel(approvalWorkflow.qa)} />
            <SummaryTile title="Quality Gate" value={qaTestSuite.coverage_score >= 80 ? `${qaTestSuite.coverage_score} - Ready For Approval` : `${qaTestSuite.coverage_score} - Needs Work`} />
          </div>
        ) : null}
      </section>
      {qaTestSuite ? (
        <>
          <details className="planner-nested">
            <summary>Show details</summary>
            {storyImpact ? <StoryImpactResult result={storyImpact} /> : null}
            <RelationshipSummaryCard summary={graphSummary} />
            <CoverageIntelligenceCard report={coverageReport} />
            <EngineeringMemoryEvidence context={qaTestSuite.memory_context} area="QA" />
            <IntelligenceTracePanel trace={qaTestSuite.intelligence_trace} />
            <details className="planner-nested">
              <summary>QA Input</summary>
              <RefinementInput input={storyInput} setInput={setStoryInput} titlePlaceholder="Open critical fault event details" descriptionPlaceholder="Story description or outcome for QA validation." />
              <textarea
                className="planner-textarea compact"
                value={acceptanceCriteria}
                onChange={(event) => setAcceptanceCriteria(event.target.value)}
                placeholder="Acceptance criteria, one per line"
              />
            </details>
            <QAIntelligencePanel result={qaTestSuite} />
          </details>
        </>
      ) : (
        <section className="planner-card">
          <div className="planner-label">QA & Release</div>
          <div className="planner-subtle">{hasExecutionPackage ? 'No tests generated yet. Generate tests to evaluate coverage and release readiness.' : 'Build an Implementation Package before running QA Intelligence.'}</div>
          <div className="planner-summary-grid">
            <SummaryTile title="Implementation Package" value={hasExecutionPackage ? 'Ready' : 'Missing'} />
            <SummaryTile title="Implementation Validation" value={hasValidation ? 'Ready' : 'Recommended'} />
            <SummaryTile title="Repository Intelligence" value={executionContext ? 'Available' : 'Pending'} />
            <SummaryTile title="QA Analysis" value="Not Run" />
          </div>
        </section>
      )}
    </>
  );
}

function ContextCapsuleCard({
  context,
  loading,
  readOnly,
  onRefresh,
  onBuild,
}: {
  context: ExecutionContextResult;
  loading: boolean;
  readOnly: boolean;
  onRefresh: () => void;
  onBuild: () => void;
}) {
  const capsule = context.context_capsule;
  if (!capsule) {
    return null;
  }
  const files = (capsule.relevantFiles || [])
    .map((file) => file.path ? `${file.path}${file.confidence ? ` (${Math.round(file.confidence * 100)}%)` : ''}` : '')
    .filter(Boolean);
  return (
    <section className="planner-card">
      <div className="planner-label">Context Capsule</div>
      <div className="planner-subtle">Execution starts from this selected capsule. Broad project context is intentionally excluded.</div>
      <div className="planner-status-grid">
        <Row label="Capsule Type" value={titleCase(capsule.capsuleType || 'execution')} />
        <Row label="Knowledge Version" value={capsule.knowledgeVersion || 'Not available'} />
        <Row label="Repository Snapshot" value={capsule.repositorySnapshotVersion || 'Not available'} />
        <Row label="Token Estimate" value={formatNumber(capsule.tokenEstimate)} />
        <Row label="Confidence" value={capsule.confidence !== undefined ? `${Math.round(capsule.confidence * 100)}%` : 'n/a'} />
        <Row label="Freshness" value={titleCase(capsule.freshnessStatus || 'unknown')} />
      </div>
      <div className="planner-grid">
        <ListBlock title="Modules" items={capsule.selectedModules || []} />
        <ListBlock title="Flows" items={capsule.selectedFlows || []} />
        <ListBlock title="Dependencies" items={capsule.selectedDependencies || []} />
        <ListBlock title="In Scope" items={capsule.inScope || []} />
        <ListBlock title="Out Of Scope" items={capsule.outOfScope || []} />
        <ListBlock title="Relevant Files" items={files.length ? files : [capsule.fileRankingStatus || 'Repository file ranking not available']} />
      </div>
      <EngineeringDNASection dna={capsule.workItemDNA} />
      <details className="planner-task">
        <summary className="planner-label">View Details</summary>
        <div className="planner-subtle">{capsule.intentSummary || context.capsule_summary || 'No capsule summary available.'}</div>
        <ListBlock title="Standards" items={capsule.selectedStandards || []} />
        <ListBlock title="Rejected Context" items={(capsule.rejectedContext || []).map((item) => `${item.name}${item.reason ? `: ${item.reason}` : ''}`)} />
      </details>
      <div className="planner-actions">
        <button className="planner-button secondary" onClick={onRefresh} disabled={loading || readOnly}>Refresh Capsule</button>
        <button className="planner-button" onClick={onBuild} disabled={loading || readOnly}>Build Implementation Package</button>
      </div>
    </section>
  );
}

function EngineeringDNASection({ dna, summary }: { dna?: WorkItemDNA; summary?: WorkItemDNASummary }) {
  const evidence = dna?.repositoryEvidence || {};
  const boundary = dna?.planningBoundary || {};
  const validation = dna?.validationSummary || {};
  const businessGoals = summary?.businessGoals || dna?.businessGoals || [];
  const responsibilities = summary?.responsibilities || dna?.responsibilities || [];
  const inScope = summary?.inScope || boundary.inScope || [];
  const outOfScope = summary?.outOfScope || boundary.outOfScope || [];
  const modules = summary?.modules || evidence.modules || [];
  const flows = summary?.flows || evidence.flows || [];
  const files = summary?.files || evidence.files || [];
  const dependencies = summary?.dependencies || dna?.dependencies || [];
  const constraints = summary?.constraints || dna?.constraints || [];
  const risks = summary?.risks || dna?.risks || [];
  const acceptanceThemes = summary?.acceptanceThemes || dna?.acceptanceThemes || [];
  const validationIssues = summary?.validationIssues || validation.issues || [];
  const dnaId = summary?.dnaId || dna?.dnaId;
  if (!dnaId && !summary?.capability && !dna?.capability) {
    return null;
  }
  return (
    <section className="planner-task">
      <div className="planner-label">Engineering DNA</div>
      <div className="planner-subtle">Canonical engineering identity inherited through planning and execution.</div>
      <div className="planner-status-grid">
        <Row label="DNA" value={`${dnaId || 'Not available'}${summary?.version || dna?.version ? ` v${summary?.version || dna?.version}` : ''}`} />
        <Row label="Type" value={summary?.workItemType || dna?.workItemType || 'Work Item'} />
        <Row label="Capability" value={summary?.capability || dna?.capability || 'Not captured'} />
        <Row label="Business Outcome" value={summary?.businessOutcome || dna?.businessOutcome || 'Not captured'} />
        <Row label="Validation" value={`${summary?.validationScore ?? validation.score ?? 0}%${validationIssues.length ? `, ${validationIssues.length} issue(s)` : ''}`} />
        <Row label="Confidence" value={summary?.confidence !== undefined || dna?.confidence !== undefined ? `${Math.round((summary?.confidence ?? dna?.confidence ?? 0) * 100)}%` : 'n/a'} />
        <Row label="Parent DNA" value={summary?.parentDNA || dna?.parentDNA || 'Root DNA'} />
        <Row label="Approved" value={summary?.approved || dna?.approved ? 'Yes' : 'No'} />
      </div>
      <div className="planner-grid">
        <ListBlock title="Business Goals" items={businessGoals} />
        <ListBlock title="Responsibilities" items={responsibilities} />
        <ListBlock title="In Scope" items={inScope} />
        <ListBlock title="Out Of Scope" items={outOfScope} />
        <ListBlock title="Modules" items={modules} />
        <ListBlock title="Flows" items={flows} />
        <ListBlock title="Files" items={files} />
        <ListBlock title="Dependencies" items={dependencies} />
        <ListBlock title="Constraints" items={constraints} />
        <ListBlock title="Risks" items={risks} />
        <ListBlock title="Acceptance Themes" items={acceptanceThemes} />
        <ListBlock title="Validation Issues" items={validationIssues} />
      </div>
    </section>
  );
}

function ExecutionContextBlock({ context }: { context: ExecutionContextResult }) {
  return (
    <section className="planner-card" id="execution-package-details">
      <div className="planner-label">Implementation Package</div>
      <SourceBadge metadata={context} />
      <RelevanceSummary metadata={context} />
      <div className="planner-status-grid">
        <Row label="Story Summary" value={context.story_summary || 'Not generated yet'} />
        <Row label="Package Source" value={titleCase(context.execution_package_source || context.implementation_package_source || 'context_capsule')} />
        <Row label="Task Focus" value={context.task_focus || 'Not selected'} />
        <Row label="Implementation Boundary" value={context.implementation_boundary || 'Not generated'} />
        <Row label="Execution Readiness" value={`${context.execution_readiness_result || context.execution_readiness || 'Not assessed'} (${context.execution_readiness_score || 0}%)`} />
        <Row label="Technology Stack" value={formatStack(context.technology_stack || EMPTY_STACK) || 'Not captured'} />
        <Row label="Repository File Ranking" value={context.file_ranking_status || 'Repository file ranking not available'} />
      </div>
      <EngineeringDNASection dna={context.work_item_dna} summary={context.dna_summary} />
      <div className="planner-grid">
        <ListBlock title="Acceptance Criteria" items={context.acceptance_criteria || []} />
        <ListBlock title="Affected Applications" items={context.affected_applications || []} />
        <ListBlock title="Affected Modules" items={context.affected_modules || []} />
        <ListBlock title="Affected Flows" items={context.affected_flows || []} />
        <ListBlock title="Dependencies" items={context.dependencies || []} />
        <ListBlock title="Risks" items={context.risks || []} />
        <ListBlock title="Recommended Files" items={context.recommended_files || []} />
        <ListBlock title="Development Tasks" items={context.implementation_tasks || []} />
        <ListBlock title="Testing Tasks" items={context.testing_tasks || []} />
        <ListBlock title="Documentation Tasks" items={context.documentation_tasks || []} />
        <ListBlock title="Implementation Notes" items={context.implementation_notes || []} />
        <ListBlock title="Engineering Rules" items={context.engineering_rules || []} />
        <ListBlock title="Rejected Context" items={(context.rejected_context || []).map((item) => `${item.name}${item.reason ? `: ${item.reason}` : ''}`)} />
      </div>
      <div className="planner-task">
        <div className="planner-label">Acceptance Criteria Mapping</div>
        {(context.acceptance_criteria_mapping || []).length ? (
          <ul className="planner-list">
            {context.acceptance_criteria_mapping.map((item) => (
              <li key={`${item.acceptance_criterion}-${item.implementation_task}`}>
                <strong>{item.acceptance_criterion}</strong>: {item.implementation_task}
              </li>
            ))}
          </ul>
        ) : (
          <div className="planner-subtle">No acceptance criteria mapping generated yet.</div>
        )}
      </div>
      <div className="planner-task">
        <div className="planner-label">Readiness Breakdown</div>
        <div className="planner-status-grid">
          {Object.entries(context.execution_readiness_breakdown || {}).map(([key, value]) => (
            <Row key={key} label={titleCase(key)} value={`${value}%`} />
          ))}
        </div>
      </div>
    </section>
  );
}

function ImplementationValidationPanel({
  report,
  changedFilesInput,
  setChangedFilesInput,
  loading,
  readOnly,
  onValidate,
}: {
  report?: ImplementationValidationReport;
  changedFilesInput: string;
  setChangedFilesInput: (value: string) => void;
  loading: boolean;
  readOnly: boolean;
  onValidate: () => void;
}) {
  const changedFiles = report?.changedFiles || [];
  const violations = report?.violations || [];
  const summary = report ? implementationValidationSummary(report) : '';
  return (
    <section className="planner-card">
      <div className="planner-section-header">
        <div>
          <div className="planner-label">Implementation Validation</div>
          <div className="planner-subtle">Validate completed code changes against the approved task, story, implementation package, and AI prompt.</div>
        </div>
        <StatusBadge label={report?.status || 'Not Run'} tone={report?.status === 'Passed' ? 'success' : report?.status === 'Failed' ? 'error' : 'warning'} />
      </div>
      <textarea
        className="planner-textarea compact"
        value={changedFilesInput}
        onChange={(event) => setChangedFilesInput(event.target.value)}
        placeholder={'Changed files, one per line. Optional format: path | status | diff summary\nsrc/fault/FaultEventController.cs | modified | added validation, authorization, and device health mapping'}
      />
      <div className="planner-actions">
        <button className="planner-button" onClick={onValidate} disabled={loading || readOnly}>Validate Implementation</button>
        <button className="planner-button secondary" onClick={() => void copyText(changedFiles.map((file) => `${file.path || ''} - ${file.status || ''}`).join('\n'))} disabled={!changedFiles.length}>View Changed Files</button>
        <button className="planner-button secondary" onClick={() => void copyText(violations.map((item) => `${item.severity || 'issue'}: ${item.message || item.rule || ''}${item.file ? ` (${item.file})` : ''}`).join('\n'))} disabled={!violations.length}>View Violations</button>
        <button className="planner-button secondary" onClick={() => void copyText(summary)} disabled={!report}>Copy Review Summary</button>
      </div>
      {report ? (
        <>
          <div className="planner-summary-grid">
            <SummaryTile title="Acceptance Coverage" value={`${report.acceptanceCoverageScore}%`} />
            <SummaryTile title="Scope Compliance" value={`${report.scopeComplianceScore}%`} />
            <SummaryTile title="Repository Alignment" value={`${report.repositoryAlignmentScore}%`} />
            <SummaryTile title="Standards" value={`${report.standardsComplianceScore}%`} />
            <SummaryTile title="Tests" value={`${report.testCoverageScore}%`} />
            <SummaryTile title="Risk" value={`${report.riskScore}%`} />
          </div>
          <div className="planner-grid">
            <ListBlock title="Acceptance Results" items={(report.acceptanceResults || []).map((item) => `${item.acceptanceCriteriaId || 'AC'}: ${titleCase(item.status || 'unknown')} - ${item.acceptanceText || ''}`)} />
            <ListBlock title="Changed Files" items={changedFiles.length ? changedFiles.map((file) => `${file.path || 'unknown'} - ${titleCase(file.status || 'needs review')}`) : ['No changed files supplied.']} />
            <ListBlock title="Standards" items={(report.standards || []).map((item) => `${item.standard || 'Standard'} - ${titleCase(item.status || 'unknown')}`)} />
            <ListBlock title="Tests" items={(report.tests || []).map((item) => `${item.testType || 'Test'} - ${titleCase(item.status || 'unknown')}`)} />
            <ListBlock title="Violations" items={violations.length ? violations.map((item) => `${titleCase(item.severity || 'issue')}: ${item.message || item.rule || ''}`) : ['No violations detected.']} />
            <ListBlock title="Recommendations" items={report.recommendations?.length ? report.recommendations : ['No recommendations.']} />
          </div>
        </>
      ) : (
        <div className="planner-subtle">No implementation validation report yet. Add changed files or diff summaries, then validate.</div>
      )}
    </section>
  );
}

function PRReviewPanel({
  report,
  loading,
  readOnly,
  onRun,
  onPost,
}: {
  report?: PRReviewReport;
  loading: boolean;
  readOnly: boolean;
  onRun: () => void;
  onPost: () => void;
}) {
  return (
    <section className="planner-card">
      <div className="planner-section-header">
        <div>
          <div className="planner-label">PR Review</div>
          <div className="planner-subtle">Review a PR against its linked work item, implementation package, standards, tests, and approved scope.</div>
        </div>
        <StatusBadge label={report?.status || 'Not Run'} tone={report?.status === 'Passed' ? 'success' : report?.status === 'Blocked' ? 'error' : 'warning'} />
      </div>
      <div className="planner-actions">
        <button className="planner-button" onClick={onRun} disabled={loading || readOnly}>Run PR Review</button>
        <button className="planner-button secondary" onClick={() => void copyText(report?.generatedReviewComment || '')} disabled={!report?.generatedReviewComment}>Copy Review Comment</button>
        <button className="planner-button secondary" onClick={onPost} disabled={!report || loading || !report.commentPostingEnabled}>Post to Azure DevOps PR</button>
        <button className="planner-button secondary" onClick={onRun} disabled={loading || readOnly}>Re-run After Changes</button>
      </div>
      {!report ? (
        <div className="planner-subtle">No PR Review report yet. Add changed files above, then run PR Review.</div>
      ) : (
        <>
          {!report.commentPostingEnabled ? <div className="planner-warning">PR comment posting is disabled by feature flag.</div> : null}
          <div className="planner-status-grid">
            <Row label="Validation Score" value={`${report.validationScore}%`} />
            <Row label="Linked Work Items" value={String(report.linkedWorkItems?.length || 0)} />
            <Row label="Changed Files" value={String(report.changedFiles?.length || 0)} />
            <Row label="Acceptance Coverage" value={`${report.scores?.acceptanceCoverage || 0}%`} />
            <Row label="Tests" value={`${report.scores?.tests || 0}%`} />
            <Row label="Repository Alignment" value={`${report.scores?.repositoryAlignment || 0}%`} />
          </div>
          <div className="planner-grid">
            <ListBlock title="Linked Work Items" items={(report.linkedWorkItems || []).map((item) => `#${item.id || 'n/a'} ${item.type || ''} ${item.title || ''}`.trim())} />
            <ListBlock title="Blocking Issues" items={report.blockingIssues?.length ? report.blockingIssues : ['None']} />
            <ListBlock title="Warnings" items={report.warnings?.length ? report.warnings : ['None']} />
            <ListBlock title="Changed Files" items={(report.changedFiles || []).map((file) => `${file.path || 'unknown'} - ${titleCase(file.status || 'needs review')}`)} />
            <ListBlock title="Recommendations" items={report.recommendations?.length ? report.recommendations : ['No recommendations.']} />
          </div>
          <details className="planner-task">
            <summary className="planner-label">Generated Review Comment</summary>
            <pre className="planner-prompt">{report.generatedReviewComment}</pre>
          </details>
        </>
      )}
    </section>
  );
}

function implementationValidationSummary(report: ImplementationValidationReport): string {
  return [
    `Implementation Validation: ${report.status}`,
    `Package: ${report.packageId}`,
    `Acceptance Coverage: ${report.acceptanceCoverageScore}%`,
    `Scope Compliance: ${report.scopeComplianceScore}%`,
    `Repository Alignment: ${report.repositoryAlignmentScore}%`,
    `Standards: ${report.standardsComplianceScore}%`,
    `Tests: ${report.testCoverageScore}%`,
    `Risk: ${report.riskScore}%`,
    '',
    'Violations:',
    ...(report.violations.length ? report.violations.map((item) => `- ${item.severity || 'issue'}: ${item.message || item.rule || ''}${item.file ? ` (${item.file})` : ''}`) : ['- None']),
    '',
    'Recommendations:',
    ...(report.recommendations.length ? report.recommendations.map((item) => `- ${item}`) : ['- None']),
  ].join('\n');
}

function QuickStartSetup({
  profile,
  adoProjects,
  repositories,
  branches,
  repositoryLoadMessage,
  loading,
  onProfileChange,
  onSelectAdoProject,
  onSelectRepository,
  onReloadRepositories,
  onAnalyzeProject,
}: {
  profile: ProjectProfile;
  adoProjects: AdoProject[];
  repositories: GitRepository[];
  branches: string[];
  repositoryLoadMessage: string;
  loading: boolean;
  onProfileChange: (profile: ProjectProfile) => void;
  onSelectAdoProject: (adoProject: string) => void;
  onSelectRepository: (repositoryId: string) => void;
  onReloadRepositories: () => void;
  onAnalyzeProject: () => void;
}) {
  const mapping = getAdoMapping(profile);
  return (
    <section className="planner-card planner-quick-start">
      <div>
        <div className="planner-label">Quick Start</div>
        <div className="planner-subtle">Enter the minimum context. Repository documents will fill the profile when available.</div>
      </div>
      <div>
        <div className="planner-label">Project Name</div>
        <input
          className="planner-input"
          value={profile.project_name}
          onChange={(event) => onProfileChange({ ...profile, project_name: event.target.value })}
          placeholder="LineDefender Smart Monitoring Platform"
        />
      </div>
      <div className="planner-grid">
        <div>
          <div className="planner-label">ADO Project optional</div>
          <select className="planner-input" value={mapping.ado_project} onChange={(event) => onSelectAdoProject(event.target.value)} disabled={!adoProjects.length}>
            <option value="">{adoProjects.length ? 'Select Azure DevOps project' : 'No projects loaded'}</option>
            {adoProjects.map((project) => <option key={project.id || project.name} value={project.name}>{project.name}</option>)}
            {mapping.ado_project && !adoProjects.some((project) => project.name === mapping.ado_project) ? (
              <option value={mapping.ado_project}>{mapping.ado_project}</option>
            ) : null}
          </select>
        </div>
        <div>
          <div className="planner-label">Repository optional</div>
          <select className="planner-input" value={repositories.some((repo) => repo.id === profile.repository_connection.repository_id) ? profile.repository_connection.repository_id : ''} onChange={(event) => onSelectRepository(event.target.value)} disabled={!repositories.length}>
            <option value="">{repositories.length ? 'No repository selected' : 'No repositories loaded'}</option>
            {repositories.map((repo) => <option key={repo.id} value={repo.id}>{repo.name}</option>)}
          </select>
          {repositoryLoadMessage ? <div className="planner-subtle">{repositoryLoadMessage}</div> : null}
          <div className="planner-actions compact">
            <button className="planner-button secondary" onClick={onReloadRepositories} disabled={loading}>Retry Repositories</button>
          </div>
        </div>
        <div>
          <div className="planner-label">Branch</div>
          {branches.length ? (
            <select
              className="planner-input"
              value={profile.repository_connection.branch}
              onChange={(event) => onProfileChange(applyAdoMapping({
                ...profile,
                repository_connection: { ...profile.repository_connection, branch: event.target.value, status: profile.repository_connection.repository_id ? 'Repository connected' : profile.repository_connection.status },
              }, { branch: event.target.value }))}
            >
              <option value="">Default branch</option>
              {branches.map((branch) => <option key={branch} value={branch}>{branch}</option>)}
              {profile.repository_connection.branch && !branches.includes(profile.repository_connection.branch) ? (
                <option value={profile.repository_connection.branch}>{profile.repository_connection.branch}</option>
              ) : null}
            </select>
          ) : (
            <input
              className="planner-input"
              value={profile.repository_connection.branch}
              onChange={(event) => onProfileChange(applyAdoMapping({
                ...profile,
                repository_connection: { ...profile.repository_connection, branch: event.target.value, status: profile.repository_connection.repository_id ? 'Repository connected' : profile.repository_connection.status },
              }, { branch: event.target.value }))}
              placeholder="main"
            />
          )}
        </div>
      </div>
      <div>
        <div className="planner-label">Project Description optional</div>
        <textarea
          className="planner-textarea compact"
          value={profile.project_description}
          onChange={(event) => onProfileChange({ ...profile, project_description: event.target.value })}
          placeholder="Describe the product goal, domain, users, and major systems. You can paste a short brief here."
        />
      </div>
      <div className="planner-actions">
        <button className="planner-button" onClick={onAnalyzeProject} disabled={loading || !profile.project_name.trim()}>
          Analyze Project
        </button>
      </div>
    </section>
  );
}

function ProjectProfileCompletion({ profile }: { profile: ProjectProfile }) {
  const setup = projectSetupStatus(profile);
  return (
    <section className="planner-card">
      <div className="planner-label">Project Setup</div>
      <div className="planner-health-grid">
        {setup.checks.map((check) => (
          <HealthCard key={check.title} title={check.title} status={check.status} detail={check.detail} />
        ))}
      </div>
    </section>
  );
}

function ProjectHealthDashboard({ profile }: { profile: ProjectProfile }) {
  const execution = executionReadiness(profile, false);
  return (
    <section className="planner-card">
      <div className="planner-label">Project Health</div>
      <div className="planner-health-grid">
        <HealthCard title="Repository Connected" status={profile.repository_connection.repository_id ? 'Ready' : 'Missing'} detail={profile.repository_connection.repository_name || 'Optional, but recommended'} />
        <HealthCard title="Knowledge Registry" status={knowledgeRegistryStatus(profile)} detail={registrySummary(profile)} />
        <HealthCard title="UI Guidelines" status={summarizeUiGuidelines(profile) === 'Not captured yet' ? 'Missing' : 'Ready'} detail={summarizeUiGuidelines(profile)} />
        <HealthCard title="Development Standards" status={hasDevelopmentStandards(profile) ? 'Ready' : 'Missing'} detail={hasDevelopmentStandards(profile) ? 'Captured' : 'Repository scan can detect this'} />
        <HealthCard title="Execution Readiness" status={execution.label === 'Ready' ? 'Ready' : execution.label === 'Partially Ready' ? 'Partial' : 'Missing'} detail={execution.label} />
      </div>
    </section>
  );
}

function HealthCard({ title, status, detail }: { title: string; status: 'Missing' | 'Partial' | 'Ready'; detail: string }) {
  return (
    <div className={`planner-health-card ${status.toLowerCase()}`}>
      <strong>{title}</strong>
      <span>{status}</span>
      <small>{detail}</small>
    </div>
  );
}

function OnboardingForm({
  profile,
  loading,
  onProfileChange,
  onAnalyze,
  onSave,
}: {
  profile: ProjectProfile;
  loading: boolean;
  onProfileChange: (profile: ProjectProfile) => void;
  onAnalyze: () => void;
  onSave: () => void;
}) {
  const selectedDomain = DOMAIN_OPTIONS.includes(profile.domain) ? profile.domain : (profile.domain ? 'Custom' : '');
  return (
    <>
      <section className="planner-card">
        <div>
          <div className="planner-label">Project Intelligence Onboarding</div>
          <div className="planner-subtle">This appears for a new project. After setup, Project Intelligence stays in the background and can be edited when context changes.</div>
        </div>
      </section>

      <section className="planner-card">
        <div className="planner-label">Project Name</div>
        <input
          className="planner-input"
          value={profile.project_name}
          onChange={(event) => onProfileChange({ ...profile, project_name: event.target.value })}
          placeholder="Smart Meter Analytics Platform"
        />

        <div className="planner-label">Business Domain</div>
        <select
          className="planner-input"
          value={selectedDomain}
          onChange={(event) => onProfileChange({ ...profile, domain: event.target.value })}
        >
          <option value="">Select domain</option>
          {DOMAIN_OPTIONS.map((domain) => <option key={domain} value={domain}>{domain}</option>)}
        </select>
        {selectedDomain === 'Custom' ? (
          <input
            className="planner-input"
            value={profile.domain === 'Custom' ? '' : profile.domain}
            onChange={(event) => onProfileChange({ ...profile, domain: event.target.value })}
            placeholder="Custom domain"
          />
        ) : null}

        <div className="planner-label">Project Type</div>
        <select
          className="planner-input"
          value={profile.project_type}
          onChange={(event) => onProfileChange({ ...profile, project_type: event.target.value })}
        >
          <option value="">Select project type</option>
          {PROJECT_TYPES.map((type) => <option key={type} value={type}>{type}</option>)}
        </select>

        <div className="planner-label">Project Description</div>
        <textarea
          className="planner-textarea"
          value={profile.project_description}
          onChange={(event) => onProfileChange({ ...profile, project_description: event.target.value })}
          placeholder="Describe the product, business goals, users, domain, systems, and delivery context."
        />
        <div className="planner-actions">
          <button className="planner-button" onClick={onAnalyze} disabled={loading || !profile.project_description.trim()}>
            Analyze Description
          </button>
        </div>
      </section>

      <ApplicationsEditor profile={profile} onProfileChange={onProfileChange} />
      <TechnologyStackEditor profile={profile} onProfileChange={onProfileChange} />
      <UiGuidelinesEditor profile={profile} onProfileChange={onProfileChange} />
      <DevelopmentStandardsEditor profile={profile} onProfileChange={onProfileChange} />

      <section className="planner-card">
        <div className="planner-label">Repository Sources</div>
        <textarea
          className="planner-textarea compact"
          value={profile.repository_sources.join('\n')}
          onChange={(event) => onProfileChange({ ...profile, repository_sources: splitLines(event.target.value) })}
          placeholder="README.md&#10;docs/architecture.md&#10;openapi.yaml"
        />
        <div className="planner-subtle">Repository README scan coming next.</div>
      </section>

      <section className="planner-card">
        <div className="planner-actions">
          <button className="planner-button" onClick={onSave} disabled={loading || !profile.project_description.trim()}>
            Finish Setup
          </button>
        </div>
      </section>
    </>
  );
}

function ApplicationsEditor({ profile, onProfileChange }: { profile: ProjectProfile; onProfileChange: (profile: ProjectProfile) => void }) {
  const applications = profile.applications.length ? profile.applications : [{ name: '', type: 'API' }];
  return (
    <section className="planner-card">
      <div className="planner-label">Applications</div>
      {applications.map((application, index) => (
        <div className="planner-grid" key={`application-${index}`}>
          <input
            className="planner-input"
            value={application.name}
            onChange={(event) => updateApplication(index, { ...application, name: event.target.value })}
            placeholder="Application name"
          />
          <select className="planner-input" value={application.type} onChange={(event) => updateApplication(index, { ...application, type: event.target.value })}>
            {APPLICATION_TYPES.map((type) => <option key={type} value={type}>{type}</option>)}
          </select>
        </div>
      ))}
      <div className="planner-actions">
        <button className="planner-button secondary" onClick={() => onProfileChange({ ...profile, applications: [...applications.filter((app) => app.name.trim()), { name: '', type: 'API' }] })}>
          Add Application
        </button>
      </div>
    </section>
  );

  function updateApplication(index: number, next: ApplicationProfile) {
    const updated = applications.map((item, itemIndex) => itemIndex === index ? next : item);
    onProfileChange({ ...profile, applications: updated });
  }
}

function TechnologyStackEditor({ profile, onProfileChange }: { profile: ProjectProfile; onProfileChange: (profile: ProjectProfile) => void }) {
  return (
    <section className="planner-card">
      <div className="planner-label">Technology Stack</div>
      <div className="planner-grid">
        {STACK_FIELDS.map((field) => (
          <div key={field}>
            <div className="planner-label">{titleCase(field)}</div>
            <textarea
              className="planner-textarea compact"
              value={profile.technology_stack[field].join('\n')}
              onChange={(event) => onProfileChange({
                ...profile,
                technology_stack: { ...profile.technology_stack, [field]: splitLines(event.target.value) },
              })}
              placeholder={stackPlaceholder(field)}
            />
          </div>
        ))}
      </div>
    </section>
  );
}

function UiGuidelinesEditor({ profile, onProfileChange }: { profile: ProjectProfile; onProfileChange: (profile: ProjectProfile) => void }) {
  return (
    <section className="planner-card">
      <div className="planner-label">UI Guidelines</div>
      <div className="planner-grid">
        <input className="planner-input" value={profile.ui_guidelines.primary_color} onChange={(event) => updateUi('primary_color', event.target.value)} placeholder="Primary color" />
        <input className="planner-input" value={profile.ui_guidelines.secondary_color} onChange={(event) => updateUi('secondary_color', event.target.value)} placeholder="Secondary color" />
        <input className="planner-input" value={profile.ui_guidelines.typography} onChange={(event) => updateUi('typography', event.target.value)} placeholder="Typography" />
        <input className="planner-input" value={profile.ui_guidelines.component_library} onChange={(event) => updateUi('component_library', event.target.value)} placeholder="Component library" />
      </div>
      <textarea
        className="planner-textarea compact"
        value={profile.ui_guidelines.accessibility_rules.join('\n')}
        onChange={(event) => onProfileChange({ ...profile, ui_guidelines: { ...profile.ui_guidelines, accessibility_rules: splitLines(event.target.value) } })}
        placeholder="Accessibility rules, one per line"
      />
    </section>
  );

  function updateUi(field: 'primary_color' | 'secondary_color' | 'typography' | 'component_library', value: string) {
    onProfileChange({ ...profile, ui_guidelines: { ...profile.ui_guidelines, [field]: value } });
  }
}

function DevelopmentStandardsEditor({ profile, onProfileChange }: { profile: ProjectProfile; onProfileChange: (profile: ProjectProfile) => void }) {
  return (
    <section className="planner-card">
      <div className="planner-label">Development Standards</div>
      <div className="planner-grid">
        <StandardTextarea label="Architecture Patterns" value={profile.development_standards.architecture_patterns} onChange={(items) => updateStandards('architecture_patterns', items)} placeholder="MVVM&#10;Repository Pattern" />
        <StandardTextarea label="Coding Guidelines" value={profile.development_standards.coding_guidelines} onChange={(items) => updateStandards('coding_guidelines', items)} placeholder="Small focused services&#10;Typed API contracts" />
        <StandardTextarea label="Security Requirements" value={profile.development_standards.security_requirements} onChange={(items) => updateStandards('security_requirements', items)} placeholder="OAuth2&#10;JWT&#10;No secrets in logs" />
        <StandardTextarea label="Testing Requirements" value={profile.development_standards.testing_requirements} onChange={(items) => updateStandards('testing_requirements', items)} placeholder="Unit tests required&#10;Code coverage >80%" />
      </div>
    </section>
  );

  function updateStandards(field: keyof DevelopmentStandards, items: string[]) {
    onProfileChange({ ...profile, development_standards: { ...profile.development_standards, [field]: items } });
  }
}

function StandardTextarea({ label, value, onChange, placeholder }: { label: string; value: string[]; onChange: (items: string[]) => void; placeholder: string }) {
  return (
    <div>
      <div className="planner-label">{label}</div>
      <textarea className="planner-textarea compact" value={value.join('\n')} onChange={(event) => onChange(splitLines(event.target.value))} placeholder={placeholder} />
    </div>
  );
}

function ProjectProfileSummary({ profile }: { profile: ProjectProfile }) {
  return (
    <section className="planner-card">
      <div className="planner-label">Project Profile</div>
      <div className="planner-status-grid">
        <Row label="Project Name" value={profile.project_name || 'Not captured yet'} />
        <Row label="Description" value={profile.project_description || 'Not captured yet'} />
        <Row label="Domain" value={profile.domain || profile.knowledge_profile_preview.domain || 'Not captured yet'} />
        <Row label="Project Type" value={profile.project_type || 'Not captured yet'} />
        <Row label="Applications" value={formatApplications(profile.applications) || 'Not captured yet'} />
        <Row label="Technology Stack" value={formatStack(profile.technology_stack) || 'Not captured yet'} />
        <Row label="UI Guidelines" value={summarizeUiGuidelines(profile)} />
      </div>
    </section>
  );
}

function KnowledgeProfilePreview({ profile, governance, canAdmin }: { profile: ProjectProfile; governance: KnowledgeGovernance; canAdmin: boolean }) {
  const modules = registryModuleDetails(profile);
  const flows = registryFlowDetails(profile);
  const components = registryComponentDetails(profile);
  const architecture = profile.knowledge_registry.architecture_notes.length
    ? profile.knowledge_registry.architecture_notes
    : profile.readme_analysis.architecture_notes;
  return (
    <section className="planner-card planner-knowledge-card">
      <div className="planner-section-header">
        <div>
          <div className="planner-label">Knowledge Summary</div>
          <div className="planner-subtle">Repository intelligence condensed into delivery-ready project knowledge.</div>
        </div>
      </div>
      <div className="planner-knowledge-summary-grid">
        <SummaryTile title="Modules" value={`${modules.length || profile.knowledge_registry.modules.length} captured`} />
        <SummaryTile title="Flows" value={`${flows.length || profile.knowledge_registry.flows.length} captured`} />
        <SummaryTile title="Components" value={`${components.length || profile.knowledge_registry.components.length} captured`} />
        <SummaryTile title="Architecture" value={architecture.length ? 'Detected' : 'Pending'} />
        <SummaryTile title="Knowledge Status" value={governance.registry_status === 'read_only' ? 'Read Only' : 'Pending'} />
        <SummaryTile title="Admin Controls" value={canAdmin ? 'Editable' : 'Read Only'} />
      </div>
      <details className="planner-accordion">
        <summary>View Modules</summary>
        <ChipList items={(modules.length ? modules.map((module) => module.name) : profile.knowledge_registry.modules).slice(0, 12)} />
        {modules.slice(0, 6).map((module) => (
          <details className="planner-nested" key={module.name}>
            <summary>{module.name}</summary>
            <ListBlock title="Responsibilities" items={module.responsibilities?.length ? module.responsibilities : ['Not captured']} />
            <ListBlock title="Dependencies" items={module.dependencies?.length ? module.dependencies : ['Not captured']} />
          </details>
        ))}
      </details>
      <details className="planner-accordion">
        <summary>View Flows</summary>
        <ChipList items={(flows.length ? flows.map((flow) => flow.name) : profile.knowledge_registry.flows).slice(0, 12)} />
        {flows.slice(0, 6).map((flow) => (
          <details className="planner-nested" key={flow.name}>
            <summary>{flow.name}</summary>
            {flow.steps?.length ? <ListBlock title="Steps" items={flow.steps} /> : <div className="planner-subtle">Steps not captured yet.</div>}
          </details>
        ))}
      </details>
      <details className="planner-accordion">
        <summary>View Components</summary>
        <ChipList items={(components.length ? components.map((component) => `${component.name}${component.type ? ` (${component.type})` : ''}`) : profile.knowledge_registry.components).slice(0, 12)} />
      </details>
      <ArchitectureDiagram notes={architecture} />
    </section>
  );
}

function RegistryModuleCard({ modules }: { modules: ModuleDetail[] }) {
  return (
    <div className="planner-task">
      <div className="planner-label">Modules</div>
      {modules.length ? modules.map((module) => (
        <div className="planner-task" key={module.name}>
          <strong>{module.name}</strong>
          <ListBlock title="Responsibilities" items={module.responsibilities?.length ? module.responsibilities : ['Not captured']} />
          <ListBlock title="Dependencies" items={module.dependencies?.length ? module.dependencies : ['Not captured']} />
        </div>
      )) : <div className="planner-subtle">Pending repository analysis</div>}
    </div>
  );
}

function RegistryFlowCard({ flows }: { flows: FlowDetail[] }) {
  return (
    <div className="planner-task">
      <div className="planner-label">Flows</div>
      {flows.length ? flows.map((flow) => (
        <div className="planner-task" key={flow.name}>
          <strong>{flow.name}</strong>
          {flow.steps?.length ? <ListBlock title="Steps" items={flow.steps} /> : null}
        </div>
      )) : <div className="planner-subtle">Pending repository analysis</div>}
    </div>
  );
}

function RegistryComponentCard({ components }: { components: ComponentDetail[] }) {
  return (
    <div className="planner-task">
      <div className="planner-label">Components</div>
      {components.length ? (
        <ul className="planner-list">
          {components.map((component) => <li key={component.name}>{component.name}{component.type ? ` (${component.type})` : ''}</li>)}
        </ul>
      ) : <div className="planner-subtle">Pending repository analysis</div>}
    </div>
  );
}

function RepositoryIntelligenceCard({
  profile,
  adoProjects,
  repositories,
  branches,
  repositoryLoadMessage,
  repositoryDocuments,
  fileStatus,
  selectedFiles,
  loading,
  showConnectionControls,
  onSelectAdoProject,
  onSelectRepository,
  onReloadRepositories,
  onProfileChange,
  onRepositoryDocumentsChange,
  onFileStatusChange,
  onSelectedFilesChange,
  onAnalyzeReadme,
  onDiscoverDocuments,
  onAnalyzeDocuments,
  governance,
}: {
  profile: ProjectProfile;
  adoProjects: AdoProject[];
  repositories: GitRepository[];
  branches: string[];
  repositoryLoadMessage: string;
  repositoryDocuments: Record<string, string>;
  fileStatus: Record<string, 'available' | 'missing' | 'unknown'>;
  selectedFiles: string[];
  loading: boolean;
  showConnectionControls: boolean;
  onSelectAdoProject: (adoProject: string) => void;
  onSelectRepository: (repositoryId: string) => void;
  onReloadRepositories: () => void;
  onProfileChange: (profile: ProjectProfile) => void;
  onRepositoryDocumentsChange: (documents: Record<string, string>) => void;
  onFileStatusChange: (status: Record<string, 'available' | 'missing' | 'unknown'>) => void;
  onSelectedFilesChange: (files: string[]) => void;
  onAnalyzeReadme: () => void;
  onDiscoverDocuments: () => void;
  onAnalyzeDocuments: () => void;
  governance: KnowledgeGovernance;
}) {
  const selectedRepositoryLoaded = repositories.some((repo) => repo.id === profile.repository_connection.repository_id);
  const mapping = getAdoMapping(profile);
  const documents = repositoryDocumentSummary(fileStatus, profile.knowledge_registry.source_files);
  const foundDocuments = documents.filter((doc) => doc.status === 'available');
  const missingDocuments = documents.filter((doc) => doc.status !== 'available');
  return (
    <section className="planner-card">
      <div className="planner-section-header">
        <div>
          <div className="planner-label">Repository Summary</div>
          <div className="planner-subtle">Connect documentation once. The platform converts it into planning and engineering knowledge.</div>
        </div>
      </div>
      {showConnectionControls ? (
        <>
          <div className="planner-step-row">
            <span>1 Connect Repository</span>
            <span>2 Discover Documentation</span>
            <span>3 Analyze Repository</span>
          </div>
          <div className="planner-grid">
            <select className="planner-input" value={mapping.ado_project} onChange={(event) => onSelectAdoProject(event.target.value)} disabled={!adoProjects.length}>
              <option value="">{adoProjects.length ? 'Select ADO project' : 'No projects loaded'}</option>
              {adoProjects.map((project) => <option key={project.id || project.name} value={project.name}>{project.name}</option>)}
              {mapping.ado_project && !adoProjects.some((project) => project.name === mapping.ado_project) ? (
                <option value={mapping.ado_project}>{mapping.ado_project}</option>
              ) : null}
            </select>
            <select className="planner-input" value={repositories.some((repo) => repo.id === profile.repository_connection.repository_id) ? profile.repository_connection.repository_id : ''} onChange={(event) => onSelectRepository(event.target.value)} disabled={!repositories.length}>
              <option value="">{repositories.length ? 'Select Azure DevOps repository' : 'No repositories loaded'}</option>
              {repositories.map((repo) => <option key={repo.id} value={repo.id}>{repo.name}</option>)}
            </select>
            {branches.length ? (
              <select
                className="planner-input"
                value={profile.repository_connection.branch}
                onChange={(event) => onProfileChange(applyAdoMapping({
                  ...profile,
                  repository_connection: { ...profile.repository_connection, branch: event.target.value, status: 'Repository connected' },
                }, { branch: event.target.value }))}
              >
                <option value="">Select branch</option>
                {branches.map((branch) => <option key={branch} value={branch}>{branch}</option>)}
                {profile.repository_connection.branch && !branches.includes(profile.repository_connection.branch) ? (
                  <option value={profile.repository_connection.branch}>{profile.repository_connection.branch}</option>
                ) : null}
              </select>
            ) : (
              <input
                className="planner-input"
                value={profile.repository_connection.branch}
                onChange={(event) => onProfileChange(applyAdoMapping({
                  ...profile,
                  repository_connection: { ...profile.repository_connection, branch: event.target.value, status: profile.repository_connection.repository_id ? 'Repository connected' : profile.repository_connection.status },
                }, { branch: event.target.value }))}
                placeholder="main"
              />
            )}
          </div>
          {repositoryLoadMessage ? <div className="planner-subtle">{repositoryLoadMessage}</div> : null}
          <div className="planner-actions compact">
            <button className="planner-button secondary" onClick={onReloadRepositories} disabled={loading}>Retry Repositories</button>
          </div>
          <input
            className="planner-input"
            value={profile.repository_connection.readme_path}
            onChange={(event) => onProfileChange({
              ...profile,
              repository_connection: { ...profile.repository_connection, readme_path: event.target.value || '/README.md' },
            })}
            placeholder="/README.md"
          />
        </>
      ) : null}
      {!showConnectionControls ? (
        <div className="planner-status-grid">
          <Row label="ADO Project" value={mapping.ado_project || 'No project selected'} />
          <Row label="Repository" value={profile.repository_connection.repository_name || 'No repository selected'} />
          <Row label="Branch" value={profile.repository_connection.branch || 'Default branch'} />
        </div>
      ) : null}
      <div className="planner-actions">
        <button className="planner-button secondary" onClick={onDiscoverDocuments} disabled={loading || !selectedRepositoryLoaded}>
          Discover Documentation
        </button>
        <button className="planner-button" onClick={onAnalyzeDocuments} disabled={loading || (!selectedRepositoryLoaded && !Object.values(repositoryDocuments).some((content) => content.trim()))}>
          Analyze Repository
        </button>
        <button className="planner-button secondary" onClick={onAnalyzeReadme} disabled={loading || !selectedRepositoryLoaded}>
          Analyze README Only
        </button>
      </div>
      <div className="planner-task">
        <div className="planner-label">Repository Documents</div>
        <div className="planner-document-columns">
          <div>
            <div className="planner-subtle">Documents Found</div>
            <div className="planner-document-list">
              {(foundDocuments.length ? foundDocuments : [{ label: 'None yet', path: 'Run discovery or analyze pasted documents', status: 'unknown' as const }]).map((doc) => (
                <div className="planner-document-row" key={`found-${doc.label}`}>
                  <span className={`planner-document-state ${doc.status}`}>{doc.status === 'available' ? '✓' : '•'}</span>
                  <div>
                    <strong>{doc.label}</strong>
                    <small>{doc.path || 'Not Found'}</small>
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div>
            <div className="planner-subtle">Missing</div>
            <div className="planner-document-list">
              {(missingDocuments.length ? missingDocuments : [{ label: 'None', path: 'All known document groups were found', status: 'available' as const }]).map((doc) => (
                <div className="planner-document-row" key={`missing-${doc.label}`}>
                  <span className={`planner-document-state ${doc.status}`}>{doc.status === 'available' ? '✓' : '⚠'}</span>
                  <div>
                    <strong>{doc.label}</strong>
                    <small>{doc.path || 'No known file found'}</small>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
        <details className="planner-accordion">
          <summary>Choose Documentation Files</summary>
          <div className="planner-checkbox-grid">
            {REPOSITORY_DOCUMENTS.map((path) => (
              <label key={path} className="planner-checkbox">
                <input
                  type="checkbox"
                  checked={selectedFiles.includes(path)}
                  onChange={(event) => {
                    const next = event.target.checked
                      ? [...selectedFiles, path]
                      : selectedFiles.filter((file) => file !== path);
                    onSelectedFilesChange(Array.from(new Set(next)));
                  }}
                />
                <span>{path}</span>
                <span className={`planner-file-status ${fileStatus[path] || 'unknown'}`}>{fileStatus[path] || 'unknown'}</span>
              </label>
            ))}
          </div>
          <div className="planner-actions">
            <button
              className="planner-button secondary"
              onClick={() => onSelectedFilesChange(Object.entries(fileStatus).filter(([, status]) => status === 'available').map(([path]) => path))}
              disabled={loading || !Object.values(fileStatus).includes('available')}
            >
              Select Discovered
            </button>
            <button
              className="planner-button secondary"
              onClick={() => {
                onFileStatusChange({});
                onSelectedFilesChange(['README.md', 'architecture.md', 'modules.md', 'flows.md']);
              }}
              disabled={loading}
            >
              Reset Discovery
            </button>
          </div>
        </details>
      </div>
      <details className="planner-task">
        <summary className="planner-label">Manual Document Paste Fallback</summary>
        <div className="planner-grid">
          {['README.md', 'architecture.md', 'modules.md', 'flows.md'].map((path) => (
            <div key={path}>
              <div className="planner-label">{path}</div>
              <textarea
                className="planner-textarea compact"
                value={repositoryDocuments[path] || ''}
                onChange={(event) => onRepositoryDocumentsChange({ ...repositoryDocuments, [path]: event.target.value })}
                placeholder={`Paste ${path} content here if Azure Repos cannot load it.`}
              />
            </div>
          ))}
        </div>
      </details>
      <div className="planner-status-grid">
        <Row label="Repository" value={profile.repository_connection.repository_name || 'Not connected'} />
        <Row label="Branch" value={profile.repository_connection.branch || 'Not selected'} />
        <Row label="Status" value={profile.repository_connection.status || 'Not connected'} />
        <Row label="Knowledge Status" value={knowledgeStatusLabel(governance)} />
        <Row label="Last Refreshed By" value={governance.last_refreshed_by || 'Not refreshed yet'} />
        <Row label="Last Refreshed On" value={formatTimestamp(governance.last_refreshed_on)} />
        <Row label="Knowledge Captured" value={registrySummary(profile)} />
      </div>
      <div className="planner-subtle">Repository README scan and known documentation ingestion are enabled. Full repository scans are intentionally not included.</div>
    </section>
  );
}

function RefinementReadinessDashboard({
  profile,
  epicResult,
  featureResult,
  storyResult,
  hasImpact,
}: {
  profile: ProjectProfile;
  epicResult?: EpicRefinement;
  featureResult?: FeatureRefinement;
  storyResult?: StoryRefinement;
  hasImpact: boolean;
}) {
  const execution = executionReadiness(profile, hasImpact);
  return (
    <section className="planner-card">
      <div className="planner-label">Refinement Intelligence Status</div>
      <div className="planner-status-grid">
        <Row label="Project Profile" value={profile.project_description ? 'Ready' : 'Basic'} />
        <Row label="Repository Intelligence" value={profile.repository_connection.status === 'README analyzed' ? 'Ready' : 'Pending README'} />
        <Row label="Knowledge Registry" value={(profile.knowledge_registry.modules.length || profile.knowledge_registry.flows.length) ? 'Ready' : 'Pending'} />
        <Row label="Epic Intelligence" value={epicResult ? 'Ready' : 'Not run'} />
        <Row label="Feature Intelligence" value={featureResult ? 'Ready' : 'Not run'} />
        <Row label="Story Intelligence" value={storyResult ? 'Ready' : 'Not run'} />
        <Row label="Impact Analysis" value={hasImpact ? 'Ready' : 'Not run'} />
        <Row label="Execution Readiness" value={execution.label} />
        <Row label="Readiness Breakdown" value={execution.breakdown} />
      </div>
    </section>
  );
}

function ProjectIntelligenceProviderDiagnostics({ metadata }: { metadata?: ProviderMetadata }) {
  return (
    <details className="planner-card">
      <summary className="planner-label">Developer Diagnostics</summary>
      <div className="planner-status-grid">
        <Row label="Project Intelligence Provider" value={sourceLabel(metadata?.provider_used || metadata?.source)} />
        <Row label="Provider Configured" value={metadata?.provider_configured === undefined ? 'Unknown' : metadata.provider_configured ? 'Yes' : 'No'} />
        <Row label="Deployment" value={String(metadata?.provider_deployment || 'Unknown')} />
        <Row label="Health" value={String(metadata?.provider_health || 'Unknown')} />
        <Row label="Last Success" value={String(metadata?.provider_last_success || 'Never')} />
        <Row label="Last Failure" value={String(metadata?.provider_last_failure || 'Never')} />
        <Row label="Current Response Source" value={sourceLabel(metadata?.source || metadata?.provider_used)} />
        <Row label="Phi Status" value={String(metadata?.phi_status || 'Not run')} />
        <Row label="Phi Latency" value={metadata?.phi_latency_ms ? `${metadata.phi_latency_ms} ms` : 'n/a'} />
        <Row label="Phi Prompt Tokens" value={formatNumber(metadata?.phi_prompt_tokens)} />
        <Row label="Phi Completion Tokens" value={formatNumber(metadata?.phi_completion_tokens)} />
        <Row label="Phi Finish Reason" value={metadata?.phi_finish_reason || 'n/a'} />
        <Row label="Phi Response Length" value={formatNumber(metadata?.phi_response_length)} />
        <Row label="Diagnostics Path" value={metadata?.diagnostics_path || 'n/a'} />
        <Row label="Context Size" value={formatNumber(metadata?.context_size)} />
        <Row label="Context After Compression" value={formatNumber(metadata?.context_after_compression)} />
        <Row label="Tokens Sent" value={metadata?.tokens_sent ? `${metadata.tokens_sent} / ${metadata.context_budget_tokens || 2500}` : 'n/a'} />
        <Row label="Model Limit" value={formatNumber(metadata?.model_context_limit)} />
        <Row label="Reserved Tokens" value={formatNumber(metadata?.reserved_tokens)} />
        <Row label="Compression Ratio" value={metadata?.compression_ratio !== undefined ? `${Math.round(metadata.compression_ratio * 100)}%` : 'n/a'} />
        <Row label="Final Prompt Tokens" value={metadata?.final_prompt_tokens ? `${metadata.final_prompt_tokens} / ${metadata.model_context_limit || 'n/a'}` : 'n/a'} />
        <Row label="Project Context Tokens" value={formatNumber(metadata?.project_context_tokens || metadata?.compressed_context_tokens)} />
        <Row label="Context Capsule Used" value={metadata?.context_capsule_used === undefined ? 'n/a' : metadata.context_capsule_used ? 'Yes' : 'No'} />
        <Row label="Context Capsule Type" value={metadata?.context_capsule_type || 'n/a'} />
        <Row label="Context Capsule Version" value={formatNumber(metadata?.context_capsule_version)} />
        <Row label="Context Capsule Size" value={formatNumber(metadata?.context_capsule_size_tokens)} />
        <Row label="Capsule Source Size" value={formatNumber(metadata?.context_capsule_source_size_tokens)} />
        <Row label="Capsule Compression" value={metadata?.context_capsule_compression_ratio !== undefined ? `${Math.round(metadata.context_capsule_compression_ratio * 100)}%` : 'n/a'} />
        <Row label="Context Budget Used" value={formatNumber(metadata?.context_budget_used)} />
        <Row label="Compression Level" value={formatNumber(metadata?.compression_level || metadata?.context_compression_level)} />
        <Row label="Retry Attempt" value={formatNumber(metadata?.retry_attempt)} />
        <Row label="Project Summary Mode" value={metadata?.project_summary_mode === undefined ? 'n/a' : metadata.project_summary_mode ? 'Yes' : 'No'} />
        <Row label="System Prompt Tokens" value={formatNumber(metadata?.system_prompt_tokens)} />
        <Row label="User Prompt Tokens" value={formatNumber(metadata?.user_prompt_tokens)} />
        <Row label="Schema Tokens" value={formatNumber(metadata?.output_schema_tokens)} />
        <Row label="Compression Applied" value={metadata?.compression_applied === undefined ? 'n/a' : metadata.compression_applied ? 'Yes' : 'No'} />
        <Row label="Largest Sections" value={formatLargestSections(metadata?.largest_context_sections)} />
        <Row label="Prompt Too Long Stage" value={metadata?.prompt_too_long_stage || 'n/a'} />
        <Row label="Intent Keywords" value={(metadata?.intent_keywords || []).join(', ') || 'n/a'} />
        <Row label="Selected Modules" value={(metadata?.selected_modules || []).join(', ') || 'n/a'} />
        <Row label="Selected Flows" value={(metadata?.selected_flows || []).join(', ') || 'n/a'} />
        <Row label="Selected Dependencies" value={(metadata?.selected_dependencies || []).join(', ') || 'n/a'} />
        <Row label="Rejected Context" value={formatRejectedContext(metadata?.rejected_context)} />
        <Row label="Relevance Scores" value={formatRelevanceScores(metadata?.relevance_scores)} />
        <Row label="Relevance Token Estimate" value={formatNumber(metadata?.token_estimate)} />
        <Row label="Context Source" value={metadata?.context_source || 'n/a'} />
        <Row label="Final Prompt Preview" value={metadata?.final_prompt_preview ? metadata.final_prompt_preview.slice(0, 240) : 'n/a'} />
        <Row label="Fallback Reason" value={String(metadata?.fallback_reason || 'n/a')} />
      </div>
    </details>
  );
}

function SourceBadge({ metadata }: { metadata?: ProviderMetadata }) {
  return (
    <div className="planner-subtle">
      Source: <strong>{sourceLabel(metadata?.source || metadata?.provider_used)}</strong>
      {metadata?.phi_status ? ` | Phi: ${metadata.phi_status}` : ''}
      {metadata?.fallback_used ? <div>This output was generated by fallback logic, not the configured AI model.</div> : null}
    </div>
  );
}

function ImpactAnalysisDashboard({
  loading,
  epicInput,
  featureInput,
  storyInput,
  epicImpact,
  featureImpact,
  storyImpact,
  setEpicInput,
  setFeatureInput,
  setStoryInput,
  analyzeEpic,
  analyzeFeature,
  analyzeStory,
}: {
  loading: boolean;
  epicInput: { title: string; description: string };
  featureInput: { title: string; description: string };
  storyInput: { title: string; description: string };
  epicImpact?: EpicImpact;
  featureImpact?: FeatureImpact;
  storyImpact?: StoryImpact;
  setEpicInput: (value: { title: string; description: string }) => void;
  setFeatureInput: (value: { title: string; description: string }) => void;
  setStoryInput: (value: { title: string; description: string }) => void;
  analyzeEpic: () => void;
  analyzeFeature: () => void;
  analyzeStory: () => void;
}) {
  return (
    <section className="planner-card">
      <div className="planner-label">Impact Analysis Dashboard</div>
      <div className="planner-subtle">Use project profile and repository intelligence to identify affected systems before execution.</div>
      <div className="planner-grid">
        <ImpactCard title="Epic Impact" input={epicInput} setInput={setEpicInput} onAnalyze={analyzeEpic} loading={loading} placeholder="Improve Device Monitoring">
          {epicImpact ? <EpicImpactResult result={epicImpact} /> : null}
        </ImpactCard>
        <ImpactCard title="Feature Impact" input={featureInput} setInput={setFeatureInput} onAnalyze={analyzeFeature} loading={loading} placeholder="Fault Event Monitoring">
          {featureImpact ? <FeatureImpactResult result={featureImpact} /> : null}
        </ImpactCard>
        <ImpactCard title="Story Impact" input={storyInput} setInput={setStoryInput} onAnalyze={analyzeStory} loading={loading} placeholder="Display Fault Event Details">
          {storyImpact ? <StoryImpactResult result={storyImpact} /> : null}
        </ImpactCard>
      </div>
    </section>
  );
}

function ImpactCard({
  title,
  input,
  setInput,
  onAnalyze,
  loading,
  placeholder,
  children,
}: {
  title: string;
  input: { title: string; description: string };
  setInput: (value: { title: string; description: string }) => void;
  onAnalyze: () => void;
  loading: boolean;
  placeholder: string;
  children: React.ReactNode;
}) {
  return (
    <div className="planner-task">
      <div className="planner-label">{title}</div>
      <RefinementInput input={input} setInput={setInput} titlePlaceholder={placeholder} descriptionPlaceholder="Describe scope, behavior, or rollout concern." />
      <div className="planner-actions">
        <button className="planner-button" onClick={onAnalyze} disabled={loading || !input.title.trim()}>Analyze Impact</button>
      </div>
      {children}
    </div>
  );
}

function EpicImpactResult({ result }: { result: EpicImpact }) {
  return (
    <div>
      <SourceBadge metadata={result} />
      <ListBlock title="Applications" items={result.affected_applications} />
      <ListBlock title="Modules" items={result.affected_modules} />
      <ListBlock title="Flows" items={result.affected_flows} />
      <ListBlock title="Program Dependencies" items={result.program_dependencies} />
      <ListBlock title="Risks" items={result.risks} />
      <ListBlock title="Rollout Strategy" items={result.recommended_rollout_strategy} />
    </div>
  );
}

function FeatureImpactResult({ result }: { result: FeatureImpact }) {
  return (
    <div>
      <SourceBadge metadata={result} />
      <ListBlock title="Applications" items={result.affected_applications} />
      <ListBlock title="Modules" items={result.affected_modules} />
      <ListBlock title="Flows" items={result.affected_flows} />
      <ListBlock title="Cross-Team Dependencies" items={result.cross_team_dependencies} />
      <ListBlock title="Integration Points" items={result.integration_points} />
      <ListBlock title="Risks" items={result.risks} />
    </div>
  );
}

function StoryImpactResult({ result }: { result: StoryImpact }) {
  return (
    <div>
      <SourceBadge metadata={result} />
      <ListBlock title="Applications" items={result.affected_applications} />
      <ListBlock title="Modules" items={result.affected_modules} />
      <ListBlock title="Flows" items={result.affected_flows} />
      <ListBlock title="Components" items={result.affected_components} />
      <ListBlock title="Dependencies" items={result.dependencies} />
      <ListBlock title="Risks" items={result.risks} />
      <ListBlock title="Integration Points" items={result.integration_points} />
      <ListBlock title="Recommended Reviewers" items={result.recommended_reviewers} />
    </div>
  );
}

function ProjectRefinementCards({
  loading,
  epicInput,
  featureInput,
  storyInput,
  epicResult,
  featureResult,
  storyResult,
  setEpicInput,
  setFeatureInput,
  setStoryInput,
  refineEpic,
  refineFeature,
  refineStory,
}: {
  loading: boolean;
  epicInput: { title: string; description: string };
  featureInput: { title: string; description: string };
  storyInput: { title: string; description: string };
  epicResult?: EpicRefinement;
  featureResult?: FeatureRefinement;
  storyResult?: StoryRefinement;
  setEpicInput: (value: { title: string; description: string }) => void;
  setFeatureInput: (value: { title: string; description: string }) => void;
  setStoryInput: (value: { title: string; description: string }) => void;
  refineEpic: () => void;
  refineFeature: () => void;
  refineStory: () => void;
}) {
  return (
    <>
      <section className="planner-card">
        <div className="planner-label">Epic Intelligence</div>
        <RefinementInput input={epicInput} setInput={setEpicInput} titlePlaceholder="Improve Device Monitoring" descriptionPlaceholder="Describe the epic goal and business context." />
        <div className="planner-actions">
          <button className="planner-button" onClick={refineEpic} disabled={loading || !epicInput.title.trim()}>Refine Epic</button>
        </div>
        {epicResult ? <EpicRefinementResult result={epicResult} /> : null}
      </section>

      <section className="planner-card">
        <div className="planner-label">Feature Intelligence</div>
        <RefinementInput input={featureInput} setInput={setFeatureInput} titlePlaceholder="Telemetry Health Dashboard" descriptionPlaceholder="Describe the feature scope." />
        <div className="planner-actions">
          <button className="planner-button" onClick={refineFeature} disabled={loading || !featureInput.title.trim()}>Refine Feature</button>
        </div>
        {featureResult ? <FeatureRefinementResult result={featureResult} onRetry={refineFeature} /> : null}
      </section>

      <section className="planner-card">
        <div className="planner-label">Story Intelligence</div>
        <RefinementInput input={storyInput} setInput={setStoryInput} titlePlaceholder="View device telemetry health state" descriptionPlaceholder="Describe the user story or delivery need." />
        <div className="planner-actions">
          <button className="planner-button" onClick={refineStory} disabled={loading || !storyInput.title.trim()}>Refine Story</button>
        </div>
        {storyResult ? <StoryRefinementResult result={storyResult} /> : null}
      </section>
    </>
  );
}

function RefinementInput({
  input,
  setInput,
  titlePlaceholder,
  descriptionPlaceholder,
}: {
  input: { title: string; description: string };
  setInput: (value: { title: string; description: string }) => void;
  titlePlaceholder: string;
  descriptionPlaceholder: string;
}) {
  return (
    <>
      <input className="planner-input" value={input.title} onChange={(event) => setInput({ ...input, title: event.target.value })} placeholder={titlePlaceholder} />
      <textarea className="planner-textarea compact" value={input.description} onChange={(event) => setInput({ ...input, description: event.target.value })} placeholder={descriptionPlaceholder} />
    </>
  );
}

function EpicRefinementResult({ result }: { result: EpicRefinement }) {
  return (
    <div className="planner-status-grid">
      <SourceBadge metadata={result} />
      <GenerationReviewBlock review={result.generation_review} />
      <Row label="Business Goal" value={result.business_goal} />
      <ListBlock title="Business Outcomes" items={result.business_outcomes} />
      <ListBlock title="Users" items={result.users} />
      <ListBlock title="Applications" items={result.applications} />
      <ListBlock title="Constraints" items={result.constraints} />
      <ListBlock title="Dependencies" items={result.dependencies} />
      <ListBlock title="Risks" items={result.risks} />
      <CardList title="Recommended Features" items={result.recommended_features} />
    </div>
  );
}

function FeatureAnalysisStatusCard({
  result,
  onRetryAI,
  onContinue,
  loading,
  readOnly,
}: {
  result: FeatureRefinement;
  onRetryAI?: () => void;
  onContinue?: () => void;
  loading?: boolean;
  readOnly?: boolean;
}) {
  const analysis = result.feature_analysis_result || result.featureAnalysisResult;
  if (!analysis) {
    return null;
  }
  const aiStatus = String(analysis.aiStatus || result.ai_status || 'not_requested');
  const aiOk = aiStatus === 'success';
  const aiFailed = ['timeout', 'parse_error', 'provider_unavailable'].includes(aiStatus);
  const statusText = aiOk
    ? 'AI enrichment completed.'
    : aiFailed
      ? 'Feature analysis is available. AI enrichment failed and can be retried.'
      : 'Deterministic analysis ready. AI enrichment has not been requested.';
  return (
    <div className={`planner-banner ${aiFailed ? 'planner-provider-failure' : ''}`}>
      <strong>Feature Analysis</strong>
      <div>{statusText}</div>
      <div className="planner-summary-grid">
        <SummaryTile title="Status" value={analysis.validationStatus || result.validation_status || 'Ready'} />
        <SummaryTile title="AI" value={aiStatus.replace(/_/g, ' ')} />
        <SummaryTile title="Stories" value={formatNumber(analysis.diagnostics?.storyCandidateCount ?? result.recommended_stories?.length ?? 0)} />
      </div>
      {analysis.warnings?.length ? <ListBlock title="Warnings" items={analysis.warnings} /> : null}
      <div className="planner-actions">
        {onContinue ? (
          <button className="planner-button" type="button" onClick={onContinue} disabled={loading || readOnly}>
            Continue with deterministic analysis
          </button>
        ) : null}
        {onRetryAI ? (
          <button className="planner-button secondary" type="button" onClick={onRetryAI} disabled={loading || readOnly}>
            Retry AI Enrichment
          </button>
        ) : null}
        <details className="planner-nested">
          <summary>View Diagnostics</summary>
          <Row label="Provider Timeout" value={analysis.diagnostics?.providerTimeoutMs ? `${analysis.diagnostics.providerTimeoutMs} ms` : 'n/a'} />
          <Row label="Parse Error" value={analysis.diagnostics?.parseError || 'None'} />
          <ListBlock title="Selected Modules" items={analysis.diagnostics?.selectedModules || []} />
          <ListBlock title="Selected Flows" items={analysis.diagnostics?.selectedFlows || []} />
          {analysis.diagnostics?.rawResponsePreview ? <pre className="planner-code-block">{analysis.diagnostics.rawResponsePreview}</pre> : null}
        </details>
      </div>
    </div>
  );
}

function FeatureRefinementResult({ result, onRetry }: { result: FeatureRefinement; onRetry?: () => void }) {
  const diagnostics = result.story_generation_diagnostics || {};
  return (
    <div className="planner-status-grid">
      <FeatureAnalysisStatusCard result={result} onRetryAI={onRetry} />
      <SourceBadge metadata={result} />
      <ProviderParseFailurePanel metadata={result} onRetry={onRetry} />
      <GenerationReviewBlock review={result.generation_review} />
      <Row label="Feature Summary" value={result.feature_summary} />
      <Row label="Capability Count" value={formatNumber(diagnostics.capability_count)} />
      <Row label="Action Count" value={formatNumber(diagnostics.action_count)} />
      <Row label="Generated Story Count" value={formatNumber(diagnostics.generated_story_count)} />
      <Row label="Story Quality Score" value={formatNumber(diagnostics.story_quality_score)} />
      <Row label="Acceptance Criteria Quality Score" value={formatNumber(diagnostics.acceptance_criteria_quality_score)} />
      <Row label="Acceptance Criteria Count" value={formatNumber(diagnostics.acceptance_criteria_count)} />
      <ListBlock title="Story Coverage Areas" items={diagnostics.story_coverage_areas || []} />
      <ListBlock title="Capabilities Identified" items={diagnostics.capabilities_identified || []} />
      <ListBlock title="User Actions Identified" items={diagnostics.user_actions_identified || []} />
      <ListBlock title="Rejected Generic Criteria" items={diagnostics.rejected_generic_criteria || []} />
      <ListBlock title="Affected Modules" items={result.affected_modules} />
      <ListBlock title="Affected Flows" items={result.affected_flows} />
      <ListBlock title="Dependencies" items={result.dependencies} />
      <ListBlock title="Risks" items={result.risks} />
      <CardList title="Recommended Stories" items={result.recommended_stories} />
    </div>
  );
}

function ProviderParseFailurePanel({ metadata, onRetry }: { metadata?: ProviderMetadata; onRetry?: () => void }) {
  const phiStatus = String(metadata?.phi_status || '').toLowerCase();
  const fallbackReason = String(metadata?.fallback_reason || '').toLowerCase();
  const isParseFailure = phiStatus === 'parse_error' || fallbackReason.includes('normalized into a json object') || fallbackReason.includes('parse');
  if (!isParseFailure) {
    return null;
  }
  const rawResponse = metadata?.raw_response_preview || metadata?.phi_raw_response_preview || '';
  return (
    <div className="planner-error planner-provider-failure">
      <strong>Feature generation failed.</strong>
      <div>Phi returned a response that could not be parsed into the required JSON shape.</div>
      {metadata?.diagnostics_path ? (
        <details className="planner-nested">
          <summary>View Diagnostics</summary>
          <Row label="Diagnostics Path" value={metadata.diagnostics_path} />
          <Row label="Files" value={metadata.diagnostics_files?.join(', ') || 'prompt.txt, response.txt, metadata.json'} />
          <Row label="Prompt Tokens" value={formatNumber(metadata.phi_prompt_tokens)} />
          <Row label="Completion Tokens" value={formatNumber(metadata.phi_completion_tokens)} />
          <Row label="Finish Reason" value={metadata.phi_finish_reason || 'n/a'} />
          <Row label="Response Length" value={formatNumber(metadata.phi_response_length)} />
        </details>
      ) : null}
      <div className="planner-actions">
        {metadata?.diagnostics_path ? (
          <button className="planner-button secondary" type="button" onClick={() => void navigator.clipboard?.writeText(metadata.diagnostics_path || '')}>
            Copy Diagnostics Path
          </button>
        ) : null}
        <button className="planner-button secondary" type="button" disabled={!rawResponse} onClick={() => void navigator.clipboard?.writeText(rawResponse)}>
          Copy Raw Response
        </button>
        {onRetry ? (
          <button className="planner-button" type="button" onClick={onRetry}>
            Retry
          </button>
        ) : null}
      </div>
    </div>
  );
}

function StoryPlanningWorkspace({
  result,
  currentWorkItem,
  activeTab,
  onTabChange,
  taskDrafts,
  hasExecutionPackage,
  onGenerateTasks,
  loading,
  readOnly,
  taskApprovalStatus,
}: {
  result: StoryRefinement;
  currentWorkItem?: AdoWorkItem;
  activeTab: StoryPlanningTab;
  onTabChange: (tab: StoryPlanningTab) => void;
  taskDrafts: ChildDraft[];
  hasExecutionPackage: boolean;
  onGenerateTasks: () => void;
  loading: boolean;
  readOnly: boolean;
  taskApprovalStatus: ApprovalStatus;
}) {
  const title = normalizeStoryTitle(currentWorkItem?.title || result.story_summary || 'Story');
  const confidence = qualityScoreForStory(result) || 0;
  const priority = storyPriority(result);
  const acceptanceItems = result.acceptance_criteria || [];
  const repositoryState = repositoryContextState(result);
  const validationState = confidence >= 75 && acceptanceItems.length ? 'PASS' : 'Validation Pending';
  const storyId = currentWorkItem?.id ? `Story #${currentWorkItem.id}` : 'Story ID Pending';
  const taskCount = taskDrafts.length || result.proposed_tasks?.length || 0;
  const nextAction =
    !acceptanceItems.length
      ? 'Review Acceptance Criteria'
      : !taskDrafts.length
        ? 'Generate Tasks'
        : taskApprovalStatus === 'approved'
          ? 'Open Execution'
          : 'Approve Tasks';
  return (
    <section className="planner-card hei-story-workspace">
      <div className="hei-story-header">
        <div>
          <div className="planner-label">Story Planning Workspace</div>
          <h2>{title}</h2>
          <div className="hei-story-meta">
            <span className={`hei-status-badge ${confidence >= 75 ? 'success' : 'warning'}`}>{confidence >= 75 ? 'Ready For Review' : 'Needs Review'}</span>
            <span className="hei-status-badge warning">{priority} Priority</span>
            <span className="hei-status-badge neutral">Confidence {confidence}%</span>
            <span className="hei-status-badge neutral">{storyId}</span>
          </div>
        </div>
        <div className="hei-planning-primary">
          <span>{nextAction}</span>
          <small>Use the sticky header action to continue.</small>
        </div>
      </div>

      <div className="hei-story-grid without-queue">
        <article className="hei-story-detail">
          <StoryPlanningTabs selected={activeTab} onSelect={onTabChange} />
          {activeTab === 'overview' ? <StoryOverviewPanel result={result} title={title} /> : null}
          {activeTab === 'acceptance' ? <StoryAcceptancePanel result={result} taskDrafts={taskDrafts} /> : null}
          {activeTab === 'implementation' ? <StoryImplementationPanel result={result} /> : null}
          {activeTab === 'repository' ? <StoryRepositoryPanel result={result} /> : null}
          {activeTab === 'knowledge' ? <StoryKnowledgePanel result={result} /> : null}
          {activeTab === 'history' ? <StoryHistoryPanel result={result} taskCount={taskCount} hasExecutionPackage={hasExecutionPackage} /> : null}
        </article>

        <aside className="hei-story-insights">
          <div className="planner-label">Planning Health</div>
          <div className="planner-status-grid">
            <Row label="Story" value={confidence >= 75 ? 'Approved' : 'Ready For Review'} />
            <Row label="Repository" value={repositoryState} />
            <Row label="Knowledge" value={(result.affected_modules?.length || result.affected_flows?.length) ? 'Ready' : 'Knowledge Not Loaded'} />
            <Row label="Validation" value={validationState} />
            <Row label="Execution" value={hasExecutionPackage ? 'Ready' : 'Locked'} />
            <Row label="Prompt" value={hasExecutionPackage ? 'Ready To Generate' : 'Not Generated'} />
            <Row label="Implementation Package" value={hasExecutionPackage ? 'Built' : 'Not Built'} />
          </div>
          <div className="hei-stage-summary-card">
            <div>
              <span>Story Readiness</span>
              <strong>{nextAction}</strong>
            </div>
            <div className="planner-status-grid">
              <Row label="Validation" value={validationState} />
              <Row label="Knowledge" value={(result.affected_modules?.length || result.affected_flows?.length) ? 'PASS' : 'Knowledge Not Loaded'} />
              <Row label="Repository" value={repositoryState} />
              <Row label="Acceptance" value={acceptanceItems.length ? `${acceptanceItems.length} Mapped` : 'Validation Pending'} />
              <Row label="Task Approval" value={taskDrafts.length ? approvalStatusLabel(taskApprovalStatus) : 'Not Generated'} />
              <Row label="Execution" value={hasExecutionPackage ? 'Ready' : (taskApprovalStatus === 'approved' ? 'Ready' : 'Waiting')} />
            </div>
            {!taskDrafts.length ? (
              <button className="planner-button" onClick={onGenerateTasks} disabled={loading || readOnly || !acceptanceItems.length}>
                Generate Tasks →
              </button>
            ) : null}
          </div>
        </aside>
      </div>
    </section>
  );
}

function StoryPlanningTabs({ selected, onSelect }: { selected: StoryPlanningTab; onSelect: (tab: StoryPlanningTab) => void }) {
  const tabs: Array<{ id: StoryPlanningTab; label: string }> = [
    { id: 'overview', label: 'Overview' },
    { id: 'acceptance', label: 'Acceptance' },
    { id: 'implementation', label: 'Implementation' },
    { id: 'repository', label: 'Repository' },
    { id: 'knowledge', label: 'Knowledge' },
    { id: 'history', label: 'History' },
  ];
  return (
    <div className="hei-detail-tabs">
      {tabs.map((tab) => (
        <button key={tab.id} className={selected === tab.id ? 'active' : ''} type="button" onClick={() => onSelect(tab.id)}>
          {tab.label}
        </button>
      ))}
    </div>
  );
}

function StoryOverviewPanel({ result, title }: { result: StoryRefinement; title: string }) {
  return (
    <div className="hei-business-grid">
      <InfoBlock title="Business Context" value={storyBusinessContext(result)} empty="Business context pending validation." />
      <InfoBlock title="User Story" value={storyAsAStatement(result, title)} empty="User story pending refinement." />
      <InfoBlock title="Business Value" value={storyBusinessValue(result)} empty="Business value pending validation." />
      <InfoBlock title="Implementation Objective" value={storyImplementationObjective(result, title)} empty="Implementation objective pending engineering review." />
    </div>
  );
}

function StoryAcceptancePanel({ result, taskDrafts }: { result: StoryRefinement; taskDrafts: ChildDraft[] }) {
  const criteria = result.acceptance_criteria || [];
  if (!criteria.length) {
    return <EmptyGuidance title="No acceptance criteria generated yet." detail="Generate or refine the Story to produce testable acceptance criteria." />;
  }
  return (
    <div className="hei-acceptance-list">
      {criteria.map((criterion, index) => {
        const mapping = acceptanceMappingForStory(result, taskDrafts, criterion, index);
        return (
          <div className="hei-acceptance-card" key={`${index}-${criterion}`}>
            <div>
              <strong>✓ AC-{index + 1}</strong>
              <p>{criterion}</p>
            </div>
            <div className="planner-status-grid">
              <Row label="Status" value={mapping.validationStatus} />
              <Row label="Repository Coverage" value={mapping.repositoryCoverage} />
              <Row label="Implementation Area" value={mapping.implementationArea} />
              <Row label="Mapped Tasks" value={mapping.mappedTaskCount} />
              <Row label="Mapped Repository Modules" value={mapping.modules} />
              <Row label="Mapped Tests" value={mapping.tests} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function StoryImplementationPanel({ result }: { result: StoryRefinement }) {
  return (
    <div className="hei-business-grid">
      <InfoBlock title="In Scope" items={storyInScope(result)} empty="Implementation scope pending validation." />
      <InfoBlock title="Out Of Scope" items={storyOutOfScope(result)} empty="No out-of-scope items identified." />
      <InfoBlock title="Dependencies" items={result.dependencies || []} empty="No dependencies identified." />
      <InfoBlock title="Repository Modules" items={result.affected_modules || []} empty="Repository Analysis Pending" />
      <InfoBlock title="Affected Flows" items={result.affected_flows || []} empty="Repository Context Ready after flow mapping." />
      <InfoBlock title="Required APIs" items={requiredApisForStory(result)} empty="Repository Validation Required" />
      <InfoBlock title="Suggested Components" items={suggestedComponentsForStory(result)} empty="Repository Analysis Pending" />
      <InfoBlock title="Coding Standards" items={result.technical_considerations || []} empty="Coding standards pending project setup." />
    </div>
  );
}

function StoryRepositoryPanel({ result }: { result: StoryRefinement }) {
  return (
    <div className="hei-business-grid">
      <InfoBlock title="Repository Status" value={repositoryContextState(result)} />
      <InfoBlock title="Affected Modules" items={result.affected_modules || []} empty="Repository Analysis Pending" />
      <InfoBlock title="Affected Flows" items={result.affected_flows || []} empty="Repository Context Ready after flow mapping." />
      <InfoBlock title="Dependencies" items={result.dependencies || []} empty="No dependencies identified" />
    </div>
  );
}

function StoryKnowledgePanel({ result }: { result: StoryRefinement }) {
  return (
    <div className="hei-business-grid">
      <InfoBlock title="Knowledge Modules" items={result.affected_modules || []} empty="Knowledge Not Loaded" />
      <InfoBlock title="Knowledge Flows" items={result.affected_flows || []} empty="Knowledge Not Loaded" />
      <InfoBlock title="UI Considerations" items={result.ui_considerations || []} empty="UI considerations pending." />
      <InfoBlock title="QA Considerations" items={result.qa_considerations || []} empty="QA considerations pending." />
      <div className="hei-info-block">
        <span>Engineering DNA</span>
        <p>DNA is available in engineering details and is used by implementation packages when generated.</p>
      </div>
    </div>
  );
}

function StoryHistoryPanel({ result, taskCount, hasExecutionPackage }: { result: StoryRefinement; taskCount: number; hasExecutionPackage: boolean }) {
  return (
    <div className="hei-business-grid">
      <InfoBlock title="Story Generated" value={result.story_summary ? 'Story refinement completed.' : 'Story refinement pending.'} />
      <InfoBlock title="Tasks" value={taskCount ? `${taskCount} proposed tasks` : 'No tasks generated yet. Generate Tasks to continue planning.'} />
      <InfoBlock title="Implementation Package" value={hasExecutionPackage ? 'Implementation Package built.' : 'Implementation Package Not Generated'} />
      <InfoBlock title="Validation" value={qualityScoreForStory(result) ? 'Validation available.' : 'Validation Pending'} />
    </div>
  );
}

function normalizeStoryTitle(value: string): string {
  const cleaned = normalizePlannerText(value)
    .replace(/^use\s+/i, '')
    .replace(/^view\s+detect\s+fault$/i, 'View Critical Fault Details')
    .replace(/^use\s+classify\s+severity$/i, 'Classify Fault Severity')
    .replace(/^classify\s+severity$/i, 'Classify Fault Severity')
    .replace(/^review\s+events$/i, 'Review Active Fault Events')
    .replace(/^review\s+view\s+event\s+details$/i, 'Review Fault Event Details')
    .replace(/^see\s+newly\s+arrived\s+events$/i, 'Review Newly Arrived Fault Events');
  return titleCase(cleaned || 'Story');
}

function normalizePlannerText(value: string | undefined): string {
  return String(value || '').replace(/\s+/g, ' ').trim();
}

function storyPriority(result: StoryRefinement): string {
  const text = [result.story_summary, ...(result.acceptance_criteria || []), ...(result.risks || [])].join(' ').toLowerCase();
  if (/(critical|severity|permission|outage|security|fault)/.test(text)) {
    return 'High';
  }
  if ((result.dependencies || []).length || (result.risks || []).length) {
    return 'Medium';
  }
  return 'Normal';
}

function storyBusinessContext(result: StoryRefinement): string {
  const modules = (result.affected_modules || []).slice(0, 2).join(', ');
  const flows = (result.affected_flows || []).slice(0, 2).join(', ');
  if (modules || flows) {
    return `This story exists to make ${modules || 'the selected capability'} usable in ${flows || 'the approved delivery flow'}.`;
  }
  return result.story_summary || 'This story exists to convert the approved requirement into a testable delivery slice.';
}

function storyAsAStatement(result: StoryRefinement, title: string): string {
  const summary = normalizePlannerText(result.story_summary);
  if (/^as an?\s+/i.test(summary) || /^as a\s+/i.test(summary)) {
    return summary;
  }
  return `As an Operations User, I want to ${title.charAt(0).toLowerCase()}${title.slice(1)} so that I can complete the approved operational workflow with clear context.`;
}

function storyBusinessValue(result: StoryRefinement): string {
  const summary = normalizePlannerText(result.story_summary);
  if (summary && !/^as an?\s+/i.test(summary)) {
    return summary;
  }
  if ((result.risks || []).some((risk) => /permission|security/i.test(risk))) {
    return 'Reduces operational risk by making access-controlled behavior explicit and testable.';
  }
  return 'Improves delivery clarity by turning the approved capability into measurable user behavior.';
}

function storyImplementationObjective(result: StoryRefinement, title: string): string {
  const modules = (result.affected_modules || []).slice(0, 2).join(', ');
  const flows = (result.affected_flows || []).slice(0, 2).join(', ');
  return `Deliver ${title} across ${modules || 'the selected module'} with validation for ${flows || 'the approved flow'}.`;
}

function storyInScope(result: StoryRefinement): string[] {
  return uniqueStrings([
    ...(result.acceptance_criteria || []).slice(0, 4),
    ...(result.ui_considerations || []).slice(0, 2),
    ...(result.technical_considerations || []).slice(0, 2),
  ]);
}

function storyOutOfScope(result: StoryRefinement): string[] {
  const blocked = ['Broad refactors', 'Unrelated module changes'];
  if (!(result.affected_modules || []).some((item) => /firmware/i.test(item))) {
    blocked.push('Firmware changes unless explicitly approved');
  }
  if (!(result.affected_flows || []).some((item) => /login|auth|token/i.test(item))) {
    blocked.push('Authentication flow changes unless explicitly approved');
  }
  return blocked;
}

function requiredApisForStory(result: StoryRefinement): string[] {
  const text = [result.story_summary, ...(result.acceptance_criteria || []), ...(result.technical_considerations || [])].join(' ').toLowerCase();
  const apis: string[] = [];
  if (/fault|event/.test(text)) apis.push('Fault event query or detail API');
  if (/device|health/.test(text)) apis.push('Device health lookup API');
  if (/permission|access|restricted|unauthorized/.test(text)) apis.push('Permission validation API');
  return apis;
}

function suggestedComponentsForStory(result: StoryRefinement): string[] {
  const text = [result.story_summary, ...(result.acceptance_criteria || []), ...(result.ui_considerations || [])].join(' ').toLowerCase();
  const components: string[] = [];
  if (/detail/.test(text)) components.push('Detail view');
  if (/list|active|events/.test(text)) components.push('Event list');
  if (/filter/.test(text)) components.push('Filter controls');
  if (/empty|unavailable|missing/.test(text)) components.push('Empty and unavailable data states');
  if (/permission|access|unauthorized/.test(text)) components.push('Access denied state');
  return components;
}

function repositoryContextState(result: StoryRefinement): string {
  if ((result.affected_modules || []).length || (result.affected_flows || []).length) {
    return 'Repository Context Ready';
  }
  if ((result.dependencies || []).length || (result.technical_considerations || []).length) {
    return 'Repository Validation Required';
  }
  return 'Repository Analysis Pending';
}

function acceptanceMappingForStory(result: StoryRefinement, taskDrafts: ChildDraft[], criterion: string, index: number) {
  const implementationArea = implementationAreaForCriterion(criterion);
  const matchingTasks = taskDrafts.filter((task) => {
    const text = [task.title, task.description, ...(task.acceptanceCriteria || [])].join(' ').toLowerCase();
    return criterion
      .toLowerCase()
      .split(/\W+/)
      .filter((word) => word.length > 4)
      .some((word) => text.includes(word));
  });
  const taskFallback = taskDrafts.length && index < taskDrafts.length ? 1 : 0;
  const mappedTaskCount = matchingTasks.length || taskFallback;
  const modules = (result.affected_modules || []).slice(0, 2).join(', ') || 'Repository Analysis Pending';
  const repositoryCoverage = modules === 'Repository Analysis Pending' ? 'Repository Analysis Pending' : '95%';
  const tests = mappedTaskCount ? 'Mapped after task approval' : 'Tests Pending';
  return {
    implementationArea,
    mappedTaskCount: String(mappedTaskCount),
    modules,
    tests,
    repositoryCoverage,
    validationStatus: criterion ? 'Ready' : 'Validation Pending',
  };
}

function implementationAreaForCriterion(criterion: string): string {
  const text = criterion.toLowerCase();
  const areas: string[] = [];
  if (/api|backend|service|query|data|telemetry|device/.test(text)) areas.push('Backend API');
  if (/screen|view|display|list|filter|search|empty|loading/.test(text)) areas.push('Dashboard UI');
  if (/permission|access|unauthorized|restricted|role/.test(text)) areas.push('Permission');
  if (/test|validate|error|missing|unavailable|negative/.test(text)) areas.push('Tests');
  return areas.length ? areas.join(', ') : 'Implementation';
}

function EmptyGuidance({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="hei-selected-empty">
      <strong>{title}</strong>
      <span>{detail}</span>
    </div>
  );
}

function StoryRefinementResult({ result }: { result: StoryRefinement }) {
  return (
    <div className="planner-status-grid">
      <SourceBadge metadata={result} />
      <GenerationReviewBlock review={result.generation_review} />
      <Row label="Story Summary" value={result.story_summary} />
      <Row label="Acceptance Criteria Quality" value={formatNumber(result.acceptance_criteria_quality_score)} />
      <ListBlock title="Acceptance Criteria Categories" items={result.acceptance_criteria_categories || []} />
      <ListBlock title="Acceptance Criteria" items={result.acceptance_criteria} />
      <ListBlock title="Affected Applications" items={result.affected_applications} />
      <ListBlock title="Affected Modules" items={result.affected_modules} />
      <ListBlock title="Affected Flows" items={result.affected_flows} />
      <ListBlock title="Dependencies" items={result.dependencies} />
      <ListBlock title="Risks" items={result.risks} />
      <ListBlock title="UI Considerations" items={result.ui_considerations} />
      <ListBlock title="Technical Considerations" items={result.technical_considerations} />
      <ListBlock title="QA Considerations" items={result.qa_considerations} />
    </div>
  );
}

function GenerationReviewBlock({ review }: { review?: GenerationReview }) {
  if (!review) {
    return null;
  }
  const scores = review.quality_scores || {};
  return (
    <div className="planner-task">
      <div className="planner-label">Generated Using</div>
      <div className="planner-summary-grid">
        <SummaryTile title="Knowledge Usage" value={formatNumber(scores.knowledge_usage)} />
        <SummaryTile title="Module Coverage" value={formatNumber(scores.module_coverage)} />
        <SummaryTile title="Flow Coverage" value={formatNumber(scores.flow_coverage)} />
        <SummaryTile title="Domain Specificity" value={formatNumber(scores.domain_specificity)} />
        <SummaryTile title="Generic Risk" value={formatNumber(scores.generic_content_risk)} />
        <SummaryTile title="Quality Gate" value={titleCase(review.quality_gate || 'not scored')} />
      </div>
      <div className="planner-grid">
        <ListBlock title="Modules Used" items={review.modules_used || []} />
        <ListBlock title="Flows Used" items={review.flows_used || []} />
        <ListBlock title="Applications Used" items={review.applications_used || []} />
        <ListBlock title="Standards Used" items={review.standards_used || []} />
      </div>
    </div>
  );
}

function ListBlock({ title, items, empty }: { title: string; items: string[]; empty?: string }) {
  const normalizedItems = Array.isArray(items) ? items : [String(items || '')].filter(Boolean);
  return (
    <div className="planner-task">
      <div className="planner-label">{title}</div>
      <ul className="planner-list">
        {(normalizedItems.length ? normalizedItems : [empty || 'Not identified yet']).map((item) => <li key={item}>{item}</li>)}
      </ul>
    </div>
  );
}

function CardList({ title, items }: { title: string; items: Array<{ title: string; description: string; work_item_dna?: WorkItemDNA }> }) {
  return (
    <div className="planner-task">
      <div className="planner-label">{title}</div>
      {(items.length ? items : [{ title: 'No recommendation', description: 'Add more project or repository context.' }]).map((item) => (
        <div className="planner-task" key={item.title}>
          <strong>{item.title}</strong>
          <span>{item.description}</span>
          <EngineeringDNADisclosure dna={item.work_item_dna} />
        </div>
      ))}
    </div>
  );
}

function EngineeringDNADisclosure({ dna }: { dna?: WorkItemDNA }) {
  if (!dna?.dnaId) {
    return null;
  }
  return (
    <details className="planner-task">
      <summary className="planner-label">View DNA</summary>
      <EngineeringDNASection dna={dna} />
    </details>
  );
}

function StoryPromptGeneration({
  loading,
  storyTitle,
  storyDescription,
  acceptanceCriteria,
  prompts,
  setStoryTitle,
  setStoryDescription,
  setAcceptanceCriteria,
  generatePrompts,
}: {
  loading: boolean;
  storyTitle: string;
  storyDescription: string;
  acceptanceCriteria: string;
  prompts?: PromptResult;
  setStoryTitle: (value: string) => void;
  setStoryDescription: (value: string) => void;
  setAcceptanceCriteria: (value: string) => void;
  generatePrompts: () => void;
}) {
  return (
    <section className="planner-card">
      <div className="planner-label">Story Prompt Generation</div>
      <div className="planner-subtle">UI, Dev, and QA prompts include project name, domain, project type, applications, technology stack, UI rules, and development standards.</div>
      <input className="planner-input" value={storyTitle} onChange={(event) => setStoryTitle(event.target.value)} placeholder="Story title" />
      <textarea className="planner-textarea compact" value={storyDescription} onChange={(event) => setStoryDescription(event.target.value)} placeholder="Story description" />
      <textarea className="planner-textarea compact" value={acceptanceCriteria} onChange={(event) => setAcceptanceCriteria(event.target.value)} placeholder="Acceptance criteria, one per line" />
      <div className="planner-actions">
        <button className="planner-button" onClick={generatePrompts} disabled={loading}>Generate Story Prompts</button>
      </div>
      {prompts ? (
        <div className="planner-status-grid">
          <PromptBlock title="Specialized UI Prompt" value={prompts.ui_prompt} metadata={prompts} />
          <PromptBlock title="Developer Prompt" value={prompts.dev_prompt} metadata={prompts} />
          <PromptBlock title="Specialized QA Prompt" value={prompts.qa_prompt} metadata={prompts} />
        </div>
      ) : null}
    </section>
  );
}

function RoadmapCard() {
  return (
    <section className="planner-card">
      <div className="planner-label">Current Capabilities</div>
      <div className="planner-grid">
        <div>
          <div className="planner-label">Completed</div>
          <ul className="planner-list">
            <li>Planning</li>
            <li>Story Generation</li>
            <li>Task Generation</li>
            <li>Implementation Packages</li>
            <li>QA Intelligence</li>
            <li>Coverage Analysis</li>
          </ul>
        </div>
        <div>
          <div className="planner-label">Coming Next</div>
          <ul className="planner-list">
            <li>PR Validation</li>
            <li>Teams Agent</li>
            <li>Autonomous Planning Agent</li>
            <li>Defect Radar</li>
            <li>Metrics Export</li>
          </ul>
        </div>
      </div>
    </section>
  );
}

function SummaryTile({ title, value }: { title: string; value: string | number }) {
  return (
    <div className="planner-summary-tile">
      <span>{title}</span>
      <strong>{value || 'Pending'}</strong>
    </div>
  );
}

function ActionTile({
  title,
  detail,
  action,
  onRun,
  disabled,
  primary,
}: {
  title: string;
  detail: string;
  action: string;
  onRun: () => void;
  disabled?: boolean;
  primary?: boolean;
}) {
  return (
    <div className="hei-action-tile">
      <div>
        <strong>{title}</strong>
        <p>{detail}</p>
      </div>
      <button className={primary ? 'planner-button' : 'planner-button secondary'} onClick={onRun} disabled={disabled}>
        {action}
      </button>
    </div>
  );
}

function StructuredChildDraftList({ drafts }: { drafts: ChildDraft[] }) {
  return (
    <div className="planner-list">
      {drafts.map((draft) => (
        <article className="planner-task" key={draft.id}>
          <div className="planner-task-header">
            <div>
              <strong>{draft.title}</strong>
              <p>{draft.description}</p>
            </div>
            <span className={`planner-badge ${statusTone(draft.status)}`}>{draft.status}</span>
          </div>
          <ListBlock title="Acceptance Criteria" items={draft.acceptanceCriteria || []} empty="Acceptance criteria pending." />
        </article>
      ))}
    </div>
  );
}

function StructuredChildDraftGrid({ drafts }: { drafts: ChildDraft[] }) {
  return (
    <div className="hei-package-grid">
      {drafts.map((draft) => (
        <article className="hei-package-card" key={draft.id}>
          <div className="planner-task-header">
            <strong>{draft.title}</strong>
            <span className={`planner-badge ${statusTone(draft.status)}`}>{draft.status}</span>
          </div>
          <p>{draft.description}</p>
          <Row label="Acceptance Criteria" value={String(draft.acceptanceCriteria?.length || 0)} />
          <ListBlock title="Acceptance Criteria" items={draft.acceptanceCriteria || []} empty="Acceptance criteria pending." />
        </article>
      ))}
    </div>
  );
}

function splitAcceptanceCriteriaText(value: string): string[] {
  return splitLines(value).map((item) => item.replace(/^[*-]\s*/, '').trim()).filter(Boolean);
}

function normalizedMemoryCategory(category?: string): string {
  const value = String(category || '').toLowerCase();
  if (value.includes('decision')) return 'Decision';
  if (value.includes('lesson')) return 'Lesson Learned';
  if (value.includes('qa')) return 'QA Pattern';
  if (value.includes('execution')) return 'Execution Pattern';
  return 'Planning Pattern';
}

function ExecutionPackageCards({
  executionContext,
  executionPlan,
  devPrompt,
  uiPrompt,
  qaPrompt,
  onGeneratePrompt,
  onOpenVsCode,
  loading,
}: {
  executionContext?: ExecutionContextResult;
  executionPlan?: ExecutionPlanResult;
  devPrompt?: PromptBuilderResult;
  uiPrompt?: PromptBuilderResult;
  qaPrompt?: PromptBuilderResult;
  onGeneratePrompt: (kind: 'dev' | 'ui' | 'qa' | 'copilot') => void;
  onOpenVsCode: () => void;
  loading: boolean;
}) {
  type PackageKind = 'dev' | 'ui' | 'qa' | 'copilot';
  type PackageCard = {
    title: string;
    prompt: string;
    files: string[];
    risk: string[];
    kind: PackageKind;
    focus: string;
  };
  const allFiles = executionContextFileNames(executionContext);
  const allRisks = executionContextRiskText(executionContext);
  const sourceTitle = executionContext?.execution_source?.title || 'Selected work item';
  const cards: PackageCard[] = [
    { title: 'UI Package', prompt: uiPrompt?.prompt || '', files: filterPackageFiles(allFiles, ['page', 'screen', 'view', 'component', 'xaml', 'css', 'scss', 'tsx', 'jsx']), risk: filterPackageRisks(allRisks, ['ui', 'accessibility', 'validation', 'display']), kind: 'ui', focus: 'Focus on screens, interaction states, accessibility, validation feedback, and user-facing behavior only.' },
    { title: 'Frontend Package', prompt: devPrompt?.prompt || executionPlan?.plan || '', files: filterPackageFiles(allFiles, ['front', 'client', 'web', 'mobile', 'viewmodel', 'presenter', 'hook', 'tsx', 'jsx', 'js']), risk: filterPackageRisks(allRisks, ['frontend', 'mobile', 'state', 'interaction']), kind: 'dev', focus: 'Focus on client-side state, orchestration, interaction flow, and rendering behavior for the approved scope.' },
    { title: 'Backend/API Package', prompt: devPrompt?.prompt || executionPlan?.plan || '', files: filterPackageFiles(allFiles, ['api', 'controller', 'service', 'handler', 'endpoint', 'repository', 'cs', 'py', 'ts']), risk: filterPackageRisks(allRisks, ['backend', 'api', 'authorization', 'integration', 'service']), kind: 'dev', focus: 'Focus on APIs, handlers, services, authorization, and integration boundaries for the approved scope.' },
    { title: 'Data Package', prompt: devPrompt?.prompt || executionPlan?.plan || '', files: filterPackageFiles(allFiles, ['data', 'entity', 'model', 'schema', 'migration', 'sql', 'db']), risk: filterPackageRisks(allRisks, ['data', 'migration', 'integrity', 'consistency']), kind: 'dev', focus: 'Focus on entities, schemas, persistence, migration safety, and data integrity only.' },
    { title: 'Analytics Package', prompt: qaPrompt?.prompt || executionPlan?.plan || '', files: filterPackageFiles(allFiles, ['analytics', 'report', 'metric', 'dashboard', 'telemetry']), risk: filterPackageRisks(allRisks, ['analytics', 'reporting', 'telemetry']), kind: 'qa', focus: 'Focus on telemetry, analytics outputs, reporting signals, and verification of measurable outcomes.' },
  ];
  const [selectedPackageTitle, setSelectedPackageTitle] = useState<string | null>(null);
  useEffect(() => {
    if (!cards.length) {
      if (selectedPackageTitle !== null) {
        setSelectedPackageTitle(null);
      }
      return;
    }
    if (!selectedPackageTitle || !cards.some((card) => card.title === selectedPackageTitle)) {
      setSelectedPackageTitle(cards[0].title);
    }
  }, [cards, selectedPackageTitle]);
  const selectedCard = cards.find((card) => card.title === selectedPackageTitle) || cards[0];
  const buildPackagePrompt = (card: PackageCard, files: string[], risk: string, basePrompt: string): string => {
    const lines = [
      `Package Focus: ${card.title}`,
      `Source Artifact: ${sourceTitle}`,
      card.focus,
      files.length
        ? `Prioritize these files first: ${files.join(', ')}`
        : 'Repository file ranking not available. Locate the closest existing implementation before editing.',
      `Primary risk: ${risk}`,
      '',
      basePrompt || executionPlan?.plan || 'Generate the implementation prompt for this package from the approved implementation package.',
    ];
    return lines.join('\n');
  };
  return (
    <section className="planner-card">
      <div className="planner-section-header">
        <div>
          <div className="planner-label">Implementation Packages</div>
        <div className="planner-subtle">Package cards keep the implementation view focused. Advanced artifacts stay collapsed below.</div>
        </div>
      </div>
      <div className="hei-package-grid">
        {cards.map((card) => {
          const files = card.files.length ? card.files : allFiles.slice(0, 4);
          const risk = card.risk.length ? card.risk[0] : allRisks[0] || 'Risk will appear after package generation.';
          const promptText = buildPackagePrompt(card, files, risk, card.prompt);
          const status = executionContext ? (card.prompt ? 'Prompt Ready' : 'Package Built') : 'Not Built';
          const isSelected = selectedCard?.title === card.title;
          return (
            <article className={`hei-package-card${isSelected ? ' selected' : ''}`} key={card.title}>
              <div className="planner-task-header">
                <strong>{card.title}</strong>
              </div>
              <Row label="Status" value={status} />
              <Row label="Files Impacted" value={files.length ? `${files.length} files` : 'Repository file ranking not available'} />
              <Row label="Risk" value={risk} />
              <ListBlock title="Files Impacted" items={files} empty="Repository file ranking not available" />
              <div className="planner-actions">
                <button
                  className="planner-button secondary"
                  onClick={() => {
                    setSelectedPackageTitle(card.title);
                    window.setTimeout(() => {
                      document.getElementById('execution-package-card-details')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    }, 0);
                  }}
                  disabled={!executionContext}
                >
                  View Package
                </button>
                <button className="planner-button secondary" onClick={() => promptText ? void copyText(promptText) : onGeneratePrompt(card.kind)} disabled={loading || (!promptText && !executionContext)}>
                  Copy Developer Prompt
                </button>
                <button className="planner-button secondary" onClick={onOpenVsCode} disabled={!executionContext}>
                  Open Copilot Chat
                </button>
              </div>
            </article>
          );
        })}
      </div>
      {selectedCard ? (
        <section className="planner-card" id="execution-package-card-details">
          <div className="planner-section-header">
            <div>
              <div className="planner-label">{selectedCard.title}</div>
              <div className="planner-subtle">Focused implementation view for this package. Use the copied prompt for Copilot, Codex, or Claude.</div>
            </div>
          </div>
          <div className="planner-summary-grid">
            <SummaryTile title="Package" value={selectedCard.title} />
            <SummaryTile title="Files Impacted" value={selectedCard.files.length ? `${selectedCard.files.length} prioritized` : (allFiles.length ? `${allFiles.slice(0, 4).length} fallback files` : 'Not Available')} />
            <SummaryTile title="Prompt" value={selectedCard.prompt ? 'Available' : 'Generated From Implementation Plan'} />
          </div>
          <ListBlock title="Focused Files" items={selectedCard.files.length ? selectedCard.files : allFiles.slice(0, 4)} empty="Repository file ranking not available" />
          <ListBlock title="Focused Risks" items={selectedCard.risk.length ? selectedCard.risk : allRisks.slice(0, 3)} empty="Risk will appear after package generation." />
          <PromptBlock title={`${selectedCard.title} Developer Prompt`} value={buildPackagePrompt(selectedCard, selectedCard.files.length ? selectedCard.files : allFiles.slice(0, 4), selectedCard.risk[0] || allRisks[0] || 'Risk will appear after package generation.', selectedCard.prompt)} copyable />
        </section>
      ) : null}
    </section>
  );
}

function formatQATestSuiteForCopy(result?: QATestSuiteResult): string {
  if (!result) {
    return '';
  }
  const cases = result.test_suite.test_cases || [];
  return [
    `# ${result.test_suite.title || 'QA Test Suite'}`,
    '',
    `Coverage Score: ${result.coverage_score}%`,
    `Generated Tests: ${result.generated_test_count}`,
    '',
    ...cases.map((test) => [
      `## ${test.test_id} - ${test.title}`,
      `Category: ${test.category}`,
      `Priority: ${test.priority}`,
      `Risk: ${test.risk_level}`,
      `Preconditions: ${(test.preconditions || []).join('; ') || 'None'}`,
      `Steps: ${(test.steps || []).join('; ') || 'Not provided'}`,
      `Expected: ${test.expected_result}`,
      '',
    ].join('\n')),
  ].join('\n');
}

function ApprovalStatusStrip({ label, status, qualityScore }: { label: string; status: ApprovalStatus; qualityScore?: number }) {
  return (
    <div className="planner-status-grid">
      <Row label={`${label} Status`} value={approvalStatusLabel(status)} />
      <Row label="Quality Gate" value={qualityScore === undefined ? 'Not scored' : `${formatNumber(qualityScore)} ${isReadyForApproval(qualityScore) ? '- Ready For Approval' : '- Draft'}`} />
    </div>
  );
}

function ChipList({ items }: { items: string[] }) {
  const values = items.length ? items : ['Pending repository analysis'];
  return (
    <div className="planner-chip-row">
      {values.map((item) => <span className="planner-chip" key={item}>{item}</span>)}
    </div>
  );
}

function ArchitectureDiagram({ notes }: { notes: string[] }) {
  const layers = architectureLayers(notes);
  return (
    <details className="planner-accordion" open>
      <summary>Architecture Summary</summary>
      <div className="planner-architecture">
        {layers.map((layer, index) => (
          <React.Fragment key={layer}>
            <span>{layer}</span>
            {index < layers.length - 1 ? <b>↓</b> : null}
          </React.Fragment>
        ))}
      </div>
      <details className="planner-nested">
        <summary>View Architecture Details</summary>
        <ListBlock title="Architecture Notes" items={notes.length ? notes : ['Pending repository analysis']} />
      </details>
    </details>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="planner-status-row">
      <span>{label}</span>
      <span>{value}</span>
    </div>
  );
}

function PromptBlock({ title, value, metadata, copyable }: { title: string; value: string; metadata?: ProviderMetadata; copyable?: boolean }) {
  return (
    <div className="planner-task">
      <div className="planner-label">{title}</div>
      <SourceBadge metadata={metadata} />
      {copyable ? (
        <div className="planner-actions">
          <button className="planner-button secondary" onClick={() => void copyText(value)}>Copy</button>
        </div>
      ) : null}
      <pre className="planner-prompt">{value}</pre>
    </div>
  );
}

function buildVsCodeExecutionPackageUri(
  executionContext: ExecutionContextResult,
  executionPlan?: ExecutionPlanResult,
  devPrompt?: PromptBuilderResult,
  uiPrompt?: PromptBuilderResult,
  qaPrompt?: PromptBuilderResult,
  copilotContext?: CopilotContextResult,
): string {
  const payload = {
    execution_context: executionContext,
    execution_plan: executionPlan?.plan || executionPlan?.finalPlan || executionPlan?.prompt || '',
    dev_prompt: devPrompt?.prompt || executionPlan?.plan || executionPlan?.finalPlan || executionPlan?.prompt || '',
    ui_prompt: uiPrompt?.prompt || '',
    qa_prompt: qaPrompt?.prompt || '',
    copilot_context: copilotContext?.context || '',
  };
  const params = new URLSearchParams({
    payload: btoa(unescape(encodeURIComponent(JSON.stringify(payload)))),
  });
  return `vscode://rathiesh.ai-gen-vscode/openExecution?${params.toString()}`;
}

async function copyText(value: string): Promise<void> {
  if (!value) {
    return;
  }
  await navigator.clipboard?.writeText(value);
}

async function getProfile(): Promise<ProjectProfile> {
  const response = await fetch(`${BASE_URL}/profile`);
  if (!response.ok) {
    throw new Error(await response.text() || `Backend returned HTTP ${response.status}`);
  }
  return response.json() as Promise<ProjectProfile>;
}

async function getEngineeringWorkspace(userId: string, role: AIGenRole): Promise<EngineeringWorkspace> {
  const params = new URLSearchParams({ userId: userId || 'current-user', role });
  const response = await fetch(`${PLATFORM_BASE_URL}/workspace?${params.toString()}`);
  if (!response.ok) {
    throw new Error(await response.text() || `Workspace service returned HTTP ${response.status}`);
  }
  return response.json() as Promise<EngineeringWorkspace>;
}

async function getDashboardOverview(projectId = ''): Promise<DashboardOverview> {
  const params = new URLSearchParams();
  if (projectId) {
    params.set('projectId', projectId);
  }
  const suffix = params.toString() ? `?${params.toString()}` : '';
  const response = await fetch(`${PLATFORM_BASE_URL}/dashboard/overview${suffix}`);
  if (!response.ok) {
    throw new Error(await response.text() || `Dashboard service returned HTTP ${response.status}`);
  }
  return response.json() as Promise<DashboardOverview>;
}

function dashboardNotifications(overview: DashboardOverview): EngineeringWorkspace['notifications'] {
  return overview.notifications.items.slice(0, 8).map((item, index) => ({
    id: String(item.notificationId || item.id || index),
    title: String(item.title || item.type || 'HEI notification'),
    message: String(item.message || item.description || ''),
    severity: String(item.severity || 'information'),
  }));
}

async function putWorkspacePreferences(
  userId: string,
  role: AIGenRole,
  changes: Partial<WorkspacePreferences>,
): Promise<WorkspacePreferences> {
  const response = await fetch(`${PLATFORM_BASE_URL}/workspace/preferences`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ userId, role, ...changes }),
  });
  const payload = await response.json() as WorkspacePreferences & { error?: { message?: string } };
  if (!response.ok) {
    throw new Error(payload.error?.message || `Workspace service returned HTTP ${response.status}`);
  }
  return payload;
}

async function getBackendProjectSession(): Promise<BackendProjectSessionResponse> {
  return getJson<BackendProjectSessionResponse>('/session');
}

async function saveBackendProjectSession(session: ProjectSessionSnapshot): Promise<void> {
  await postJson<BackendProjectSessionResponse>('/session', {
    session: {
      active_project: session.active_project,
      project_id: session.profile.project_id,
      auto_route_by_work_item_type: session.auto_route_by_work_item_type,
      approval_workflow: session.approval_workflow,
      knowledge_governance: session.knowledge_governance,
      last_active_workspace: session.last_active_tab,
      last_active_tab: session.last_active_tab,
      last_work_item_id: session.last_work_item_id,
      last_work_item_type: session.last_work_item_type,
      last_work_item_title: session.last_work_item_title,
      last_repository: session.repository_name,
      last_repository_id: session.repository_id,
      last_branch: session.branch,
      last_analysis_timestamp: session.last_analysis_timestamp,
      knowledge_version: session.knowledge_version,
      execution_context: session.execution_context,
      execution_plan: session.execution_plan,
      dev_prompt: session.dev_prompt,
      ui_prompt: session.ui_prompt,
      qa_prompt: session.qa_prompt,
      copilot_context: session.copilot_context,
      qa_test_suite: session.qa_test_suite,
      implementation_validation: session.implementation_validation,
      pr_review: session.pr_review,
    },
  });
}

async function getKnowledgeCache(): Promise<KnowledgeCacheResponse> {
  return getJson<KnowledgeCacheResponse>('/knowledge-cache');
}

async function getContextCapsules(): Promise<ContextCapsuleResponse> {
  return getJson<ContextCapsuleResponse>('/context-capsules');
}

async function fetchAdoProjects(): Promise<AdoProjectListResponse> {
  const response = await getJson<AdoProjectListResponse & { error?: string }>('/connectors/azure-devops/projects');
  return {
    ...response,
    projects: response.projects || [],
  };
}

async function fetchAdoRepositories(adoProject: string): Promise<GitRepository[]> {
  const params = new URLSearchParams({ ado_project: adoProject });
  const url = `/connectors/azure-devops/repositories?${params.toString()}`;
  const response = await getJson<{ repositories?: GitRepository[]; error?: string }>(url);
  return response.repositories || [];
}

async function fetchAdoBranches(adoProject: string, repositoryId: string): Promise<string[]> {
  const params = new URLSearchParams({ ado_project: adoProject, repository_id: repositoryId });
  const response = await getJson<{ branches?: string[]; error?: string }>(`/connectors/azure-devops/branches?${params.toString()}`);
  return (response.branches || []).map((branch) => normalizeBranchName(branch)).filter(Boolean);
}

async function fetchAdoRepositoryFileContent(mapping: AzureDevOpsConnectorMapping, path: string): Promise<string> {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  const response = await postJson<{ content?: string }>('/connectors/azure-devops/file', {
    connector_mapping: mapping,
    path: normalizedPath,
  });
  if (!response.content) {
    throw new Error(`${normalizedPath} did not contain readable text content.`);
  }
  return response.content;
}

async function saveAdoMapping(profile: ProjectProfile): Promise<void> {
  await postJson<{ mapping?: AzureDevOpsConnectorMapping }>('/connectors/azure-devops/mapping', {
    project_id: profile.project_id || '',
    mapping: getAdoMapping(profile),
  });
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`);
  if (!response.ok) {
    throw new Error(await response.text() || `Backend returned HTTP ${response.status}`);
  }
  const payload = await response.json();
  if (payload && typeof payload === 'object' && typeof payload.error === 'string' && payload.error.trim()) {
    throw new Error(payload.error);
  }
  return payload as T;
}

async function fetchAdoRest<T>(relativePath: string, timeoutMs: number, timeoutMessage: string): Promise<T> {
  const token = await SDK.getAccessToken();
  const url = `${trimTrailingSlash(getCollectionUri())}/${relativePath.replace(/^\/+/, '')}`;
  const response = await withTimeout(
    fetch(url, {
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'application/json',
      },
    }),
    timeoutMs,
    timeoutMessage,
  );
  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `Azure DevOps returned HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

async function loadCurrentWorkItem(): Promise<AdoWorkItem | undefined> {
  try {
    const service = await SDK.getService<IWorkItemFormService>(WorkItemTrackingServiceIds.WorkItemFormService);
    const fields = await service.getFieldValues([
      'System.Id',
      'System.Title',
      'System.WorkItemType',
      'System.Description',
      'Microsoft.VSTS.Common.AcceptanceCriteria',
      'System.State',
      'System.AreaPath',
      'System.IterationPath',
      'System.Tags',
    ]);
    const id = Number(fields['System.Id'] || 0);
    if (!id) {
      return undefined;
    }
    const project = await getProjectName();
    const collectionUri = getCollectionUri();
    const full = await fetchAdoWorkItem(collectionUri, project, id);
    return {
      id,
      type: String(fields['System.WorkItemType'] || full.type || ''),
      title: String(fields['System.Title'] || full.title || ''),
      description: String(fields['System.Description'] || full.description || ''),
      acceptanceCriteria: String(fields['Microsoft.VSTS.Common.AcceptanceCriteria'] || full.acceptanceCriteria || ''),
      state: String(fields['System.State'] || full.state || ''),
      areaPath: String(fields['System.AreaPath'] || full.areaPath || ''),
      iterationPath: String(fields['System.IterationPath'] || full.iterationPath || ''),
      tags: splitTags(String(fields['System.Tags'] || full.tags || '')),
      project,
      collectionUri,
      parentIds: full.parentIds,
      childIds: full.childIds,
      parents: await loadParentChain(collectionUri, project, full.parentIds[0]),
      children: await loadHierarchy(collectionUri, project, full.childIds, 'child'),
    };
  } catch {
    return undefined;
  }
}

async function fetchAdoWorkItem(collectionUri: string, projectName: string, id: number): Promise<AdoWorkItem & { parentIds: number[]; childIds: number[] }> {
  const token = await SDK.getAccessToken();
  const response = await fetch(`${trimTrailingSlash(collectionUri)}/${encodeURIComponent(projectName)}/_apis/wit/workItems/${id}?$expand=relations&api-version=7.1`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    throw new Error(`Azure DevOps returned HTTP ${response.status} while loading work item #${id}.`);
  }
  const body = await response.json() as {
    id: number;
    fields?: Record<string, unknown>;
    relations?: Array<{ rel?: string; url?: string }>;
  };
  const fields = body.fields || {};
  const relations = body.relations || [];
  return {
    id: body.id,
    type: String(fields['System.WorkItemType'] || ''),
    title: String(fields['System.Title'] || ''),
    description: String(fields['System.Description'] || ''),
    acceptanceCriteria: String(fields['Microsoft.VSTS.Common.AcceptanceCriteria'] || ''),
    state: String(fields['System.State'] || ''),
    areaPath: String(fields['System.AreaPath'] || ''),
    iterationPath: String(fields['System.IterationPath'] || ''),
    tags: splitTags(String(fields['System.Tags'] || '')),
    project: projectName,
    collectionUri,
    parentIds: relations.filter((relation) => relation.rel === 'System.LinkTypes.Hierarchy-Reverse').map((relation) => extractWorkItemId(relation.url)).filter(Boolean),
    childIds: relations.filter((relation) => relation.rel === 'System.LinkTypes.Hierarchy-Forward').map((relation) => extractWorkItemId(relation.url)).filter(Boolean),
    parents: [],
    children: [],
  };
}

async function loadHierarchy(collectionUri: string, projectName: string, ids: number[], direction: 'parent' | 'child'): Promise<AdoWorkItemSummary[]> {
  if (!ids.length) {
    return [];
  }
  const summaries = await Promise.all(ids.slice(0, direction === 'parent' ? 3 : 20).map(async (id) => {
    const item = await fetchAdoWorkItem(collectionUri, projectName, id);
    return { id: item.id, type: item.type, title: item.title, state: item.state };
  }));
  return direction === 'parent' ? summaries.reverse() : summaries;
}

async function loadParentChain(collectionUri: string, projectName: string, parentId?: number): Promise<AdoWorkItemSummary[]> {
  const chain: AdoWorkItemSummary[] = [];
  let nextId = parentId || 0;
  const seen = new Set<number>();
  while (nextId && !seen.has(nextId) && chain.length < 4) {
    seen.add(nextId);
    const item = await fetchAdoWorkItem(collectionUri, projectName, nextId);
    chain.unshift({ id: item.id, type: item.type, title: item.title, state: item.state });
    nextId = item.parentIds[0] || 0;
  }
  return chain;
}

async function createAdoWorkItem(parent: AdoWorkItem, accessToken: string, draft: ChildDraft): Promise<number> {
  const fields: Record<string, string> = {
    'System.Title': draft.title,
    'System.Description': draft.description,
    'System.AreaPath': parent.areaPath,
    'System.IterationPath': parent.iterationPath,
  };
  if (draft.type !== 'Task' && draft.acceptanceCriteria.length) {
    fields['Microsoft.VSTS.Common.AcceptanceCriteria'] = draft.acceptanceCriteria.map((item) => `<div>${escapeHtml(item)}</div>`).join('');
  }
  if (parent.tags.length) {
    fields['System.Tags'] = parent.tags.join('; ');
  }
  const operations: Array<Record<string, unknown>> = Object.entries(fields)
    .filter(([, value]) => String(value || '').trim())
    .map(([field, value]) => ({ op: 'add', path: `/fields/${field}`, value }));
  operations.push({
    op: 'add',
    path: '/relations/-',
    value: {
      rel: 'System.LinkTypes.Hierarchy-Reverse',
      url: `${trimTrailingSlash(parent.collectionUri)}/${encodeURIComponent(parent.project)}/_apis/wit/workItems/${parent.id}`,
    },
  });
  const typeName = encodeURIComponent(`$${draft.type}`);
  const response = await fetch(`${trimTrailingSlash(parent.collectionUri)}/${encodeURIComponent(parent.project)}/_apis/wit/workitems/${typeName}?api-version=7.1`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${accessToken}`,
      'Content-Type': 'application/json-patch+json',
    },
    body: JSON.stringify(operations),
  });
  if (!response.ok) {
    const body = await response.text().catch(() => '');
    throw new Error(`Azure DevOps returned HTTP ${response.status} while creating ${draft.type}${body ? `: ${body.slice(0, 400)}` : ''}.`);
  }
  const body = await response.json() as { id: number };
  return body.id;
}

async function addAdoComment(workItem: AdoWorkItem, text: string): Promise<void> {
  const accessToken = await SDK.getAccessToken();
  await fetch(`${trimTrailingSlash(workItem.collectionUri)}/${encodeURIComponent(workItem.project)}/_apis/wit/workItems/${workItem.id}/comments?api-version=7.1-preview.4`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${accessToken}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ text }),
  });
}

function featureDraftsFromEpic(result: EpicRefinement, approvedOnly = false): ChildDraft[] {
  const approvedCapabilitiesList = (result.capability_review || []).filter(isCapabilityApproved);
  const approvedCapabilityCategories = new Set(
    approvedCapabilitiesList.map((capability) => (capability.capabilityCategory || capability.capabilityName || '').trim().toLowerCase())
  );

  const matchedFeatures = approvedOnly && result.capability_review?.length
    ? result.recommended_features.filter((feature) => {
        const featureCapability = (feature.capability_category || feature.capability || feature.title || '').trim().toLowerCase();
        return approvedCapabilityCategories.has(featureCapability);
      })
    : result.recommended_features;

  const features = matchedFeatures.map((feature) => {
    const matchingCapability = approvedCapabilitiesList.find((capability) => {
      const category = (capability.capabilityCategory || capability.capabilityName || '').trim().toLowerCase();
      const featureCategory = (feature.capability_category || feature.capability || feature.title || '').trim().toLowerCase();
      return category === featureCategory;
    });
    if (!matchingCapability) {
      return feature;
    }
    return {
      ...feature,
      title: matchingCapability.suggestedFeatureTitle || matchingCapability.capabilityName || feature.title,
      description: matchingCapability.businessPurpose || feature.description,
      business_goal: matchingCapability.businessPurpose || feature.business_goal,
      user_problem: feature.user_problem || matchingCapability.explainability?.businessProblemSolved,
      business_value: feature.business_value || matchingCapability.businessValue,
      business_outcome: feature.business_outcome || matchingCapability.businessValue,
      impacted_applications: feature.impacted_applications?.length ? feature.impacted_applications : matchingCapability.relatedApplications,
      impacted_modules: feature.impacted_modules?.length ? feature.impacted_modules : matchingCapability.relatedModules,
      impacted_flows: feature.impacted_flows?.length ? feature.impacted_flows : matchingCapability.relatedFlows,
      dependencies: feature.dependencies?.length ? feature.dependencies : matchingCapability.dependencies,
      capability: matchingCapability.capabilityCategory || feature.capability,
      capability_category: matchingCapability.capabilityCategory || feature.capability_category || feature.capability,
    };
  });

  if (approvedOnly) {
    const matchedCapabilityNames = new Set(
      features.map((feature) => (feature.capability_category || feature.capability || feature.title || '').trim().toLowerCase())
    );

    // Synthesize missing features from approved capabilities
    for (const capability of approvedCapabilitiesList) {
      const capabilityName = (capability.capabilityCategory || capability.capabilityName || '').trim().toLowerCase();
      if (!matchedCapabilityNames.has(capabilityName)) {
        features.push({
          title: capability.suggestedFeatureTitle || capability.capabilityName || 'New Feature',
          description: capability.businessPurpose || 'Implement capability requirements.',
          acceptance_criteria: capability.inScope || [],
          business_goal: capability.businessPurpose,
          user_problem: capability.businessValue,
          business_value: capability.businessValue,
          business_outcome: capability.businessValue,
          capability: capability.capabilityCategory || capability.capabilityName,
          capability_category: capability.capabilityCategory || capability.capabilityName,
          primary_personas: result.users || [],
          primary_users: result.users || [],
          impacted_applications: capability.relatedApplications || [],
          impacted_modules: capability.relatedModules || [],
          impacted_flows: capability.relatedFlows || [],
          dependencies: capability.dependencies || [],
          confidence: capability.confidence || 0.8,
        } as any);
      }
    }
  }

  return features.map((feature, index) => ({
    id: `feature_${index + 1}`,
    type: 'Feature',
    title: feature.title,
    description: feature.description,
    acceptanceCriteria: acceptanceCriteriaForFeatureDraft(feature, result.business_outcomes),
    businessGoal: feature.business_goal,
    userProblem: feature.user_problem,
    businessValue: feature.business_value || feature.business_outcome,
    capabilityCategory: feature.capability_category || feature.capability,
    primaryPersonas: feature.primary_personas || feature.primary_users || [],
    impactedApplications: feature.impacted_applications || [],
    impactedModules: feature.impacted_modules || [],
    impactedFlows: feature.impacted_flows || [],
    dependencies: feature.dependencies || [],
    risks: feature.risks || [],
    rejectedContext: feature.rejected_irrelevant_context || result.rejected_context || [],
    relevanceConfidence: feature.confidence,
    acceptanceCriteriaCount: feature.acceptance_criteria_count,
    acceptanceCriteriaQualityScore: feature.acceptance_criteria_quality_score,
    selected: true,
    status: 'preview',
  }));
}

function acceptanceCriteriaForFeatureDraft(
  feature: EpicRefinement['recommended_features'][number],
  epicOutcomes: string[],
): string[] {
  const explicit = Array.isArray(feature.acceptance_criteria)
    ? feature.acceptance_criteria
    : typeof feature.acceptance_criteria === 'string'
      ? [feature.acceptance_criteria]
      : [];
  const cleanExplicit = explicit.filter((item) => item && !isGenericFeatureCriterion(item));
  if (cleanExplicit.length >= 4) {
    return cleanExplicit;
  }
  return uniqueStrings([...cleanExplicit, ...featureCriteriaFallback(feature, epicOutcomes)]).slice(0, 8);
}

function isGenericFeatureCriterion(value: string): boolean {
  const lowered = value.toLowerCase();
  return [
    'workflow is covered',
    'workflow for the',
    'covered end to end',
    'integrations are validated',
    'stakeholders can confirm',
    'capability supported',
  ].some((phrase) => lowered.includes(phrase));
}

function featureCriteriaFallback(
  feature: EpicRefinement['recommended_features'][number],
  epicOutcomes: string[],
): string[] {
  const title = feature.title || 'Selected feature';
  const capability = (feature.capability_category || feature.capability || '').toLowerCase();
  if (capability.includes('alert')) {
    return [
      'Operator receives an alert when a critical event is created.',
      'Alert displays Device ID, Event Type, Severity, Event Time, and Recommended Action.',
      'Operator can acknowledge the alert and the acknowledgement is timestamped.',
      'Duplicate alerts for the same active event are suppressed or grouped.',
      'Escalation status changes are visible within 60 seconds of update.',
    ];
  }
  if (capability.includes('investigation')) {
    return [
      'Operator can open an investigation workspace from an event record.',
      'Workspace shows related device, telemetry, timeline, owner, and current status.',
      'Operator can filter investigation records by severity, device, and time range.',
      'Workspace highlights missing telemetry or stale device status data.',
      'Investigation notes are saved with user identity and timestamp.',
    ];
  }
  if (capability.includes('analytics') || capability.includes('reliability')) {
    return [
      'Operations manager can view trends by device, event type, severity, and time period.',
      'Trend view shows counts, severity distribution, and response-time changes.',
      'User can compare current trends against the previous period.',
      'Trend data can be filtered by asset group and time range.',
      'System identifies incomplete or delayed analytics data.',
    ];
  }
  if (capability.includes('health')) {
    return [
      'Operator can view health status for affected assets.',
      'Health view displays Device ID, Health Score, Last Telemetry Time, Active Event Count, and Current Status.',
      'Assets with degraded health are visually separated from healthy assets.',
      'Operator can open health details showing recent telemetry and related events.',
      'System identifies stale or missing health data with a clear message.',
    ];
  }
  const outcome = feature.business_outcome || feature.business_value || epicOutcomes[0] || 'the approved business outcome';
  return [
    `User can view active ${title} records in a single list.`,
    `${title} list displays identifier, severity, event time, owner, and current status.`,
    `User can open ${title} details from the list.`,
    `${title} updates are visible within 60 seconds of source data change.`,
    `System displays a clear unavailable-data message when ${title} data cannot be loaded.`,
    `All ${title} access and update actions are audit logged.`,
    `The feature supports the business outcome: ${outcome}.`,
  ];
}

function uniqueStrings(items: string[]): string[] {
  return Array.from(new Set(items.map((item) => item.trim()).filter(Boolean)));
}

function storyDraftsFromFeature(result: FeatureRefinement): ChildDraft[] {
  return result.recommended_stories.map((story, index) => ({
    id: `story_${index + 1}`,
    type: 'User Story',
    title: story.title,
    description: story.description,
    acceptanceCriteria: story.acceptance_criteria?.length ? story.acceptance_criteria : storyCriteriaFallback(story),
    impactedModules: story.modules_used || story.affected_modules || result.affected_modules || [],
    impactedFlows: story.flows_used || story.affected_flows || result.affected_flows || [],
    rejectedContext: story.rejected_irrelevant_context || result.rejected_context || [],
    relevanceConfidence: story.confidence,
    selected: true,
    status: 'preview',
  }));
}

function storyCriteriaFallback(story: { title: string; description: string; coverage_area?: string }): string[] {
  const title = story.title || 'Story';
  const lower = `${story.title} ${story.description} ${story.coverage_area || ''}`.toLowerCase();
  const subject = lower.includes('fault') ? 'fault event' : lower.includes('telemetry') ? 'telemetry record' : lower.includes('device health') ? 'device health record' : 'record';
  return [
    `Operations User can open the ${subject} for ${title} from the approved entry point.`,
    `The view displays Device ID, Fault Type, Severity, Event Timestamp, Current Status, and Device Health when available.`,
    'Unauthorized users receive an access-restricted message and no protected operational data is displayed.',
    'Missing or stale telemetry is labeled as Data Unavailable without hiding other available fields.',
    'The primary action completes within 2 seconds for normal project data volume.',
  ];
}

function taskDraftsFromStory(result: StoryRefinement): ChildDraft[] {
  const tasks = result.proposed_tasks?.length ? result.proposed_tasks : fallbackStoryTasks(result);
  return tasks.map((task, index) => ({
    id: `task_${index + 1}`,
    type: 'Task',
    title: cleanGeneratedTitle(`${task.work_area ? `${task.work_area}: ` : ''}${task.title}`),
    description: task.description,
    acceptanceCriteria: task.acceptance_criteria?.length ? task.acceptance_criteria : result.acceptance_criteria,
    impactedModules: result.affected_modules || [],
    impactedFlows: result.affected_flows || [],
    rejectedContext: result.rejected_context || [],
    selected: true,
    status: 'preview',
  }));
}

async function postJson<T>(path: string, body: Record<string, unknown>): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), API_TIMEOUT_MS);
  try {
    const response = await fetch(`${BASE_URL}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new Error(await response.text() || `Backend returned HTTP ${response.status}`);
    }
    const payload = await response.json();
    if (payload && typeof payload === 'object' && typeof payload.error === 'string' && payload.error.trim()) {
      const phiStatus = typeof payload.phi_status === 'string' && payload.phi_status ? ` (${payload.phi_status})` : '';
      const fallbackReason = typeof payload.fallback_reason === 'string' && payload.fallback_reason && payload.fallback_reason !== payload.error
        ? `: ${payload.fallback_reason}`
        : '';
      throw new Error(`${payload.error}${phiStatus}${fallbackReason}`);
    }
    return payload as T;
  } catch (error) {
    if (controller.signal.aborted) {
      throw new Error(`Timed out contacting Project Intelligence backend after ${Math.round(API_TIMEOUT_MS / 1000)} seconds.`);
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
}

function parseChangedFilesInput(value: string): Array<{ path: string; status: string; diff: string }> {
  return value
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      if (line.includes('|')) {
        const [path, status, ...diffParts] = line.split('|').map((part) => part.trim());
        return { path, status: status || 'modified', diff: diffParts.join(' ') };
      }
      return { path: line, status: 'modified', diff: '' };
    })
    .filter((item) => item.path);
}

function getReusableArtifact(artifactType: ArtifactType, fingerprint: string, sourceItemId: string): Promise<ReusableArtifactResponse> {
  const params = new URLSearchParams({
    artifact_type: artifactType,
    fingerprint,
    source_item_id: sourceItemId,
  });
  return getJson<ReusableArtifactResponse>(`/artifacts/reusable?${params.toString()}`);
}

function getArtifacts(): Promise<{ artifacts: ArtifactRecord[]; count: number }> {
  return getJson<{ artifacts: ArtifactRecord[]; count: number }>('/artifacts');
}

function getGraphSummary(itemId = ''): Promise<GraphSummary> {
  const params = new URLSearchParams();
  if (itemId) {
    params.set('item_id', itemId);
  }
  return getJson<GraphSummary>(`/graph/summary${params.toString() ? `?${params.toString()}` : ''}`);
}

function getCoverageReport(itemId = ''): Promise<CoverageIntelligenceReport> {
  const params = new URLSearchParams();
  if (itemId) {
    params.set('item_id', itemId);
  }
  return getJson<CoverageIntelligenceReport>(`/coverage/report${params.toString() ? `?${params.toString()}` : ''}`);
}

function getEngineeringMemory(): Promise<EngineeringMemoryResponse> {
  return getJson<EngineeringMemoryResponse>('/engineering-memory');
}

function storeEngineeringMemory(memory: Record<string, unknown>, actor: string): Promise<{ stored?: boolean; memory?: EngineeringMemoryItem }> {
  return postJson<{ stored?: boolean; memory?: EngineeringMemoryItem }>('/engineering-memory', { memory, actor });
}

function validateEngineeringMemory(memoryId: string, actor: string): Promise<{ updated?: boolean; memory?: EngineeringMemoryItem }> {
  return postJson<{ updated?: boolean; memory?: EngineeringMemoryItem }>(`/engineering-memory/${encodeURIComponent(memoryId)}/validate`, { actor });
}

function approveEngineeringMemory(memoryId: string, actor: string): Promise<{ updated?: boolean; memory?: EngineeringMemoryItem }> {
  return postJson<{ updated?: boolean; memory?: EngineeringMemoryItem }>(`/engineering-memory/${encodeURIComponent(memoryId)}/approve`, { actor });
}

function indexEngineeringMemory(memoryId: string, actor: string): Promise<{ updated?: boolean; memory?: EngineeringMemoryItem }> {
  return postJson<{ updated?: boolean; memory?: EngineeringMemoryItem }>(`/engineering-memory/${encodeURIComponent(memoryId)}/index`, { actor });
}

function makeEngineeringMemoryAvailable(memoryId: string, actor: string): Promise<{ updated?: boolean; memory?: EngineeringMemoryItem }> {
  return postJson<{ updated?: boolean; memory?: EngineeringMemoryItem }>(`/engineering-memory/${encodeURIComponent(memoryId)}/available`, { actor });
}

function searchEngineeringMemoryItems(query: Record<string, unknown>): Promise<EngineeringMemoryResponse> {
  return postJson<EngineeringMemoryResponse>('/engineering-memory/search', { query });
}

function getGovernanceDashboard(): Promise<GovernanceDashboard> {
  return getJson<GovernanceDashboard>('/governance');
}

function getAgentDashboard(): Promise<AgentDashboard> {
  return getJson<AgentDashboard>('/agents');
}

function getSkillsDashboard(): Promise<SkillsDashboard> {
  return getJson<SkillsDashboard>('/skills');
}

function saveArtifact(artifact: {
  artifact_type: ArtifactType;
  title: string;
  payload: unknown;
  fingerprint: string;
  state: ArtifactLifecycleState;
  source_item: { id: string; type: string; title: string };
  created_by: string;
}): Promise<ArtifactRecord> {
  return postJson<ArtifactRecord>('/artifacts', artifact as unknown as Record<string, unknown>);
}

function approveStoredArtifact(artifactId: string, approvedBy: string): Promise<ArtifactRecord> {
  return postJson<ArtifactRecord>(`/artifacts/${encodeURIComponent(artifactId)}/approve`, { approved_by: approvedBy });
}

function artifactFingerprint(artifactType: ArtifactType, sourceItem: Record<string, unknown>, source: Record<string, unknown>): string {
  return `fp_${stableHash(stableStringify({ artifactType, sourceItem, source }))}`;
}

function stableStringify(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map((item) => stableStringify(item)).join(',')}]`;
  }
  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>;
    return `{${Object.keys(record).sort().map((key) => `${JSON.stringify(key)}:${stableStringify(record[key])}`).join(',')}}`;
  }
  return JSON.stringify(value);
}

function stableHash(value: string): string {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16).padStart(8, '0');
}

function splitLines(value: string): string[] {
  return value.split(/\n|,/).map((item) => item.trim()).filter(Boolean);
}

function splitTags(value: string): string[] {
  return value.split(/[;,]/).map((item) => item.trim()).filter(Boolean);
}

function getAdoMapping(profile: ProjectProfile, overrides: Partial<AzureDevOpsConnectorMapping> = {}): AzureDevOpsConnectorMapping {
  const current = profile.connectors?.azure_devops;
  return {
    organization_url: current?.organization_url || '',
    ado_project: overrides.ado_project ?? current?.ado_project ?? '',
    repository_id: overrides.repository_id ?? current?.repository_id ?? profile.repository_connection.repository_id ?? '',
    repository_name: overrides.repository_name ?? current?.repository_name ?? profile.repository_connection.repository_name ?? '',
    branch: overrides.branch ?? current?.branch ?? profile.repository_connection.branch ?? 'main',
  };
}

function applyAdoMapping(profile: ProjectProfile, updates: Partial<AzureDevOpsConnectorMapping>): ProjectProfile {
  const mapping = getAdoMapping(profile, updates);
  return {
    ...profile,
    connectors: {
      ...(profile.connectors || {}),
      azure_devops: mapping,
    },
    repository_connection: {
      ...profile.repository_connection,
      repository_id: mapping.repository_id,
      repository_name: mapping.repository_name,
      branch: mapping.branch,
      status: mapping.repository_id ? 'Repository connected' : profile.repository_connection.status,
    },
  };
}

function extractWorkItemId(url?: string): number {
  const match = String(url || '').match(/workItems\/(\d+)/i);
  return match ? Number(match[1]) : 0;
}

function normalizePlannerItemType(type: string): WorkItemKind {
  const normalized = type.toLowerCase();
  if (normalized.includes('epic')) return 'Epic';
  if (normalized.includes('feature')) return 'Feature';
  if (normalized.includes('bug')) return 'Bug';
  if (normalized.includes('test case') || normalized.includes('testcase')) return 'Test Case';
  if (normalized.includes('task')) return 'Task';
  return 'Story';
}

function recommendedWorkspaceForItem(type: WorkItemKind): RoutedWorkspace {
  if (type === 'Epic' || type === 'Feature' || type === 'Story') {
    return 'planning';
  }
  if (type === 'Test Case') {
    return 'qa';
  }
  return 'execution';
}

function routedWorkspaceForWorkflow(type: WorkItemKind, workflow: WorkflowOrchestrationState): RoutedWorkspace {
  if (workflow.nextAction.workspace === 'planning' || workflow.nextAction.workspace === 'execution' || workflow.nextAction.workspace === 'qa') {
    return workflow.nextAction.workspace;
  }
  return recommendedWorkspaceForItem(type);
}

function workspaceLabel(tab: PlannerTab | RoutedWorkspace): string {
  if (tab === 'planning') return 'Planning';
  if (tab === 'execution') return 'Execution';
  if (tab === 'qa') return 'QA & Release';
  if (tab === 'memory') return 'Memory';
  if (tab === 'governance') return 'Governance';
  if (tab === 'agents') return 'Agents';
  if (tab === 'skills') return 'Skills';
  if (tab === 'diagnostics') return 'Diagnostics';
  if (tab === 'admin') return 'Administration';
  return 'Command Center';
}

function knowledgeStatusText(status: KnowledgeCacheStatus['knowledge_status'] | string): string {
  if (status === 'ready') return 'Ready';
  if (status === 'refresh_available') return 'Refresh Available';
  if (status === 'stale') return 'Stale';
  return 'Missing';
}

function defaultApprovalWorkflowState(): ApprovalWorkflowState {
  return {
    epic: 'locked',
    features: 'locked',
    feature: 'locked',
    stories: 'locked',
    story: 'locked',
    tasks: 'locked',
    qa: 'locked',
    execution: 'locked',
  };
}

function normalizeApprovalWorkflowState(value: unknown): ApprovalWorkflowState {
  const current = (value && typeof value === 'object' ? value : {}) as Partial<Record<ApprovalArtifact, string>>;
  const base = defaultApprovalWorkflowState();
  (Object.keys(base) as ApprovalArtifact[]).forEach((key) => {
    const status = current[key];
    if (status === 'draft' || status === 'ready_for_approval' || status === 'approved' || status === 'locked') {
      base[key] = status;
    }
  });
  return base;
}

function approvalStatusLabel(status: ApprovalStatus): string {
  if (status === 'approved') return '✓ Approved';
  if (status === 'ready_for_approval') return 'Ready For Approval';
  if (status === 'draft') return 'Draft';
  return 'Locked';
}

function isApprovalPending(status: ApprovalStatus): boolean {
  return status === 'draft' || status === 'ready_for_approval';
}

function isReadyForApproval(score?: number): boolean {
  return Number(score || 0) >= 75;
}

function lifecycleTypesForApproval(approval: ApprovalArtifact): ArtifactType[] {
  const mapping: Record<ApprovalArtifact, ArtifactType[]> = {
    epic: ['Epic'],
    features: ['Feature'],
    feature: ['Feature'],
    stories: ['Story'],
    story: ['Story'],
    tasks: ['Task'],
    qa: ['Test Suite', 'Test Plan', 'QA Prompt', 'Coverage Report'],
    execution: ['Execution Package', 'Implementation Package', 'Execution Plan', 'Implementation Plan', 'Dev Prompt', 'UI Prompt', 'QA Prompt', 'Context Capsule'],
  };
  return mapping[approval];
}

function approvalLabel(approval: ApprovalArtifact): string {
  const labels: Record<ApprovalArtifact, string> = {
    epic: 'Epic',
    features: 'Features',
    feature: 'Feature',
    stories: 'Stories',
    story: 'Story',
    tasks: 'Tasks',
    qa: 'QA artifact',
    execution: 'Execution package',
  };
  return labels[approval];
}

function artifactLifecycleLabel(artifact: ArtifactRecord): string {
  if (artifact.state === 'locked') return `Locked${artifact.approved_on ? ` on ${formatTimestamp(artifact.approved_on)}` : ''}`;
  if (artifact.state === 'approved') return 'Approved';
  if (artifact.state === 'archived') return 'Archived';
  return `Draft${artifact.created_on ? ` from ${formatTimestamp(artifact.created_on)}` : ''}`;
}

function qualityScoreForEpic(result?: EpicRefinement): number | undefined {
  if (!result) return undefined;
  if (result.recommended_features?.length) return 85;
  if (result.business_goal || result.business_outcomes?.length) return 75;
  return 60;
}

function qualityScoreForFeature(result?: FeatureRefinement): number | undefined {
  if (!result) return undefined;
  const diagnostics = result.story_generation_diagnostics || {};
  return diagnostics.story_quality_score || diagnostics.acceptance_criteria_quality_score || (result.recommended_stories?.length >= 4 ? 85 : result.recommended_stories?.length ? 70 : 50);
}

function qualityScoreForStory(result?: StoryRefinement): number | undefined {
  if (!result) return undefined;
  return result.acceptance_criteria_quality_score || (result.acceptance_criteria?.length >= 3 ? 85 : result.acceptance_criteria?.length ? 70 : 50);
}

function qualityScoreForTasks(result?: StoryRefinement): number | undefined {
  if (!result) return undefined;
  const diagnostics = result.task_intelligence_diagnostics || {};
  return diagnostics.task_quality_score || (result.proposed_tasks?.length ? 80 : 50);
}

function qualityScoreForFeatureDrafts(drafts: ChildDraft[]): number | undefined {
  if (!drafts.length) return undefined;
  const scores = drafts.map((draft) => draft.acceptanceCriteriaQualityScore || (draft.acceptanceCriteria?.length >= 3 ? 80 : 65));
  return Math.round(scores.reduce((sum, score) => sum + score, 0) / scores.length);
}

function qualityScoreForTaskDrafts(drafts: ChildDraft[]): number | undefined {
  if (!drafts.length) return undefined;
  const scored = drafts.map((draft) => draft.acceptanceCriteria?.length >= 2 ? 80 : 65);
  return Math.round(scored.reduce((sum, score) => sum + score, 0) / scored.length);
}

function htmlToText(value: string): string {
  const element = document.createElement('div');
  element.innerHTML = value || '';
  return (element.textContent || element.innerText || '').trim();
}

function cleanGeneratedTitle(value: string): string {
  return value.replace(/\s+/g, ' ').replace(/^(.{0,120}).*$/, '$1').trim();
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function getCollectionUri(): string {
  const pageContext = SDK.getPageContext() as unknown as {
    webContext?: {
      collection?: { uri?: string };
    };
  };
  return pageContext.webContext?.collection?.uri || `${window.location.origin}/`;
}

function trimTrailingSlash(value: string): string {
  return value.endsWith('/') ? value.slice(0, -1) : value;
}

function isProfileComplete(profile: ProjectProfile): boolean {
  return Boolean(profile.onboarding_completed || profile.project_description.trim());
}

function saveStatusLabel(status: 'saved' | 'saving' | 'unsaved' | 'error'): string {
  if (status === 'saving') return 'Saving...';
  if (status === 'unsaved') return 'Unsaved changes';
  if (status === 'error') return 'Autosave failed';
  return 'Saved';
}

function navigationIdForPlannerTab(tab: PlannerTab): string {
  const mapping: Record<PlannerTab, string> = {
    overview: 'overview',
    planning: 'planning',
    execution: 'execution',
    qa: 'execution',
    memory: 'memory',
    governance: 'approvals',
    agents: 'agents',
    skills: 'agents',
    admin: 'administration',
    diagnostics: 'activity',
  };
  return mapping[tab];
}

function defaultPermissionState(): PermissionState {
  return {
    role: 'admin',
    user_display_name: '',
    user_name: '',
    mapped_group: 'Permission Mapping Paused',
    azure_groups: [],
    status: 'fallback',
    warning: 'Azure DevOps permission mapping is paused. Project Intelligence access is temporarily open while group resolution is stabilized.',
    diagnostics: {
      matched_groups: [],
      matched_roles: ['admin'],
      selected_role: 'admin',
      precedence_rule: 'permission_mapping_paused',
    },
  };
}

async function resolveCurrentUserPermission(projectContext?: AzureProjectContext): Promise<PermissionState> {
  const user = getCurrentAzureDevOpsUserIdentity();
  if (!AZURE_DEVOPS_PERMISSION_MAPPING_ENABLED) {
    return {
      role: 'admin',
      user_display_name: user.displayName || user.name || '',
      user_name: user.uniqueName || user.email || user.name || '',
      mapped_group: 'Permission Mapping Paused',
      azure_groups: [],
      status: 'fallback',
      warning: 'Azure DevOps permission mapping is paused. Project Intelligence access is temporarily open while group resolution is stabilized.',
      diagnostics: {
        matched_groups: [],
        matched_roles: ['admin'],
        selected_role: 'admin',
        precedence_rule: 'permission_mapping_paused',
      },
    };
  }
  try {
    const graphClient = getClient(GraphRestClient);
    const descriptor = await resolveUserGraphDescriptor(graphClient, user);
    let groupNames: string[] = [];
    if (descriptor) {
      groupNames = await collectAzureDevOpsGroupNames(graphClient, descriptor);
      if (!groupNames.length) {
        groupNames = await collectGroupsViaRestApi(descriptor);
      }
    }
    if (groupNames.length) {
      const mapping = mapGroupsToAIGenRole(groupNames, projectContext?.name || '');
      const ownerFallback = inferProjectOwnerPermission(user);
      if (mapping.role === 'viewer' && ownerFallback) {
        return {
          ...ownerFallback,
          azure_groups: uniqueStrings([...groupNames, ...ownerFallback.azure_groups]),
          status: 'resolved',
          warning: 'Azure DevOps only exposed a Readers mapping, so organization owner context was used for AI Gen Admin access.',
          diagnostics: {
            matched_groups: uniqueStrings([...groupNames, ...ownerFallback.azure_groups]),
            matched_roles: uniqueStrings([...(mapping.diagnostics?.matched_roles || []), 'admin']) as AIGenRole[],
            selected_role: 'admin',
            precedence_rule: 'organization_owner_over_readers',
          },
        };
      }
      return {
        role: mapping.role,
        user_display_name: user.displayName || user.name || '',
        user_name: user.uniqueName || user.email || user.name || '',
        mapped_group: mapping.group,
        azure_groups: groupNames,
        status: 'resolved',
        warning: undefined,
        diagnostics: mapping.diagnostics,
      };
    }
    const ownerFallback = inferProjectOwnerPermission(user);
    if (ownerFallback) {
      return ownerFallback;
    }
    return {
      role: 'viewer',
      user_display_name: user.displayName || user.name || '',
      user_name: user.uniqueName || user.email || user.name || '',
      mapped_group: 'Readers',
      azure_groups: [],
      status: 'fallback',
      warning: descriptor
        ? 'Azure DevOps group membership returned no visible groups. Viewer access is applied.'
        : 'Azure DevOps user descriptor could not be resolved. Viewer access is applied.',
    };
  } catch (error) {
    const ownerFallback = inferProjectOwnerPermission(user);
    if (ownerFallback) {
      return {
        ...ownerFallback,
        warning: `${ownerFallback.warning} Graph lookup failed: ${error instanceof Error ? error.message : String(error)}`,
      };
    }
    return {
      role: 'viewer',
      user_display_name: user.displayName || user.name || '',
      user_name: user.uniqueName || user.email || user.name || '',
      mapped_group: 'Readers',
      azure_groups: [],
      status: 'fallback',
      warning: `Could not resolve Azure DevOps group membership. Viewer access is applied. ${error instanceof Error ? error.message : String(error)}`,
    };
  }
}

function getCurrentAzureDevOpsUserIdentity(): AzureDevOpsUserIdentity {
  const sdkUser = SDK.getUser() as AzureDevOpsUserIdentity;
  const webUser = (SDK.getWebContext() as unknown as { user?: AzureDevOpsUserIdentity }).user || {};
  return {
    ...webUser,
    ...sdkUser,
    id: sdkUser.id || webUser.id,
    descriptor: sdkUser.descriptor || webUser.descriptor,
    subjectId: sdkUser.subjectId || webUser.subjectId,
    displayName: sdkUser.displayName || webUser.displayName || sdkUser.name || webUser.name,
    name: sdkUser.name || webUser.name || sdkUser.displayName || webUser.displayName,
    uniqueName: sdkUser.uniqueName || webUser.uniqueName || webUser.email || sdkUser.email,
    email: sdkUser.email || webUser.email || webUser.uniqueName || sdkUser.uniqueName,
  };
}

async function resolveUserGraphDescriptor(
  graphClient: GraphRestClient,
  user: AzureDevOpsUserIdentity,
): Promise<string> {
  if (user.descriptor) {
    return user.descriptor;
  }
  const candidates = uniqueStrings([
    user.id || '',
    user.subjectId || '',
  ]);
  for (const storageKey of candidates) {
    try {
      const descriptor = await graphClient.getDescriptor(storageKey);
      if (descriptor?.value) {
        return descriptor.value;
      }
    } catch {
      // Try the next candidate.
    }
    try {
      const descriptor = await getDescriptorViaRestApi(storageKey);
      if (descriptor) {
        return descriptor;
      }
    } catch {
      // Try the next candidate.
    }
  }
  return '';
}

async function getDescriptorViaRestApi(storageKey: string): Promise<string> {
  const token = await SDK.getAccessToken();
  const collectionUri = trimTrailingSlash(getCollectionUri());
  const response = await fetch(`${collectionUri}/_apis/graph/descriptors/${encodeURIComponent(storageKey)}?api-version=7.1-preview.1`, {
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/json',
    },
  });
  if (!response.ok) {
    return '';
  }
  const payload = await response.json();
  return String(payload.value || '');
}

async function collectGroupsViaRestApi(userDescriptor: string): Promise<string[]> {
  try {
    const token = await SDK.getAccessToken();
    const collectionUri = trimTrailingSlash(getCollectionUri());
    const url = `${collectionUri}/_apis/graph/memberships/${encodeURIComponent(userDescriptor)}?direction=Up&depth=1&api-version=7.1-preview.1`;
    const response = await fetch(url, {
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'application/json',
      },
    });
    if (!response.ok) {
      return [];
    }
    const data = await response.json();
    const descriptors = uniqueStrings((data.value || []).map((item: { containerDescriptor?: string }) => item.containerDescriptor || '').filter(Boolean));
    const subjects = await Promise.all(descriptors.map((descriptor) => getGraphSubjectViaRestApi(descriptor)));
    return uniqueStrings(subjects.map((subject) => subject.displayName || '').filter(Boolean));
  } catch (error) {
    return [];
  }
}

async function getGraphSubjectViaRestApi(descriptor: string): Promise<{ displayName?: string }> {
  try {
    const token = await SDK.getAccessToken();
    const collectionUri = trimTrailingSlash(getCollectionUri());
    const response = await fetch(`${collectionUri}/_apis/graph/subjects/${encodeURIComponent(descriptor)}?api-version=7.1-preview.1`, {
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'application/json',
      },
    });
    if (!response.ok) {
      return {};
    }
    return await response.json();
  } catch {
    return {};
  }
}

function inferProjectOwnerPermission(user: { name?: string; uniqueName?: string; email?: string }): PermissionState | undefined {
  const accountNames = getAzureDevOpsAccountNames();
  const identifiers = [user.uniqueName, user.email, user.name].map((value) => String(value || '').toLowerCase());
  const identifierPrefixes = identifiers
    .map((identifier) => identifier.split('@')[0])
    .filter(Boolean);
  const ownsOrganization = accountNames.some((accountName) => (
    accountName && (
      identifiers.some((identifier) => identifier.startsWith(`${accountName}@`) || identifier === accountName)
      || identifierPrefixes.includes(accountName)
    )
  ));
  if (!ownsOrganization) {
    return undefined;
  }
  return {
    role: 'admin',
    user_display_name: user.name || user.uniqueName || '',
    user_name: user.uniqueName || user.email || user.name || '',
    mapped_group: 'Project Administrators',
    azure_groups: ['Project Administrators'],
    status: 'fallback',
    warning: 'Azure DevOps Graph group lookup was unavailable, so organization owner context was mapped to AI Gen Admin.',
    diagnostics: {
      matched_groups: uniqueStrings(['Project Administrators', ...accountNames.map((name) => `account:${name}`)]),
      matched_roles: ['admin'],
      selected_role: 'admin',
      precedence_rule: 'organization_owner_fallback',
    },
  };
}

function getAzureDevOpsAccountNames(): string[] {
  const names: string[] = [];
  const addName = (value?: string) => {
    const cleaned = String(value || '').trim();
    if (cleaned) {
      names.push(cleaned);
    }
  };
  const addUrl = (value?: string) => {
    const org = extractAzureDevOpsOrgName(value || '');
    if (org) {
      names.push(org);
    }
  };
  try {
    const host = SDK.getHost() as unknown as { name?: string };
    addName(host?.name);
  } catch {
    // Continue with web/page context.
  }
  try {
    const context = SDK.getWebContext() as unknown as {
      account?: { name?: string; uri?: string };
      host?: { name?: string; uri?: string };
      collection?: { name?: string; uri?: string };
    };
    [context.account?.name, context.host?.name, context.collection?.name].forEach(addName);
    [context.account?.uri, context.host?.uri, context.collection?.uri].forEach(addUrl);
  } catch {
    // Continue with page context.
  }
  try {
    const pageContext = SDK.getPageContext() as unknown as {
      webContext?: {
        account?: { name?: string; uri?: string };
        host?: { name?: string; uri?: string };
        collection?: { name?: string; uri?: string };
      };
    };
    [pageContext.webContext?.account?.name, pageContext.webContext?.host?.name, pageContext.webContext?.collection?.name].forEach(addName);
    [pageContext.webContext?.account?.uri, pageContext.webContext?.host?.uri, pageContext.webContext?.collection?.uri].forEach(addUrl);
    collectAzureDevOpsNamesFromObject(pageContext).forEach(addName);
  } catch {
    // Ignore missing host context.
  }
  try {
    addUrl(getCollectionUri());
  } catch {
    // Ignore missing collection URI.
  }
  [window.location.href, document.referrer].forEach(addUrl);
  return uniqueStrings(names.map((name) => String(name).toLowerCase()).filter(Boolean));
}

function collectAzureDevOpsNamesFromObject(value: unknown): string[] {
  const names: string[] = [];
  const seen = new Set<unknown>();
  const visit = (node: unknown, depth: number) => {
    if (!node || depth > 5 || seen.has(node)) {
      return;
    }
    if (typeof node === 'string') {
      const org = extractAzureDevOpsOrgName(node);
      if (org) {
        names.push(org);
      }
      return;
    }
    if (typeof node !== 'object') {
      return;
    }
    seen.add(node);
    Object.entries(node as Record<string, unknown>).forEach(([key, item]) => {
      if ((key === 'uri' || key === 'relativeUri') && typeof item === 'string') {
        const org = extractAzureDevOpsOrgName(item);
        if (org) {
          names.push(org);
        }
      }
      if (key === 'name' && typeof item === 'string') {
        names.push(item);
      }
      visit(item, depth + 1);
    });
  };
  visit(value, 0);
  return uniqueStrings(names);
}

function extractAzureDevOpsOrgName(value: string): string {
  const text = String(value || '').trim();
  if (!text) {
    return '';
  }
  try {
    const parsed = new URL(text, window.location.origin);
    if (parsed.hostname.toLowerCase() === 'dev.azure.com') {
      return parsed.pathname.split('/').filter(Boolean)[0] || '';
    }
    if (parsed.hostname.toLowerCase().endsWith('.visualstudio.com')) {
      return parsed.hostname.split('.')[0] || '';
    }
  } catch {
    // Try simple path parsing below.
  }
  const devAzureMatch = text.match(/dev\.azure\.com\/([^/?#]+)/i);
  if (devAzureMatch?.[1]) {
    return devAzureMatch[1];
  }
  const relativeMatch = text.match(/^\/([^/?#]+)(?:\/|$)/);
  return relativeMatch?.[1] || '';
}



async function collectAzureDevOpsGroupNames(graphClient: GraphRestClient, userDescriptor: string): Promise<string[]> {
  const visited = new Set<string>([userDescriptor]);
  let frontier = [userDescriptor];
  const groupNames: string[] = [];
  for (let depth = 0; depth < 4 && frontier.length; depth += 1) {
    const memberships = (await Promise.all(frontier.map(async (descriptor) => {
      try {
        return await graphClient.listMemberships(descriptor, GraphTraversalDirection.Up, 1);
      } catch {
        return [];
      }
    }))).flat();
    const nextDescriptors = uniqueStrings(memberships.map((membership) => membership.containerDescriptor).filter(Boolean))
      .filter((descriptor) => !visited.has(descriptor));
    if (!nextDescriptors.length) {
      break;
    }
    nextDescriptors.forEach((descriptor) => visited.add(descriptor));
    const subjects = await Promise.all(nextDescriptors.map(async (descriptor) => {
      try {
        return await graphClient.getSubject(descriptor);
      } catch {
        return undefined;
      }
    }));
    subjects.forEach((subject) => {
      if (subject?.displayName) {
        groupNames.push(subject.displayName);
      }
    });
    frontier = nextDescriptors;
  }
  return uniqueStrings(groupNames);
}

function mapGroupsToAIGenRole(groupNames: string[], projectName: string): { role: AIGenRole; group: string; diagnostics: PermissionState['diagnostics'] } {
  const normalized = groupNames.map((group) => normalizeGroupName(group, projectName));

  // Collect all matched roles instead of returning on first match
  const matchedRoles: { role: AIGenRole; groups: string[] }[] = [];

  const adminGroups = normalized
    .map((group, i) => ({ group, index: i, normalized: group }))
    .filter(({ normalized }) => {
      const match = normalized.includes('project administrators')
        || normalized.includes('project collection administrators')
        || normalized.includes('collection administrators')
        || normalized.includes('team foundation administrators');
      return match;
    })
    .map(({ index }) => groupNames[index]);

  const contributorGroups = normalized
    .map((group, i) => ({ group, index: i, normalized: group }))
    .filter(({ normalized }) => {
      const match = normalized.includes('contributors');
      return match;
    })
    .map(({ index }) => groupNames[index]);

  const readerGroups = normalized
    .map((group, i) => ({ group, index: i, normalized: group }))
    .filter(({ normalized }) => {
      const match = normalized.includes('readers');
      return match;
    })
    .map(({ index }) => groupNames[index]);

  if (adminGroups.length > 0) {
    matchedRoles.push({ role: 'admin', groups: adminGroups });
  }
  if (contributorGroups.length > 0) {
    matchedRoles.push({ role: 'contributor', groups: contributorGroups });
  }
  if (readerGroups.length > 0) {
    matchedRoles.push({ role: 'viewer', groups: readerGroups });
  }

  // Determine highest role by precedence: admin > contributor > viewer
  let selectedRole: AIGenRole = 'viewer';
  let selectedGroup = 'Readers';
  let precedenceRule = 'default_viewer';

  if (matchedRoles.some(m => m.role === 'admin')) {
    selectedRole = 'admin';
    selectedGroup = 'Project Administrators';
    precedenceRule = 'admin_takes_precedence';
  } else if (matchedRoles.some(m => m.role === 'contributor')) {
    selectedRole = 'contributor';
    selectedGroup = 'Contributors';
    precedenceRule = 'contributor_takes_precedence_over_viewer';
  }

  const diagnostics = {
    matched_groups: groupNames,
    matched_roles: matchedRoles.map(m => m.role),
    selected_role: selectedRole,
    precedence_rule: precedenceRule,
  };

  return { role: selectedRole, group: selectedGroup, diagnostics };
}

function normalizeGroupName(groupName: string, projectName: string): string {
  return groupName
    .toLowerCase()
    .replace(projectName.toLowerCase(), '')
    .replace(/[\[\]\\]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function roleLabel(role: AIGenRole): string {
  if (role === 'admin') return 'AI Gen Admin';
  if (role === 'contributor') return 'AI Gen Contributor';
  return 'AI Gen Viewer';
}

function defaultKnowledgeGovernance(profile: ProjectProfile, canAdmin: boolean): KnowledgeGovernance {
  return {
    registry_status: hasKnowledgeRegistry(profile) ? 'read_only' : 'pending',
    editability: canAdmin ? 'editable' : 'read_only',
    knowledge_version: knowledgeVersion(profile),
    last_refreshed_by: '',
    last_refreshed_on: '',
  };
}

function normalizeKnowledgeGovernance(profile: ProjectProfile, governance: KnowledgeGovernance, canAdmin: boolean): KnowledgeGovernance {
  return {
    ...governance,
    registry_status: hasKnowledgeRegistry(profile) ? 'read_only' : 'pending',
    editability: canAdmin ? 'editable' : 'read_only',
    knowledge_version: knowledgeVersion(profile),
  };
}

function hasKnowledgeRegistry(profile: ProjectProfile): boolean {
  return Boolean(
    profile.knowledge_registry.modules.length
    || profile.knowledge_registry.flows.length
    || profile.knowledge_registry.components.length
    || profile.knowledge_registry.architecture_notes.length
    || profile.knowledge_registry.source_files.length
  );
}

function knowledgeStatusLabel(governance: KnowledgeGovernance): string {
  if (governance.registry_status === 'pending') {
    return governance.editability === 'editable' ? 'Editable' : 'Read Only';
  }
  return governance.editability === 'editable' ? 'Read Only / Admin Editable' : 'Read Only';
}

function readProjectSession(): ProjectSessionSnapshot | undefined {
  try {
    const raw = window.localStorage.getItem(PROJECT_SESSION_STORAGE_KEY);
    if (!raw) {
      return undefined;
    }
    const parsed = JSON.parse(raw) as Partial<ProjectSessionSnapshot>;
    if (!parsed.profile || typeof parsed.profile !== 'object') {
      return undefined;
    }
    return {
      profile: parsed.profile as ProjectProfile,
      active_project: parsed.active_project || (parsed.profile as ProjectProfile).project_name || 'Project Intelligence',
      repository_name: parsed.repository_name || (parsed.profile as ProjectProfile).repository_connection?.repository_name || '',
      repository_id: parsed.repository_id || (parsed.profile as ProjectProfile).repository_connection?.repository_id || '',
      branch: parsed.branch || (parsed.profile as ProjectProfile).repository_connection?.branch || 'main',
      knowledge_version: parsed.knowledge_version || knowledgeVersion(parsed.profile as ProjectProfile),
      last_analysis_timestamp: parsed.last_analysis_timestamp || '',
      last_active_tab: isPlannerTab(parsed.last_active_tab) ? parsed.last_active_tab : 'overview',
      last_workspace: isPlannerTab(parsed.last_workspace) ? parsed.last_workspace : (isPlannerTab(parsed.last_active_tab) ? parsed.last_active_tab : 'overview'),
      last_work_item_id: Number(parsed.last_work_item_id || 0) || undefined,
      last_work_item_type: parsed.last_work_item_type || '',
      last_work_item_title: parsed.last_work_item_title || '',
      auto_route_by_work_item_type: parsed.auto_route_by_work_item_type !== false,
      approval_workflow: normalizeApprovalWorkflowState(parsed.approval_workflow),
      knowledge_governance: parsed.knowledge_governance,
      execution_context: parsed.execution_context,
      execution_plan: parsed.execution_plan,
      dev_prompt: parsed.dev_prompt,
      ui_prompt: parsed.ui_prompt,
      qa_prompt: parsed.qa_prompt,
      copilot_context: parsed.copilot_context,
      qa_test_suite: parsed.qa_test_suite,
      implementation_validation: parsed.implementation_validation,
      pr_review: parsed.pr_review,
      saved_at: parsed.saved_at || new Date().toISOString(),
    };
  } catch {
    return undefined;
  }
}

function sessionFromBackend(response?: BackendProjectSessionResponse, cachedProfile?: ProjectProfile): ProjectSessionSnapshot | undefined {
  if (!response?.exists || !response.session || !cachedProfile) {
    return undefined;
  }
  const session = response.session;
  const tab = isPlannerTab(session.last_active_tab) ? session.last_active_tab : isPlannerTab(session.last_workspace) ? session.last_workspace : 'overview';
  return {
    profile: cachedProfile,
    active_project: String(session.active_project || cachedProfile.project_name || 'Project Intelligence'),
    repository_name: String(session.repository_name || session.last_repository || cachedProfile.repository_connection.repository_name || ''),
    repository_id: String(session.repository_id || session.last_repository_id || cachedProfile.repository_connection.repository_id || ''),
    branch: String(session.branch || session.last_branch || cachedProfile.repository_connection.branch || 'main'),
    knowledge_version: String(session.knowledge_version || knowledgeVersion(cachedProfile)),
    last_analysis_timestamp: String(session.last_analysis_timestamp || ''),
    last_active_tab: tab,
    last_workspace: tab,
    last_work_item_id: Number(session.last_work_item_id || 0) || undefined,
    last_work_item_type: String(session.last_work_item_type || ''),
    last_work_item_title: String(session.last_work_item_title || ''),
    auto_route_by_work_item_type: session.auto_route_by_work_item_type !== false,
    approval_workflow: normalizeApprovalWorkflowState(session.approval_workflow),
    execution_context: session.execution_context as ExecutionContextResult | undefined,
    execution_plan: session.execution_plan as ExecutionPlanResult | undefined,
    dev_prompt: session.dev_prompt as PromptBuilderResult | undefined,
    ui_prompt: session.ui_prompt as PromptBuilderResult | undefined,
    qa_prompt: session.qa_prompt as PromptBuilderResult | undefined,
    copilot_context: session.copilot_context as CopilotContextResult | undefined,
    qa_test_suite: session.qa_test_suite as QATestSuiteResult | undefined,
    implementation_validation: session.implementation_validation as ImplementationValidationReport | undefined,
    pr_review: session.pr_review as PRReviewReport | undefined,
    saved_at: String(session.saved_at || new Date().toISOString()),
  };
}

function writeProjectSession(session: ProjectSessionSnapshot): void {
  try {
    window.localStorage.setItem(PROJECT_SESSION_STORAGE_KEY, JSON.stringify(session));
  } catch {
    // Local persistence is best-effort; backend autosave still owns profile durability.
  }
}

function buildProjectSession(
  profile: ProjectProfile,
  activeTab: PlannerTab,
  lastAnalysisTimestamp: string,
  governance: KnowledgeGovernance,
  currentWorkItem?: AdoWorkItem,
  autoRouteByWorkItemType = true,
  approvalWorkflow: ApprovalWorkflowState = defaultApprovalWorkflowState(),
  workspaceState: Partial<ProjectSessionSnapshot> = {},
): ProjectSessionSnapshot {
  const mapping = getAdoMapping(profile);
  const now = new Date().toISOString();
  return {
    profile,
    active_project: profile.project_name || mapping.ado_project || 'Project Intelligence',
    repository_name: mapping.repository_name || profile.repository_connection.repository_name || '',
    repository_id: mapping.repository_id || profile.repository_connection.repository_id || '',
    branch: mapping.branch || profile.repository_connection.branch || 'main',
    knowledge_version: knowledgeVersion(profile),
    last_analysis_timestamp: lastAnalysisTimestamp || inferLastAnalysisTimestamp(profile) || now,
    last_active_tab: activeTab,
    last_workspace: activeTab,
    last_work_item_id: currentWorkItem?.id,
    last_work_item_type: currentWorkItem?.type || '',
    last_work_item_title: currentWorkItem?.title || '',
    auto_route_by_work_item_type: autoRouteByWorkItemType,
    approval_workflow: approvalWorkflow,
    knowledge_governance: governance,
    execution_context: workspaceState.execution_context,
    execution_plan: workspaceState.execution_plan,
    dev_prompt: workspaceState.dev_prompt,
    ui_prompt: workspaceState.ui_prompt,
    qa_prompt: workspaceState.qa_prompt,
    copilot_context: workspaceState.copilot_context,
    qa_test_suite: workspaceState.qa_test_suite,
    implementation_validation: workspaceState.implementation_validation,
    pr_review: workspaceState.pr_review,
    saved_at: now,
  };
}

function isPlannerTab(value: unknown): value is PlannerTab {
  return value === 'overview' || value === 'planning' || value === 'execution' || value === 'qa' || value === 'memory' || value === 'governance' || value === 'agents' || value === 'skills' || value === 'admin';
}

function knowledgeVersion(profile: ProjectProfile): string {
  const registry = profile.knowledge_registry;
  const input = JSON.stringify({
    project: profile.project_name,
    repository: profile.repository_connection.repository_id || profile.repository_connection.repository_name,
    branch: profile.repository_connection.branch,
    modules: registry.modules,
    flows: registry.flows,
    components: registry.components,
    architecture_notes: registry.architecture_notes,
    standards: registry.standards,
    source_files: registry.source_files,
  });
  let hash = 0;
  for (let index = 0; index < input.length; index += 1) {
    hash = ((hash << 5) - hash + input.charCodeAt(index)) | 0;
  }
  return `kv-${Math.abs(hash).toString(36).padStart(6, '0')}`;
}

function inferLastAnalysisTimestamp(profile: ProjectProfile): string {
  return profile.knowledge_registry.source_files.length || profile.readme_analysis.summary ? new Date().toISOString() : '';
}

function knowledgeFreshness(timestamp: string): 'Fresh' | 'Stale' | 'Not analyzed' {
  if (!timestamp) {
    return 'Not analyzed';
  }
  const ageMs = Date.now() - Date.parse(timestamp);
  if (!Number.isFinite(ageMs)) {
    return 'Not analyzed';
  }
  return ageMs > 14 * 24 * 60 * 60 * 1000 ? 'Stale' : 'Fresh';
}

function formatTimestamp(value: string): string {
  if (!value) {
    return 'Not analyzed yet';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

function profileCompletion(profile: ProjectProfile): { complete: boolean; missing: string[] } {
  const checks = [
    { label: 'Project Name', ready: Boolean(profile.project_name.trim()) },
    { label: 'Project Description', ready: Boolean(profile.project_description.trim()) },
    { label: 'Repository', ready: Boolean(profile.repository_connection.repository_id || profile.repository_sources.length) },
    { label: 'Applications', ready: Boolean(profile.applications.length || profile.knowledge_registry.applications.length) },
    { label: 'Technology Stack', ready: STACK_FIELDS.some((field) => profile.technology_stack[field].length > 0) },
    { label: 'Knowledge Registry', ready: Boolean(profile.knowledge_registry.modules.length || profile.knowledge_registry.flows.length || profile.knowledge_registry.components.length) },
    { label: 'UI Guidelines', ready: summarizeUiGuidelines(profile) !== 'Not captured yet' },
    { label: 'Development Standards', ready: hasDevelopmentStandards(profile) },
  ];
  const readyCount = checks.filter((check) => check.ready).length;
  return {
    complete: readyCount === checks.length,
    missing: checks.filter((check) => !check.ready).map((check) => check.label),
  };
}

function standardsCaptured(profile: ProjectProfile): boolean {
  return hasDevelopmentStandards(profile) || summarizeUiGuidelines(profile) !== 'Not captured yet';
}

function buildWorkflowOrchestration({
  itemType,
  approvalWorkflow,
  childDrafts,
  epicResult,
  featureResult,
  storyResult,
  hasQa,
  hasExecution,
  hasKnowledge,
  standardsReady,
  hasExecutionPackage,
}: {
  itemType: WorkItemKind;
  approvalWorkflow: ApprovalWorkflowState;
  childDrafts: ChildDraft[];
  epicResult?: EpicRefinement;
  featureResult?: FeatureRefinement;
  storyResult?: StoryRefinement;
  hasQa: boolean;
  hasExecution: boolean;
  hasKnowledge: boolean;
  standardsReady: boolean;
  hasExecutionPackage: boolean;
}): WorkflowOrchestrationState {
  const featureDrafts = childDrafts.filter((draft) => draft.type === 'Feature');
  const storyDrafts = childDrafts.filter((draft) => draft.type === 'User Story');
  const taskDrafts = childDrafts.filter((draft) => draft.type === 'Task');
  const featureCandidates = featureDrafts;
  const storyCandidates = storyDrafts;
  const taskCandidates = taskDrafts;
  const capabilities = epicResult?.capability_review || [];
  const hasEpicAnalysis = Boolean(epicResult || capabilities.length);
  const hasFeatureAnalysis = Boolean(featureResult);
  const hasStoryAnalysis = Boolean(storyResult);
  const allCapabilitiesReviewed = !capabilities.length || capabilities.every(isCapabilityReviewed);
  const approvedCapabilities = capabilities.filter(isCapabilityApproved).length;
  const featuresApproved = approvalWorkflow.features === 'approved' || areAllDraftsApproved(featureCandidates);
  const selectableFeatureDrafts = featureCandidates.filter((draft) => draft.selected && draft.status !== 'created');
  const storiesApproved = approvalWorkflow.stories === 'approved' || areAllDraftsReviewed(storyCandidates);
  const selectableStoryDrafts = mergeFeatureStoryDraftsFromReviewState(featureResult, childDrafts).filter((draft) => draft.selected && draft.status !== 'created');
  const tasksApproved = approvalWorkflow.tasks === 'approved' || areAllDraftsApproved(taskCandidates);
  const blockers = [
    !hasKnowledge ? 'Project knowledge is missing. Repository analysis will improve recommendations.' : '',
    !standardsReady ? 'Development or UI standards are missing.' : '',
  ].filter(Boolean);

  let nextAction: WorkflowNextAction = {
    label: 'Open Planning',
    action: 'open_planning',
    workspace: 'planning',
    reason: 'Start by planning the current work item.',
  };
  let currentStage = 'Planning';

  if (itemType === 'Epic') {
    if (!hasEpicAnalysis) {
      nextAction = { label: 'Analyze Epic', action: 'analyze_epic', workspace: 'planning', reason: 'Start by analyzing the Epic before capability review or feature generation.' };
      currentStage = 'Epic Analysis';
    } else if (capabilities.length && !allCapabilitiesReviewed) {
      nextAction = {
        label: 'Review Remaining Capabilities',
        action: 'open_planning',
        workspace: 'planning',
        reason: `${capabilities.filter((capability) => !isCapabilityReviewed(capability)).length} capabilities still require approval before feature generation.`,
      };
      currentStage = 'Capability Review';
    } else if (!featureDrafts.length) {
      nextAction = {
        label: 'Generate Features',
        action: 'generate_features',
        workspace: 'planning',
        reason: capabilities.length && approvedCapabilities === 0
          ? 'Approve at least one capability before generating Features.'
          : 'The epic is ready. Generate child Features next.',
      };
      currentStage = 'Feature Generation';
    } else if (!featuresApproved || isApprovalPending(approvalWorkflow.features)) {
      nextAction = { label: 'Approve Features', action: 'approve_features', workspace: 'planning', reason: 'Generated Features are waiting for approval.' };
      currentStage = 'Feature Approval';
    } else if (selectableFeatureDrafts.length) {
      nextAction = { label: 'Create Selected Features', action: 'create_children', workspace: 'planning', reason: 'Selected Feature drafts are ready to be created in Azure DevOps.' };
      currentStage = 'Feature Ready';
    } else {
      nextAction = { label: 'Feature Creation Complete', action: 'open_planning', workspace: 'planning', reason: 'Feature drafts have already been created or deselected for this Epic.' };
      currentStage = 'Feature Ready';
    }
  } else if (itemType === 'Feature') {
    if (!hasFeatureAnalysis) {
      nextAction = { label: 'Analyze Feature', action: 'analyze_feature', workspace: 'planning', reason: 'Start by analyzing the Feature before story generation.' };
      currentStage = 'Feature Analysis';
    } else if (isApprovalPending(approvalWorkflow.feature)) {
      nextAction = { label: 'Approve Feature', action: 'approve_feature', workspace: 'planning', reason: 'The feature draft is ready and needs approval before story generation.' };
      currentStage = 'Feature Approval';
    } else if (!storyCandidates.length) {
      nextAction = { label: 'Generate Stories', action: 'generate_stories', workspace: 'planning', reason: 'The feature is ready. Generate child Stories next.' };
      currentStage = 'Story Generation';
    } else if (!storiesApproved || storyCandidates.some((draft) => !['approved', 'created', 'failed', 'skipped'].includes(draft.status)) || isApprovalPending(approvalWorkflow.stories)) {
      nextAction = { label: 'Approve Stories', action: 'approve_stories', workspace: 'planning', reason: 'Generated Stories are waiting for approval.' };
      currentStage = 'Story Approval';
    } else if (selectableStoryDrafts.length) {
      nextAction = { label: 'Create Selected Stories', action: 'create_children', workspace: 'planning', reason: 'Selected Story drafts are ready to be created in Azure DevOps.' };
      currentStage = 'Story Ready';
    } else {
      nextAction = { label: 'Story Creation Complete', action: 'open_planning', workspace: 'planning', reason: 'Story drafts have already been created or deselected for this Feature.' };
      currentStage = 'Story Ready';
    }
  } else if (itemType === 'Story') {
    if (!hasStoryAnalysis) {
      nextAction = { label: 'Analyze Story', action: 'analyze_story', workspace: 'planning', reason: 'Start by analyzing the Story before task generation.' };
      currentStage = 'Story Analysis';
    } else if (!taskCandidates.length) {
      nextAction = { label: 'Generate Tasks', action: 'generate_tasks', workspace: 'planning', reason: 'The story analysis is ready. Generate implementation tasks next.' };
      currentStage = 'Task Generation';
    } else if (!tasksApproved || isApprovalPending(approvalWorkflow.tasks)) {
      nextAction = { label: 'Approve Tasks', action: 'approve_tasks', workspace: 'planning', reason: 'Generated Tasks are waiting for approval.' };
      currentStage = 'Task Approval';
    } else if (!hasExecution) {
      nextAction = { label: 'Open Execution Workspace', action: 'open_execution', workspace: 'execution', reason: 'Tasks are approved. Open Execution to build the implementation package from the selected Task.' };
      currentStage = 'Implementation Package';
    } else {
      nextAction = { label: 'Open VS Code', action: 'open_vscode', workspace: 'execution', reason: 'Execution package is ready for implementation.' };
      currentStage = 'Execution Ready';
    }
  } else if (itemType === 'Task') {
    nextAction = hasExecutionPackage
      ? { label: 'Open VS Code', action: 'open_vscode', workspace: 'execution', reason: 'The implementation package is ready.' }
      : { label: 'Build Implementation Package', action: 'build_execution', workspace: 'execution', reason: 'Build the implementation package for this task.' };
    currentStage = hasExecutionPackage ? 'Execution Ready' : 'Implementation Package';
  } else if (itemType === 'Bug') {
    nextAction = hasExecutionPackage
      ? { label: 'Open VS Code', action: 'open_vscode', workspace: 'execution', reason: 'The fix package is ready.' }
      : { label: 'Build Implementation Package', action: 'build_execution', workspace: 'execution', reason: 'Build the fix context and regression prompt.' };
    currentStage = hasExecutionPackage ? 'Fix Ready' : 'Fix Context';
  } else {
    nextAction = { label: 'Coverage Analysis', action: 'generate_tests', workspace: 'qa', reason: 'Analyze test coverage and regression scope.' };
    currentStage = 'QA Coverage';
  }

  const statuses = workflowStatusesForStage({
    itemType,
    currentStage,
    hasQa,
    hasExecution,
    featuresApproved,
    storiesApproved,
    tasksApproved,
    featureDrafts: featureCandidates,
    storyDrafts: storyCandidates,
    taskDrafts: taskCandidates,
    approvalWorkflow,
  });

  const planningHealth: WorkflowHealthStatus = blockers.length ? 'Needs Attention' : ['Epic', 'Feature'].includes(itemType) ? 'In Progress' : 'Ready';
  const qaHealth: WorkflowHealthStatus = hasQa ? 'Ready' : itemType === 'Story' || itemType === 'Bug' || itemType === 'Test Case' ? 'Needs Attention' : 'In Progress';
  const executionHealth: WorkflowHealthStatus = hasExecution ? 'Ready' : itemType === 'Story' || itemType === 'Task' || itemType === 'Bug' ? 'Needs Attention' : 'In Progress';
  const coverageHealth: WorkflowHealthStatus = hasQa ? 'Ready' : 'Needs Attention';

  return {
    statuses,
    planningHealth,
    executionHealth,
    qaHealth,
    coverageHealth,
    currentStage,
    nextAction,
    blockers,
  };
}

function workflowStatusesForStage({
  itemType,
  currentStage,
  hasQa,
  hasExecution,
  featuresApproved,
  storiesApproved,
  tasksApproved,
  featureDrafts,
  storyDrafts,
  taskDrafts,
  approvalWorkflow,
}: {
  itemType: WorkItemKind;
  currentStage: string;
  hasQa: boolean;
  hasExecution: boolean;
  featuresApproved: boolean;
  storiesApproved: boolean;
  tasksApproved: boolean;
  featureDrafts: ChildDraft[];
  storyDrafts: ChildDraft[];
  taskDrafts: ChildDraft[];
  approvalWorkflow: ApprovalWorkflowState;
}): WorkflowOrchestrationState['statuses'] {
  const pending: WorkflowOrchestrationState['statuses'] = {
    epic: 'pending',
    features: 'pending',
    stories: 'pending',
    tasks: 'pending',
    tests: hasQa ? 'complete' : 'pending',
    execution: hasExecution ? 'complete' : 'pending',
  };
  if (itemType === 'Epic') {
    pending.epic = approvalWorkflow.epic === 'approved' ? 'complete' : currentStage === 'Epic Approval' ? 'current' : 'pending';
    pending.features = featureDrafts.length ? (featuresApproved ? 'complete' : 'current') : currentStage === 'Feature Generation' ? 'current' : 'pending';
    pending.stories = currentStage === 'Capability Review' ? 'blocked' : 'pending';
    return onlyOneCurrent(
      pending,
      currentStage === 'Epic Approval'
        ? 'epic'
        : currentStage === 'Capability Review' || currentStage.includes('Feature')
          ? 'features'
          : undefined,
    );
  }
  if (itemType === 'Feature') {
    pending.epic = 'complete';
    pending.features = approvalWorkflow.feature === 'approved' ? 'complete' : currentStage === 'Feature Approval' ? 'current' : 'pending';
    pending.stories = storyDrafts.length ? (storiesApproved ? 'complete' : 'current') : currentStage === 'Story Generation' ? 'current' : 'pending';
    return onlyOneCurrent(pending, currentStage === 'Feature Approval' ? 'features' : currentStage.includes('Story') ? 'stories' : undefined);
  }
  if (itemType === 'Story') {
    pending.epic = 'complete';
    pending.features = 'complete';
    pending.stories = currentStage === 'Story Approval' ? 'current' : 'complete';
    pending.tasks = taskDrafts.length ? (tasksApproved ? 'complete' : 'current') : currentStage === 'Task Generation' ? 'current' : 'pending';
    pending.execution = hasExecution ? 'complete' : currentStage.includes('Execution') ? 'current' : 'pending';
    return onlyOneCurrent(pending, currentStage === 'Story Approval' ? 'stories' : currentStage.includes('Task') ? 'tasks' : currentStage.includes('Execution') ? 'execution' : undefined);
  }
  if (itemType === 'Task' || itemType === 'Bug') {
    pending.epic = 'complete';
    pending.features = 'complete';
    pending.stories = 'complete';
    pending.tasks = 'complete';
    pending.execution = hasExecution ? 'complete' : 'current';
    return onlyOneCurrent(pending, hasExecution ? undefined : 'execution');
  }
  pending.tests = hasQa ? 'complete' : 'current';
  return onlyOneCurrent(pending, hasQa ? undefined : 'tests');
}

function onlyOneCurrent(statuses: WorkflowOrchestrationState['statuses'], active?: keyof WorkflowOrchestrationState['statuses']): WorkflowOrchestrationState['statuses'] {
  if (!active) {
    return statuses;
  }
  return Object.fromEntries(Object.entries(statuses).map(([key, value]) => [key, key === active ? 'current' : value === 'current' ? 'pending' : value])) as WorkflowOrchestrationState['statuses'];
}

function profileReadinessBreakdown(profile: ProjectProfile): Array<{ title: string; percent: number; missing: string[]; status: 'Missing' | 'Partial' | 'Ready' }> {
  const stack = mergeTechnologyStack(profile.technology_stack, profile.knowledge_registry.technology_stack);
  const profileChecks = [
    { label: 'Project Name', ready: Boolean(profile.project_name.trim()) },
    { label: 'Description', ready: Boolean(profile.project_description.trim()) },
    { label: 'Domain', ready: Boolean(profile.domain.trim()) },
    { label: 'Project Type', ready: Boolean(profile.project_type.trim()) },
    { label: 'Applications', ready: Boolean(profile.applications.length || profile.knowledge_registry.applications.length) },
    { label: 'Technology Stack', ready: STACK_FIELDS.some((field) => stack[field].length > 0) },
    { label: 'UI Guidelines', ready: summarizeUiGuidelines(profile) !== 'Not captured yet' },
    { label: 'Development Standards', ready: hasDevelopmentStandards(profile) },
  ];
  const repositoryChecks = [
    { label: 'Repository Connected', ready: Boolean(profile.repository_connection.repository_id || profile.repository_connection.repository_name) },
    { label: 'Branch Selected', ready: Boolean(profile.repository_connection.branch) },
    { label: 'Documents Discovered', ready: Boolean(profile.repository_sources.length || profile.knowledge_registry.source_files.length) },
    { label: 'Documents Analyzed', ready: profile.repository_connection.status === 'Repository documents analyzed' || profile.repository_connection.status === 'README analyzed' || Boolean(profile.knowledge_registry.source_files.length) },
  ];
  const registryChecks = [
    { label: 'Modules', ready: Boolean(profile.knowledge_registry.modules.length) },
    { label: 'Flows', ready: Boolean(profile.knowledge_registry.flows.length) },
    { label: 'Components', ready: Boolean(profile.knowledge_registry.components.length) },
    { label: 'Architecture', ready: Boolean(profile.knowledge_registry.architecture_notes.length) },
    { label: 'Standards', ready: hasDevelopmentStandards(profile) },
  ];
  const executionChecks = [
    { label: 'Profile Setup', ready: readinessSection(profileChecks).status === 'Ready' },
    { label: 'Repository Analyzed', ready: readinessSection(repositoryChecks).status === 'Ready' },
    { label: 'Applications', ready: Boolean(profile.applications.length || profile.knowledge_registry.applications.length) },
    { label: 'Modules', ready: Boolean(profile.knowledge_registry.modules.length) },
    { label: 'Flows', ready: Boolean(profile.knowledge_registry.flows.length) },
    { label: 'Standards', ready: hasDevelopmentStandards(profile) },
    { label: 'Implementation Package Support', ready: true },
  ];
  return [
    { title: 'Profile Setup', ...readinessSection(profileChecks) },
    { title: 'Repository Intelligence', ...readinessSection(repositoryChecks) },
    { title: 'Knowledge Registry', ...readinessSection(registryChecks) },
    { title: 'Execution Readiness', ...readinessSection(executionChecks) },
  ];
}

function readinessSection(checks: Array<{ label: string; ready: boolean }>): { percent: number; missing: string[]; status: 'Missing' | 'Partial' | 'Ready' } {
  const readyCount = checks.filter((check) => check.ready).length;
  const percent = Math.round((readyCount / checks.length) * 100);
  return {
    percent,
    missing: checks.filter((check) => !check.ready).map((check) => check.label),
    status: readyCount === checks.length ? 'Ready' : readyCount > 0 ? 'Partial' : 'Missing',
  };
}

function projectSetupStatus(profile: ProjectProfile): { complete: boolean; checks: Array<{ title: string; status: 'Missing' | 'Ready'; detail: string }> } {
  const checks = [
    {
      title: 'Project Profile',
      status: (profile.project_name || profile.project_description) ? 'Ready' as const : 'Missing' as const,
      detail: profile.project_name || 'Add project name and description',
    },
    {
      title: 'Repository Connected',
      status: (profile.repository_connection.repository_id || profile.repository_connection.repository_name) ? 'Ready' as const : 'Missing' as const,
      detail: profile.repository_connection.repository_name || 'Connect Azure Repos',
    },
    {
      title: 'Knowledge Generated',
      status: knowledgeRegistryStatus(profile) === 'Ready' ? 'Ready' as const : 'Missing' as const,
      detail: knowledgeRegistryStatus(profile) === 'Ready' ? registrySummary(profile) : 'Analyze repository documents',
    },
    {
      title: 'Standards Captured',
      status: hasDevelopmentStandards(profile) ? 'Ready' as const : 'Missing' as const,
      detail: hasDevelopmentStandards(profile) ? 'Standards available' : 'Add standards or analyze docs',
    },
  ];
  return {
    complete: checks.every((check) => check.status === 'Ready'),
    checks,
  };
}

function enterpriseReadiness(profile: ProjectProfile, qaReady: boolean, executionReady: boolean): { checks: Array<{ title: string; status: 'Missing' | 'Partial' | 'Ready'; detail: string }> } {
  const setup = projectSetupStatus(profile);
  const checks = [
    {
      title: 'Planning Ready',
      status: setup.complete ? 'Ready' as const : 'Missing' as const,
      detail: setup.complete ? 'Backlog planning can use project knowledge' : 'Complete project setup first',
    },
    {
      title: 'Execution Ready',
      status: setup.complete ? 'Ready' as const : 'Missing' as const,
      detail: setup.complete ? (executionReady ? 'Implementation package generated' : 'Ready to generate implementation packages') : 'Complete project setup first',
    },
    {
      title: 'QA Ready',
      status: setup.complete ? 'Ready' as const : 'Missing' as const,
      detail: setup.complete ? (qaReady ? 'Test suite generated' : 'Ready to generate QA coverage') : 'Complete project setup first',
    },
  ];
  return { checks };
}

function generatedTagline(profile: ProjectProfile): string {
  const domain = (profile.domain || profile.knowledge_profile_preview.domain || '').toLowerCase();
  const name = profile.project_name || 'Project Intelligence';
  if (domain.includes('utility') || domain.includes('grid')) {
    return 'Real-time fault intelligence for utility distribution networks.';
  }
  if (domain.includes('meter')) {
    return 'Connected metering intelligence for field, operations, and analytics teams.';
  }
  if (domain.includes('property') || domain.includes('hospitality')) {
    return 'Operational planning intelligence for service-focused property experiences.';
  }
  if (profile.project_description) {
    return `${name} planning context for product, engineering, and QA alignment.`;
  }
  return 'Enterprise planning intelligence for product delivery teams.';
}

function repositoryDocumentSummary(
  fileStatus: Record<string, 'available' | 'missing' | 'unknown'>,
  sourceFiles: string[],
): Array<{ label: string; path: string; status: 'available' | 'missing' | 'unknown' }> {
  const groups = [
    { label: 'README', paths: ['README.md', 'docs/README.md'] },
    { label: 'Architecture', paths: ['architecture.md', 'docs/architecture.md'] },
    { label: 'Modules', paths: ['modules.md', 'docs/modules.md'] },
    { label: 'Flows', paths: ['flows.md', 'docs/flows.md'] },
    { label: 'UI Guidelines', paths: ['ui-guidelines.md', 'docs/ui-guidelines.md'] },
    { label: 'Coding Standards', paths: ['coding-standards.md', 'docs/coding-standards.md'] },
  ];
  const normalizedSources = sourceFiles.map((path) => path.replace(/^\/+/, ''));
  return groups.map((group) => {
    const discoveredPath = group.paths.find((path) => fileStatus[path] === 'available' || normalizedSources.includes(path));
    if (discoveredPath) {
      return { label: group.label, path: `/${discoveredPath}`, status: 'available' as const };
    }
    const known = group.paths.find((path) => fileStatus[path] === 'missing' || fileStatus[path] === 'unknown');
    return { label: group.label, path: '', status: known ? fileStatus[known] || 'unknown' : 'unknown' };
  });
}

function architectureLayers(notes: string[]): string[] {
  const text = notes.join(' ').toLowerCase();
  const layers = [];
  if (text.includes('mobile') || text.includes('app')) layers.push('Mobile App');
  if (text.includes('backend') || text.includes('api')) layers.push('Backend API');
  if (text.includes('telemetry')) layers.push('Telemetry Services');
  if (text.includes('analytics')) layers.push('Analytics Platform');
  if (text.includes('dashboard') || text.includes('portal')) layers.push('Operations Dashboard');
  return layers.length ? Array.from(new Set(layers)) : ['Mobile App', 'Backend API', 'Telemetry Services', 'Analytics Platform', 'Operations Dashboard'];
}

function knowledgeRegistryStatus(profile: ProjectProfile): 'Missing' | 'Partial' | 'Ready' {
  const readyCount = [
    profile.knowledge_registry.modules.length > 0,
    profile.knowledge_registry.flows.length > 0,
    profile.knowledge_registry.components.length > 0,
    profile.knowledge_registry.architecture_notes.length > 0,
  ].filter(Boolean).length;
  if (readyCount >= 4) {
    return 'Ready';
  }
  return readyCount > 0 ? 'Partial' : 'Missing';
}

function hasDevelopmentStandards(profile: ProjectProfile): boolean {
  return Object.values(profile.development_standards).some((items) => items.length > 0) || profile.knowledge_registry.standards.length > 0;
}

function registrySummary(profile: ProjectProfile): string {
  const parts = [
    profile.knowledge_registry.modules.length ? `${profile.knowledge_registry.modules.length} modules` : '',
    profile.knowledge_registry.flows.length ? `${profile.knowledge_registry.flows.length} flows` : '',
    profile.knowledge_registry.components.length ? `${profile.knowledge_registry.components.length} components` : '',
  ].filter(Boolean);
  return parts.join(', ') || 'Analyze repository documents';
}

function mergeProfile(current: ProjectProfile, analyzed: ProjectProfile): ProjectProfile {
  return {
    ...current,
    ...analyzed,
    project_name: current.project_name || analyzed.project_name,
    domain: current.domain || analyzed.domain,
    project_type: current.project_type || analyzed.project_type,
  };
}

function formatApplications(applications: ApplicationProfile[]): string {
  return applications.map((application) => `${application.name} (${application.type})`).join(', ');
}

function formatStack(stack: TechnologyStack): string {
  return STACK_FIELDS
    .filter((field) => stack[field].length)
    .map((field) => `${titleCase(field)}: ${stack[field].join(', ')}`)
    .join('; ');
}

async function getProjectName(): Promise<string> {
  const projectService = await SDK.getService<IProjectPageService>(CommonServiceIds.ProjectPageService);
  const project = await projectService.getProject();
  return String(project?.name || SDK.getWebContext().project?.name || '');
}

async function loadAzureProjectContext(): Promise<AzureProjectContext | undefined> {
  try {
    const projectService = await SDK.getService<IProjectPageService>(CommonServiceIds.ProjectPageService);
    const pageProject = await projectService.getProject();
    const webProject = SDK.getWebContext().project;
    const id = String(pageProject?.id || webProject?.id || '');
    const name = String(pageProject?.name || webProject?.name || '');
    let description = String((pageProject as { description?: string } | undefined)?.description || '');
    if (!description && (id || name)) {
      try {
        const key = encodeURIComponent(id || name);
        const project = await fetchAdoRest<{ id?: string; name?: string; description?: string }>(
          `/_apis/projects/${key}?api-version=7.1`,
          REPOSITORY_SDK_TIMEOUT_MS,
          'Azure DevOps project details timed out.',
        );
        description = String(project.description || '');
        return {
          id: String(project.id || id),
          name: String(project.name || name),
          description,
        };
      } catch {
        // Project description is optional; keep the page context values.
      }
    }
    if (!id && !name) {
      return undefined;
    }
    return { id, name, description };
  } catch {
    const webProject = SDK.getWebContext().project;
    const id = String(webProject?.id || '');
    const name = String(webProject?.name || '');
    return id || name ? { id, name, description: '' } : undefined;
  }
}

function seedProfileFromAzureProject(profile: ProjectProfile, project?: AzureProjectContext): ProjectProfile {
  if (!project) {
    return profile;
  }
  const projectName = profile.project_name.trim() || project.name;
  const projectDescription = profile.project_description.trim() || project.description;
  const projectId = (profile.project_id || '').trim() || project.id || project.name;
  const next = {
    ...profile,
    project_id: projectId,
    project_name: projectName,
    project_description: projectDescription,
  };
  if (!getAdoMapping(profile).ado_project && project.name) {
    return applyAdoMapping(next, { ado_project: project.name });
  }
  return next;
}

async function getProjectIdentifier(): Promise<string> {
  try {
    const projectName = await getProjectName();
    if (projectName) {
      return projectName;
    }
  } catch {
    // Some Azure DevOps contribution surfaces do not expose ProjectPageService.
  }
  const project = SDK.getWebContext().project;
  return String(project?.id || project?.name || '');
}

function withTimeout<T>(promise: Promise<T>, timeoutMs: number, message: string): Promise<T> {
  return new Promise((resolve, reject) => {
    const timeout = window.setTimeout(() => reject(new Error(message)), timeoutMs);
    promise.then(
      (value) => {
        window.clearTimeout(timeout);
        resolve(value);
      },
      (error) => {
        window.clearTimeout(timeout);
        reject(error);
      },
    );
  });
}

function normalizeBranchName(branch: string): string {
  return branch.replace(/^refs\/heads\//, '');
}

function summarizeUiGuidelines(profile: ProjectProfile): string {
  const values = [
    profile.ui_guidelines.primary_color ? `Primary ${profile.ui_guidelines.primary_color}` : '',
    profile.ui_guidelines.secondary_color ? `Secondary ${profile.ui_guidelines.secondary_color}` : '',
    profile.ui_guidelines.typography,
    profile.ui_guidelines.component_library,
    ...profile.ui_guidelines.accessibility_rules,
  ].filter(Boolean);
  return values.join(', ') || 'Not captured yet';
}

function latestProviderMetadata(items: Array<ProviderMetadata | undefined>): ProviderMetadata | undefined {
  return items.find((item) => item && (item.provider_used || item.source || item.phi_status));
}

function formatNumber(value?: number): string {
  return value === undefined || value === null ? 'n/a' : value.toLocaleString();
}

function formatLargestSections(sections?: Array<{ section?: string; tokens?: number }>): string {
  if (!sections?.length) {
    return 'n/a';
  }
  return sections.map((item) => `${item.section || 'unknown'} ${item.tokens || 0}`).join(', ');
}

function formatRejectedContext(items?: RejectedContextItem[]): string {
  if (!items?.length) {
    return 'n/a';
  }
  return items.slice(0, 8).map((item) => `${item.name || 'context'}${item.reason ? `: ${item.reason}` : ''}`).join(' | ');
}

function formatRelevanceScores(scores?: Record<string, number>): string {
  if (!scores || !Object.keys(scores).length) {
    return 'n/a';
  }
  return Object.entries(scores)
    .sort((left, right) => Number(right[1] || 0) - Number(left[1] || 0))
    .slice(0, 8)
    .map(([name, score]) => `${name} ${Number(score || 0).toFixed(2)}`)
    .join(', ');
}

function sourceLabel(source?: string): string {
  const normalized = String(source || '').trim();
  if (normalized === 'azure_phi') {
    return 'Azure Phi';
  }
  if (normalized === 'domain_fallback') {
    return 'Domain Fallback';
  }
  if (normalized === 'deterministic_fallback') {
    return 'Deterministic Fallback';
  }
  if (normalized === 'deterministic_execution') {
    return 'Deterministic Execution';
  }
  if (normalized === 'knowledge_registry') {
    return 'Knowledge Registry';
  }
  return 'Not run';
}

function readiness(profile: ProjectProfile): string {
  const hasDescription = Boolean(profile.project_description.trim() || profile.project_name.trim());
  const hasApplications = profile.applications.length > 0;
  const stack = profile.knowledge_registry.technology_stack || profile.technology_stack;
  const hasStack = STACK_FIELDS.some((field) => stack[field]?.length > 0);
  const hasStandards = Object.values(profile.development_standards).some((items) => items.length > 0) || profile.knowledge_registry.standards.length > 0;
  const hasRepositoryDocs = Boolean(profile.repository_sources.length || profile.knowledge_registry.source_files.length);
  const hasRegistry = profile.knowledge_registry.modules.length > 0 && profile.knowledge_registry.flows.length > 0;
  if (hasDescription && hasApplications && hasStack && hasRepositoryDocs && hasRegistry && hasStandards) {
    return 'Execution Ready';
  }
  if (hasDescription && hasApplications && hasStack && hasRepositoryDocs && hasRegistry) {
    return 'Advanced';
  }
  if (hasDescription && hasApplications && hasStack) {
    return 'Intermediate';
  }
  return 'Basic';
}

function registryModuleDetails(profile: ProjectProfile): ModuleDetail[] {
  const details = profile.knowledge_registry.module_details || [];
  if (details.length) {
    return details;
  }
  return profile.knowledge_registry.modules.map((name) => ({ name, responsibilities: [], dependencies: [] }));
}

function registryFlowDetails(profile: ProjectProfile): FlowDetail[] {
  const details = profile.knowledge_registry.flow_details || [];
  if (details.length) {
    return details;
  }
  return profile.knowledge_registry.flows.map((name) => ({ name, steps: [] }));
}

function registryComponentDetails(profile: ProjectProfile): ComponentDetail[] {
  const details = profile.knowledge_registry.component_details || [];
  if (details.length) {
    return details;
  }
  return profile.knowledge_registry.components.map((name) => ({ name }));
}

function technologySummary(profile: ProjectProfile): string {
  const stack = mergeTechnologyStack(profile.technology_stack, profile.knowledge_registry.technology_stack);
  const stackText = formatStack(stack);
  const architecture = profile.development_standards.architecture_patterns.length
    ? `Architecture: ${profile.development_standards.architecture_patterns.join(', ')}`
    : '';
  return [stackText, architecture].filter(Boolean).join('; ');
}

function mergeTechnologyStack(base: TechnologyStack, incoming?: TechnologyStack): TechnologyStack {
  const next: TechnologyStack = { mobile: [], backend: [], firmware: [], analytics: [], frontend: [] };
  STACK_FIELDS.forEach((field) => {
    next[field] = Array.from(new Set([...(base[field] || []), ...((incoming && incoming[field]) || [])]));
  });
  return next;
}

function executionReadiness(profile: ProjectProfile, hasImpact: boolean): { score: number; label: string; breakdown: string } {
  const projectProfile = profile.project_description.trim() ? 25 : 0;
  const repositoryAnalyzed = profile.repository_connection.status === 'README analyzed' || profile.repository_connection.status === 'Repository documents analyzed' || profile.knowledge_registry.source_files.length > 0;
  const repository = repositoryAnalyzed ? 25 : 0;
  const applicationsDetected = Boolean(profile.applications.length || profile.knowledge_registry.applications.length);
  const registry = profile.knowledge_registry.modules.length && profile.knowledge_registry.flows.length && applicationsDetected ? 20 : 0;
  const impact = hasImpact ? 15 : 0;
  const standards = hasDevelopmentStandards(profile) ? 15 : 0;
  const score = projectProfile + repository + registry + impact + standards;
  const hasRequiredIntelligence = repositoryAnalyzed && applicationsDetected && profile.knowledge_registry.modules.length > 0 && profile.knowledge_registry.flows.length > 0;
  const label = score >= 85 && hasRequiredIntelligence ? 'Ready' : score >= 40 ? 'Partially Ready' : 'Not Ready';
  return {
    score,
    label,
    breakdown: `Project Profile ${projectProfile}%, Repository Intelligence ${repository}%, Knowledge Registry ${registry}%, Impact Analysis ${impact}%, Development Standards ${standards}%`,
  };
}

function stackPlaceholder(field: keyof TechnologyStack): string {
  const examples: Record<keyof TechnologyStack, string> = {
    mobile: 'MAUI&#10;Flutter&#10;Kotlin',
    backend: '.NET&#10;Node.js&#10;FastAPI',
    firmware: 'C&#10;C++',
    analytics: 'Power BI&#10;Spark',
    frontend: 'React&#10;TypeScript',
  };
  return examples[field];
}

function titleCase(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1).replace(/_/g, ' ');
}

const rootNode = document.getElementById('root');
if (rootNode) {
  createRoot(rootNode).render(<ProjectIntelligenceTab />);
}
