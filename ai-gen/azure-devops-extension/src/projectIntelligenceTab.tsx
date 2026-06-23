import * as SDK from 'azure-devops-extension-sdk';
import { CommonServiceIds, IProjectPageService } from 'azure-devops-extension-api/Common/CommonServices';
import { getClient } from 'azure-devops-extension-api/Common/Client';
import { GraphRestClient } from 'azure-devops-extension-api/Graph/GraphClient';
import { GraphTraversalDirection } from 'azure-devops-extension-api/Graph/Graph';
import { GitRepository } from 'azure-devops-extension-api/Git/Git';
import { IWorkItemFormService, WorkItemTrackingServiceIds } from 'azure-devops-extension-api/WorkItemTracking';
import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './storyPlanner.css';

const BASE_URL = 'https://ai-codegen-production.up.railway.app/project-intelligence';

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

type PlannerTab = 'overview' | 'planning' | 'execution' | 'qa' | 'admin';
type AIGenRole = 'admin' | 'contributor' | 'viewer';

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
  knowledge_governance?: KnowledgeGovernance;
  saved_at: string;
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

type ExecutionContextResult = ProviderMetadata & {
  story_summary: string;
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
};

type CopilotContextResult = ProviderMetadata & {
  context: string;
};

type EpicRefinement = ProviderMetadata & {
  business_goal: string;
  business_outcomes: string[];
  users: string[];
  applications: string[];
  constraints: string[];
  risks: string[];
  dependencies: string[];
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
    status?: string;
  }>;
};

type FeatureRefinement = ProviderMetadata & {
  feature_summary: string;
  affected_modules: string[];
  affected_flows: string[];
  dependencies: string[];
  risks: string[];
  recommended_stories: Array<{ title: string; description: string; acceptance_criteria?: string[]; coverage_area?: string }>;
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
  acceptanceCriteriaCount?: number;
  acceptanceCriteriaQualityScore?: number;
  selected: boolean;
  status: 'preview' | 'creating' | 'created' | 'failed' | 'skipped';
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
  const [selectedItemType, setSelectedItemType] = useState<'Epic' | 'Feature' | 'Story' | 'Task'>('Epic');
  const [profile, setProfile] = useState<ProjectProfile>(EMPTY_PROFILE);
  const [storyTitle, setStoryTitle] = useState('');
  const [storyDescription, setStoryDescription] = useState('');
  const [acceptanceCriteria, setAcceptanceCriteria] = useState('');
  const [prompts, setPrompts] = useState<PromptResult | undefined>();
  const [executionContext, setExecutionContext] = useState<ExecutionContextResult | undefined>();
  const [devPrompt, setDevPrompt] = useState<PromptBuilderResult | undefined>();
  const [uiPrompt, setUiPrompt] = useState<PromptBuilderResult | undefined>();
  const [qaPrompt, setQaPrompt] = useState<PromptBuilderResult | undefined>();
  const [copilotContext, setCopilotContext] = useState<CopilotContextResult | undefined>();
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
  const [showResumePanel, setShowResumePanel] = useState(false);
  const [lastAnalysisTimestamp, setLastAnalysisTimestamp] = useState('');
  const [permissionState, setPermissionState] = useState<PermissionState>(defaultPermissionState());
  const [knowledgeGovernance, setKnowledgeGovernance] = useState<KnowledgeGovernance>(() => defaultKnowledgeGovernance(EMPTY_PROFILE, false));
  const [editingProfile, setEditingProfile] = useState(false);
  const [showQuickStart, setShowQuickStart] = useState(true);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState('Loading Project Intelligence...');
  const [error, setError] = useState('');
  const [saveStatus, setSaveStatus] = useState<'saved' | 'saving' | 'unsaved' | 'error'>('saved');
  const initializedRef = useRef(false);
  const lastSavedProfileRef = useRef('');
  const latestProvider = latestProviderMetadata([qaTestSuite, copilotContext, qaPrompt, uiPrompt, devPrompt, executionContext, storyImpact, featureImpact, epicImpact, storyResult, featureResult, epicResult, prompts]);
  const canAdmin = permissionState.role === 'admin';
  const canContribute = permissionState.role === 'admin' || permissionState.role === 'contributor';
  const isViewer = permissionState.role === 'viewer';

  useEffect(() => {
    SDK.init({ loaded: false, applyTheme: true });
    SDK.ready().then(async () => {
      SDK.notifyLoadSucceeded();
      try {
        const storedSession = readProjectSession();
        if (storedSession) {
          setResumeSession(storedSession);
          setLastAnalysisTimestamp(storedSession.last_analysis_timestamp);
          setKnowledgeGovernance(storedSession.knowledge_governance || defaultKnowledgeGovernance(storedSession.profile, false));
        }
        const loaded = await getProfile();
        const projectContext = await loadAzureProjectContext();
        const permissions = await resolveCurrentUserPermission(projectContext);
        setPermissionState(permissions);
        const seeded = storedSession?.profile?.project_name ? storedSession.profile : seedProfileFromAzureProject(loaded, projectContext);
        if (!storedSession?.knowledge_governance) {
          setKnowledgeGovernance(defaultKnowledgeGovernance(seeded, permissions.role === 'admin'));
        }
        const seededChanged = JSON.stringify(seeded) !== JSON.stringify(loaded);
        if (!storedSession && seededChanged) {
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
        if (storedSession?.last_active_tab) {
          setActiveTab(storedSession.last_active_tab === 'admin' && permissions.role !== 'admin' ? 'overview' : storedSession.last_active_tab);
          setShowResumePanel(true);
        }
        setEditingProfile(permissions.role === 'admin' && !seeded.project_name.trim());
        setShowQuickStart(permissions.role === 'admin' && !seeded.project_name.trim() && !seeded.project_description.trim());
        const workItem = await loadCurrentWorkItem();
        if (workItem) {
          setCurrentWorkItem(workItem);
          seedPlannerFromWorkItem(workItem);
        }
        if (storedSession?.profile?.project_name) {
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
    const session = buildProjectSession(profile, activeTab, lastAnalysisTimestamp, nextGovernance);
    writeProjectSession(session);
    setResumeSession(session);
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
  }, [profile, activeTab, lastAnalysisTimestamp, knowledgeGovernance, canAdmin]);

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
      lastSavedProfileRef.current = JSON.stringify(analyzed);
      setSaveStatus('saved');
      setEditingProfile(false);
      setShowQuickStart(false);
      setActiveTab('planning');
    }
  }

  function continueProjectSession() {
    if (resumeSession?.last_active_tab) {
      setActiveTab(resumeSession.last_active_tab);
    }
    if (resumeSession?.profile) {
      setProfile(resumeSession.profile);
    }
    setShowResumePanel(false);
    setEditingProfile(false);
    setShowQuickStart(false);
    setRepositoryLoadMessage('Continuing saved project session. Repository analysis was not rerun.');
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
      setActiveTab('overview');
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

  async function refreshPermissions() {
    const permissions = await withLoading('Refreshing Azure DevOps permissions...', async () => {
      const projectContext = await loadAzureProjectContext();
      return resolveCurrentUserPermission(projectContext);
    });
    if (permissions) {
      setPermissionState(permissions);
    }
  }

  async function generatePrompts() {
    if (!canContribute) {
      setError('Prompt generation is restricted to AI Gen Admins and Contributors.');
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
    }
  }

  async function refineEpic() {
    if (!canContribute) {
      setError('Planning refinement is restricted to AI Gen Admins and Contributors.');
      return;
    }
    const result = await withLoading('Refining epic with Project Intelligence...', () => postJson<EpicRefinement>('/refine-epic', {
      profile,
      knowledge_profile: profile.knowledge_registry,
      epic: epicInput,
    }));
    if (result) {
      setEpicResult(result);
    }
  }

  async function refineFeature() {
    if (!canContribute) {
      setError('Planning refinement is restricted to AI Gen Admins and Contributors.');
      return;
    }
    const result = await withLoading('Refining feature with Project Intelligence...', () => postJson<FeatureRefinement>('/refine-feature', {
      profile,
      knowledge_profile: profile.knowledge_registry,
      feature: featureInput,
    }));
    if (result) {
      setFeatureResult(result);
    }
  }

  async function refineStory() {
    if (!canContribute) {
      setError('Planning refinement is restricted to AI Gen Admins and Contributors.');
      return;
    }
    const result = await withLoading('Refining story with Project Intelligence...', () => postJson<StoryRefinement>('/refine-story', {
      profile,
      knowledge_profile: profile.knowledge_registry,
      story: storyInput,
    }));
    if (result) {
      setStoryResult(result);
    }
  }

  async function generateQATestCases() {
    if (!canContribute) {
      setError('QA generation is restricted to AI Gen Admins and Contributors.');
      return;
    }
    const story = currentStoryPayload();
    const result = await withLoading('Generating QA test cases...', () => postJson<QATestSuiteResult>('/generate-qa-test-cases', {
      profile,
      knowledge_profile: profile.knowledge_registry,
      story,
      impact_analysis: storyImpact || {},
    }));
    if (result) {
      setQaTestSuite(result);
    }
  }

  async function buildExecutionPackage() {
    if (!canContribute) {
      setError('Execution package generation is restricted to AI Gen Admins and Contributors.');
      return;
    }
    const story = currentStoryPayload();
    const packageResult = await withLoading('Generating execution package...', async () => {
      const basePayload = {
        profile,
        knowledge_profile: profile.knowledge_registry,
        story,
        impact_analysis: storyImpact || {},
      };
      const context = await postJson<ExecutionContextResult>('/build-execution-context', basePayload);
      const dev = await postJson<PromptBuilderResult>('/build-dev-prompt', basePayload);
      const ui = await postJson<PromptBuilderResult>('/build-ui-prompt', basePayload);
      const qa = await postJson<PromptBuilderResult>('/build-qa-prompt', basePayload);
      const copilot = await postJson<CopilotContextResult>('/build-copilot-context', basePayload);
      return { context, dev, ui, qa, copilot };
    });
    if (packageResult) {
      setExecutionContext(packageResult.context);
      setDevPrompt(packageResult.dev);
      setUiPrompt(packageResult.ui);
      setQaPrompt(packageResult.qa);
      setCopilotContext(packageResult.copilot);
      setActiveTab('execution');
    }
  }

  function currentStoryPayload(): { title: string; description: string; acceptance_criteria: string[] } {
    return {
      title: storyInput.title || storyTitle || storyResult?.story_summary || 'Approved story',
      description: storyInput.description || storyDescription || storyResult?.story_summary || 'Implement the approved story.',
      acceptance_criteria: splitLines(acceptanceCriteria).length ? splitLines(acceptanceCriteria) : (storyResult?.acceptance_criteria || []),
    };
  }

  function seedPlannerFromWorkItem(workItem: AdoWorkItem) {
    const type = normalizePlannerItemType(workItem.type);
    setSelectedItemType(type);
    if (type === 'Epic') {
      setEpicInput({ title: workItem.title, description: htmlToText(workItem.description) });
    } else if (type === 'Feature') {
      setFeatureInput({ title: workItem.title, description: htmlToText(workItem.description) });
    } else {
      setStoryInput({ title: workItem.title, description: htmlToText(workItem.description) });
      setAcceptanceCriteria(htmlToText(workItem.acceptanceCriteria));
    }
  }

  function updateDraftSelection(draftId: string, selected: boolean) {
    setChildDrafts((current) => current.map((draft) => draft.id === draftId ? { ...draft, selected } : draft));
  }

  async function generateChildrenForCurrentType() {
    if (!canContribute) {
      setError('Planning generation is restricted to AI Gen Admins and Contributors.');
      return;
    }
    if (currentWorkItem?.state.toLowerCase() === 'closed') {
      setError('This work item is Closed. AI Planner is read-only for closed items.');
      return;
    }
    if (currentWorkItem?.state.toLowerCase() === 'active') {
      const confirmed = window.confirm('This work item is Active. Regenerating planning output may affect in-progress work. Continue?');
      if (!confirmed) {
        return;
      }
    }
    if (selectedItemType === 'Epic') {
      const generated = await withLoading('Generating Features from Epic...', () => postJson<EpicRefinement>('/refine-epic', {
        profile,
        knowledge_profile: profile.knowledge_registry,
        epic: epicInput,
      }));
      if (!generated) return;
      setEpicResult(generated);
      setChildDrafts(featureDraftsFromEpic(generated));
    } else if (selectedItemType === 'Feature') {
      const generated = await withLoading('Generating Stories from Feature...', () => postJson<FeatureRefinement>('/refine-feature', {
        profile,
        knowledge_profile: profile.knowledge_registry,
        feature: featureInput,
      }));
      if (!generated) return;
      setFeatureResult(generated);
      setChildDrafts(storyDraftsFromFeature(generated));
    } else if (selectedItemType === 'Story') {
      const generated = await withLoading('Generating Tasks from Story...', () => postJson<StoryRefinement>('/refine-story', {
        profile,
        knowledge_profile: profile.knowledge_registry,
        story: { ...storyInput, acceptance_criteria: splitLines(acceptanceCriteria) },
      }));
      if (!generated) return;
      setStoryResult(generated);
      setChildDrafts(taskDraftsFromStory(generated));
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
    const selected = childDrafts.filter((draft) => draft.selected && draft.status !== 'created');
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
    return postJson<ProjectProfile>('/repository/analyze', {
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

  return (
    <main className="planner-shell">
      <header className="planner-header">
        <div className="planner-header-brand">
          <img className="planner-header-logo" src="static/hei-logo.png" alt="Hubbell Engineering Intelligence" />
          <div className="planner-header-copy">
            <div className="planner-eyebrow">Hubbell Planning & Engineering Intelligence Platform</div>
            <div className="planner-title">Project Intelligence</div>
            <div className="planner-subtitle">
              {editingProfile
                ? 'Connect the project once. The platform turns repository knowledge into planning, execution, and QA context.'
                : 'Project-aware planning, execution packages, and QA coverage for enterprise delivery teams.'}
            </div>
            <div className={`planner-save-status ${saveStatus}`}>{saveStatusLabel(saveStatus)}</div>
          </div>
        </div>
        <div className="planner-header-actions">
          <RoleBadge permission={permissionState} />
          {canAdmin ? (
            <button
              className="planner-button secondary"
              onClick={() => {
                const next = !(editingProfile || showQuickStart);
                setEditingProfile(next);
                setShowQuickStart(next);
              }}
              disabled={loading}
            >
              {editingProfile || showQuickStart ? 'Hide Setup' : 'Edit Project Profile'}
            </button>
          ) : null}
        </div>
      </header>

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

      <WorkflowTabs activeTab={activeTab} onChange={setActiveTab} canAdmin={canAdmin} />

      {activeTab === 'overview' ? (
        <>
          <ProductIdentityCard profile={profile} />
          <EnterpriseReadinessCard profile={profile} qaReady={Boolean(qaTestSuite)} executionReady={Boolean(executionContext)} />
          {showQuickStart && canAdmin ? (
            <QuickStartSetup
              profile={profile}
              adoProjects={adoProjects}
              repositories={repositories}
              branches={branches}
              repositoryLoadMessage={repositoryLoadMessage}
              loading={loading}
              onProfileChange={setProfile}
              onSelectAdoProject={(adoProject) => void selectAdoProject(adoProject)}
              onSelectRepository={(repositoryId) => void selectRepository(repositoryId)}
              onReloadRepositories={() => void loadAdoProjects()}
              onAnalyzeProject={() => void analyzeProject()}
            />
          ) : null}
          <div className="planner-two-column">
            {canAdmin ? (
              <RepositoryIntelligenceCard
                profile={profile}
                adoProjects={adoProjects}
                repositories={repositories}
                branches={branches}
                repositoryLoadMessage={repositoryLoadMessage}
                repositoryDocuments={repositoryDocuments}
                fileStatus={repositoryFileStatus}
                selectedFiles={selectedRepositoryFiles}
                loading={loading}
                showConnectionControls={!showQuickStart}
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
                governance={knowledgeGovernance}
              />
            ) : (
              <RepositoryReadOnlyCard profile={profile} governance={knowledgeGovernance} />
            )}
            <KnowledgeProfilePreview profile={profile} governance={knowledgeGovernance} canAdmin={canAdmin} />
          </div>
          <KnowledgeGovernanceCard governance={knowledgeGovernance} canAdmin={canAdmin} />
          {canAdmin ? (
            <details className="planner-card">
              <summary className="planner-label">Advanced Manual Profile Fields</summary>
              <div className="planner-subtle">Optional fallback fields. Repository intelligence should be the preferred source for modules, flows, architecture notes, and standards.</div>
              <OnboardingForm
                profile={profile}
                loading={loading}
                onProfileChange={setProfile}
                onAnalyze={() => void analyzeDescription()}
                onSave={() => void saveProfile()}
              />
            </details>
          ) : null}
          <StandardsAndGuidelinesSummary profile={profile} />
          <RecentActivityCard currentWorkItem={currentWorkItem} profile={profile} hasQa={Boolean(qaTestSuite)} hasExecution={Boolean(executionContext)} />
          <RoadmapCard />
          <ProjectIntelligenceProviderDiagnostics metadata={latestProvider} />
        </>
      ) : null}

      {activeTab === 'planning' ? (
        <AIPlannerWorkspace
          profile={profile}
          loading={loading}
          currentWorkItem={currentWorkItem}
          childDrafts={childDrafts}
          creationLog={creationLog}
          providerMetadata={latestProvider}
          canContribute={canContribute}
          selectedItemType={selectedItemType}
          onItemTypeChange={setSelectedItemType}
          epicInput={epicInput}
          featureInput={featureInput}
          storyInput={storyInput}
          acceptanceCriteria={acceptanceCriteria}
          epicResult={epicResult}
          featureResult={featureResult}
          storyResult={storyResult}
          setEpicInput={setEpicInput}
          setFeatureInput={setFeatureInput}
          setStoryInput={setStoryInput}
          setAcceptanceCriteria={setAcceptanceCriteria}
          refineEpic={() => void refineEpic()}
          refineFeature={() => void refineFeature()}
          refineStory={() => void refineStory()}
          generateChildren={() => void generateChildrenForCurrentType()}
          updateDraftSelection={updateDraftSelection}
          createSelectedChildren={() => void createSelectedChildWorkItems()}
          buildExecutionPackage={() => void buildExecutionPackage()}
          generateQATestCases={() => void generateQATestCases()}
          qaTestSuite={qaTestSuite}
        />
      ) : null}

      {activeTab === 'execution' ? (
        <DeveloperWorkspace
          executionContext={executionContext}
          devPrompt={devPrompt}
          uiPrompt={uiPrompt}
          qaPrompt={qaPrompt}
          copilotContext={copilotContext}
          onGenerate={() => void buildExecutionPackage()}
          loading={loading}
          canContribute={canContribute}
        />
      ) : null}

      {activeTab === 'qa' ? (
        <QAWorkspace
          loading={loading}
          storyInput={storyInput}
          acceptanceCriteria={acceptanceCriteria}
          setStoryInput={setStoryInput}
          setAcceptanceCriteria={setAcceptanceCriteria}
          qaTestSuite={qaTestSuite}
          generateQATestCases={() => void generateQATestCases()}
          canContribute={canContribute}
        />
      ) : null}

      {activeTab === 'admin' && canAdmin ? (
        <AdminWorkspace permission={permissionState} profile={profile} governance={knowledgeGovernance} onRefreshPermissions={() => void refreshPermissions()} />
      ) : null}
    </main>
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
    { id: 'overview', label: 'Overview', subtitle: 'Readiness and knowledge' },
    { id: 'planning', label: 'Planning', subtitle: 'Epic to task workflow' },
    { id: 'execution', label: 'Execution', subtitle: 'Developer packages' },
    { id: 'qa', label: 'QA', subtitle: 'Coverage and test cases' },
    ...(canAdmin ? [{ id: 'admin' as PlannerTab, label: 'Admin', subtitle: 'Permissions and setup' }] : []),
  ];
  return (
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
  );
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
  onRefreshPermissions,
}: {
  permission: PermissionState;
  profile: ProjectProfile;
  governance: KnowledgeGovernance;
  onRefreshPermissions: () => void;
}) {
  return (
    <>
      <section className="planner-card">
        <div className="planner-section-header">
          <div>
            <div className="planner-label">Admin Tab</div>
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
      </section>
      <section className="planner-card">
        <div className="planner-label">Permissions Mapping</div>
        <div className="planner-status-grid">
          <Row label="Project Administrators" value="AI Gen Admin: Project Profile, Repository Mapping, Knowledge Refresh, Standards, Theme Settings" />
          <Row label="Contributors" value="AI Gen Contributor: Planning, Execution, QA" />
          <Row label="Readers" value="AI Gen Viewer: Read-only access" />
        </div>
      </section>
      <section className="planner-card">
        <div className="planner-label">Detected Azure DevOps Groups</div>
        {permission.azure_groups.length ? <ChipList items={permission.azure_groups} /> : <div className="planner-subtle">No Azure DevOps groups were visible to this extension session.</div>}
      </section>
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
  selectedItemType,
  onItemTypeChange,
  epicInput,
  featureInput,
  storyInput,
  acceptanceCriteria,
  epicResult,
  featureResult,
  storyResult,
  qaTestSuite,
  setEpicInput,
  setFeatureInput,
  setStoryInput,
  setAcceptanceCriteria,
  refineEpic,
  refineFeature,
  refineStory,
  generateChildren,
  updateDraftSelection,
  createSelectedChildren,
  buildExecutionPackage,
  generateQATestCases,
}: {
  profile: ProjectProfile;
  loading: boolean;
  currentWorkItem?: AdoWorkItem;
  childDrafts: ChildDraft[];
  creationLog: string[];
  providerMetadata?: ProviderMetadata;
  canContribute: boolean;
  selectedItemType: 'Epic' | 'Feature' | 'Story' | 'Task';
  onItemTypeChange: (type: 'Epic' | 'Feature' | 'Story' | 'Task') => void;
  epicInput: { title: string; description: string };
  featureInput: { title: string; description: string };
  storyInput: { title: string; description: string };
  acceptanceCriteria: string;
  epicResult?: EpicRefinement;
  featureResult?: FeatureRefinement;
  storyResult?: StoryRefinement;
  qaTestSuite?: QATestSuiteResult;
  setEpicInput: (value: { title: string; description: string }) => void;
  setFeatureInput: (value: { title: string; description: string }) => void;
  setStoryInput: (value: { title: string; description: string }) => void;
  setAcceptanceCriteria: (value: string) => void;
  refineEpic: () => void;
  refineFeature: () => void;
  refineStory: () => void;
  generateChildren: () => void;
  updateDraftSelection: (draftId: string, selected: boolean) => void;
  createSelectedChildren: () => void;
  buildExecutionPackage: () => void;
  generateQATestCases: () => void;
}) {
  const readOnly = !canContribute || currentWorkItem?.state.toLowerCase() === 'closed';
  return (
    <>
      <WorkItemContextCard workItem={currentWorkItem} />
      <section className="planner-card">
        <div className="planner-label">Planning Workflow</div>
        <div className="planner-subtle">Work through planning in delivery order: Epic, Feature, Story, then Task execution.</div>
        <KnowledgeRegistryNotice profile={profile} />
        {!profileCompletion(profile).complete ? (
          <div className="planner-banner">Project profile is incomplete. Results may be less accurate, but you can continue planning.</div>
        ) : null}
        {readOnly ? <div className="planner-error">This work item is Closed. Planning output is read-only.</div> : null}
        {currentWorkItem?.state.toLowerCase() === 'active' ? <div className="planner-banner">This work item is Active. AI Planner will ask before regeneration.</div> : null}
        <div className="planner-pill-row">
          {(['Epic', 'Feature', 'Story', 'Task'] as const).map((type) => (
            <button
              key={type}
              type="button"
              className={`planner-pill ${selectedItemType === type ? 'active' : ''}`}
              onClick={() => onItemTypeChange(type)}
            >
              {type}
            </button>
          ))}
        </div>
      </section>

      {selectedItemType === 'Epic' ? (
        <section className="planner-card">
          <div className="planner-label">Epic Workflow</div>
          <div className="planner-subtle">Refine the epic goal, then generate project-aware feature recommendations.</div>
          <RefinementInput input={epicInput} setInput={setEpicInput} titlePlaceholder="Launch mobile commerce platform" descriptionPlaceholder="Describe the epic goal, users, rollout intent, and business context." />
          <div className="planner-actions">
            <button className="planner-button secondary" onClick={refineEpic} disabled={loading || readOnly || !epicInput.title.trim()}>Refine Epic</button>
            <button className="planner-button" onClick={generateChildren} disabled={loading || readOnly || !epicInput.title.trim()}>Generate Features</button>
          </div>
          {epicResult ? (
            <div className="planner-status-grid">
              <EpicRefinementResult result={epicResult} />
              <CardList title="Generated Features" items={epicResult.recommended_features} />
            </div>
          ) : null}
        </section>
      ) : null}

      {selectedItemType === 'Feature' ? (
        <section className="planner-card">
          <div className="planner-label">Feature Workflow</div>
          <div className="planner-subtle">Refine the feature and generate meaningful stories from project modules and flows.</div>
          <RefinementInput input={featureInput} setInput={setFeatureInput} titlePlaceholder="Order visibility" descriptionPlaceholder="Describe feature behavior, affected users, and delivery scope." />
          <div className="planner-actions">
            <button className="planner-button secondary" onClick={refineFeature} disabled={loading || readOnly || !featureInput.title.trim()}>Refine Feature</button>
            <button className="planner-button" onClick={generateChildren} disabled={loading || readOnly || !featureInput.title.trim()}>Generate Stories</button>
          </div>
          {featureResult ? (
            <div className="planner-status-grid">
              <FeatureRefinementResult result={featureResult} />
              <CardList title="Generated Stories" items={featureResult.recommended_stories} />
            </div>
          ) : null}
        </section>
      ) : null}

      {selectedItemType === 'Story' ? (
        <section className="planner-card">
          <div className="planner-label">Story Workflow</div>
          <div className="planner-subtle">Refine the story, acceptance criteria, affected areas, and proposed implementation tasks.</div>
          <RefinementInput input={storyInput} setInput={setStoryInput} titlePlaceholder="Track order delivery status" descriptionPlaceholder="Describe the story, user outcome, and acceptance expectations." />
          <textarea
            className="planner-textarea compact"
            value={acceptanceCriteria}
            onChange={(event) => setAcceptanceCriteria(event.target.value)}
            placeholder="Acceptance criteria, one per line"
          />
          <div className="planner-actions">
            <button className="planner-button secondary" onClick={refineStory} disabled={loading || readOnly || !storyInput.title.trim()}>Refine Story</button>
            <button className="planner-button" onClick={generateChildren} disabled={loading || readOnly || !storyInput.title.trim()}>Generate Tasks</button>
            <button className="planner-button secondary" onClick={generateQATestCases} disabled={loading || readOnly || !storyInput.title.trim()}>Generate Test Cases</button>
            <button className="planner-button secondary" onClick={buildExecutionPackage} disabled={loading || readOnly || !storyInput.title.trim()}>Generate Execution Package</button>
          </div>
          {storyResult ? (
            <div className="planner-status-grid">
              <StoryRefinementResult result={storyResult} />
              <GeneratedTasksPreview story={storyResult} />
            </div>
          ) : null}
          {qaTestSuite ? <QAIntelligencePanel result={qaTestSuite} /> : null}
        </section>
      ) : null}

      {selectedItemType === 'Task' ? (
        <section className="planner-card">
          <div className="planner-label">Task Workflow</div>
          <div className="planner-subtle">Generate execution context and prompts for a developer workspace.</div>
          <RefinementInput input={storyInput} setInput={setStoryInput} titlePlaceholder="Implement approved story task" descriptionPlaceholder="Describe the task or approved story scope." />
          <textarea
            className="planner-textarea compact"
            value={acceptanceCriteria}
            onChange={(event) => setAcceptanceCriteria(event.target.value)}
            placeholder="Acceptance criteria or task validation notes, one per line"
          />
          <div className="planner-actions">
            <button className="planner-button" onClick={buildExecutionPackage} disabled={loading || readOnly || !storyInput.title.trim()}>Generate Execution Package</button>
          </div>
          {storyResult ? <GeneratedTasksPreview story={storyResult} /> : null}
        </section>
      ) : null}
      <GeneratedChildWorkItems
        drafts={childDrafts}
        creationLog={creationLog}
        currentWorkItem={currentWorkItem}
        providerMetadata={providerMetadata}
        readOnly={!canContribute}
        loading={loading}
        onSelectionChange={updateDraftSelection}
        onCreateSelected={createSelectedChildren}
      />
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
      {drafts.map((draft) => (
        <div className="planner-task" key={draft.id}>
          <label className="planner-checkbox">
            <input
              type="checkbox"
              checked={draft.selected}
              disabled={readOnly || draft.status === 'created'}
              onChange={(event) => onSelectionChange(draft.id, event.target.checked)}
            />
            <strong>{draft.type}: {draft.title}</strong>
          </label>
          <span>{draft.description}</span>
          <FeatureEnrichmentDetails draft={draft} />
          <ListBlock title="Acceptance Criteria" items={draft.acceptanceCriteria} />
          <div className="planner-subtle">
            Status: {draft.status}
            {draft.azureId ? ` #${draft.azureId}` : ''}
            {draft.error ? ` - ${draft.error}` : ''}
          </div>
        </div>
      ))}
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
  const categories = Array.from(new Set(cases.map((test) => test.category)));
  return (
    <section className="planner-card">
      <div className="planner-label">QA Intelligence</div>
      <div className="planner-subtle">Generated structured test cases from the story, acceptance criteria, modules, flows, dependencies, and domain.</div>
      <SourceBadge metadata={result} />
      <div className="planner-status-grid">
        <Row label="Test Suite" value={result.test_suite?.title || 'QA Test Suite'} />
        <Row label="Coverage Score" value={formatNumber(result.coverage_score)} />
        <Row label="Coverage %" value={`${formatNumber(result.coverage_summary?.coverage_percent)}%`} />
        <Row label="Generated Test Count" value={formatNumber(result.generated_test_count || cases.length)} />
        <Row label="Covered Acceptance Criteria" value={`${formatNumber(result.coverage_summary?.covered_acceptance_criteria_count)} / ${formatNumber(result.coverage_summary?.acceptance_criteria_count)}`} />
      </div>
      <div className="planner-status-grid">
        <Row label="Positive Tests" value={formatNumber(result.coverage_breakdown?.positive_coverage)} />
        <Row label="Negative Tests" value={formatNumber(result.coverage_breakdown?.negative_coverage)} />
        <Row label="Boundary Tests" value={formatNumber(result.coverage_breakdown?.boundary_coverage)} />
        <Row label="Permission Tests" value={formatNumber(result.coverage_breakdown?.permission_coverage)} />
        <Row label="Error Tests" value={formatNumber(result.coverage_breakdown?.error_coverage)} />
        <Row label="Regression Candidates" value={formatNumber(result.coverage_breakdown?.regression_coverage)} />
      </div>
      <ListBlock title="Coverage Gaps" items={result.coverage_gaps || []} />
      {categories.map((category) => (
        <div className="planner-task" key={category}>
          <div className="planner-label">{category}</div>
          {cases.filter((test) => test.category === category).map((test) => (
            <div className="planner-task" key={test.test_id}>
              <strong>{test.test_id}: {test.title}</strong>
              <Row label="Priority" value={test.priority} />
              <Row label="Risk Level" value={test.risk_level} />
              <ListBlock title="Preconditions" items={test.preconditions || []} />
              <ListBlock title="Steps" items={test.steps || []} />
              <Row label="Expected Result" value={test.expected_result} />
            </div>
          ))}
        </div>
      ))}
    </section>
  );
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
  devPrompt,
  uiPrompt,
  qaPrompt,
  copilotContext,
  onGenerate,
  loading,
  canContribute,
}: {
  executionContext?: ExecutionContextResult;
  devPrompt?: PromptBuilderResult;
  uiPrompt?: PromptBuilderResult;
  qaPrompt?: PromptBuilderResult;
  copilotContext?: CopilotContextResult;
  onGenerate: () => void;
  loading: boolean;
  canContribute: boolean;
}) {
  const hasPackage = Boolean(executionContext || devPrompt || uiPrompt || qaPrompt || copilotContext);
  const vsCodeUri = executionContext ? buildVsCodeExecutionPackageUri(executionContext, devPrompt, uiPrompt, qaPrompt, copilotContext) : '';
  return (
    <>
      <section className="planner-card">
        <div className="planner-label">Developer Workspace</div>
        <div className="planner-subtle">Execution-ready context for VS Code, Copilot, or manual implementation.</div>
        <div className="planner-actions">
          <button className="planner-button" onClick={onGenerate} disabled={loading || !canContribute}>Generate Execution Package</button>
          {vsCodeUri ? (
            <button className="planner-button secondary" onClick={() => window.open(vsCodeUri, '_blank')} disabled={loading}>Open in VS Code</button>
          ) : null}
        </div>
      </section>
      {!hasPackage ? (
        <section className="planner-card">
          <div className="planner-subtle">No execution package generated yet. Generate one from the Story or Task workflow.</div>
        </section>
      ) : null}
      {executionContext ? <ExecutionContextBlock context={executionContext} /> : null}
      {devPrompt ? <PromptBlock title="Dev Prompt" value={devPrompt.prompt} metadata={devPrompt} copyable /> : null}
      {uiPrompt ? <PromptBlock title="UI Prompt" value={uiPrompt.prompt} metadata={uiPrompt} copyable /> : null}
      {qaPrompt ? <PromptBlock title="QA Prompt" value={qaPrompt.prompt} metadata={qaPrompt} copyable /> : null}
      {copilotContext ? (
        <div className="planner-task">
          <div className="planner-label">Copilot Context</div>
          <SourceBadge metadata={copilotContext} />
          <div className="planner-actions">
            <button className="planner-button secondary" onClick={() => void copyText(copilotContext.context)}>Copy</button>
          </div>
          <pre className="planner-prompt">{copilotContext.context}</pre>
        </div>
      ) : null}
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
  generateQATestCases,
  canContribute,
}: {
  loading: boolean;
  storyInput: { title: string; description: string };
  acceptanceCriteria: string;
  setStoryInput: (value: { title: string; description: string }) => void;
  setAcceptanceCriteria: (value: string) => void;
  qaTestSuite?: QATestSuiteResult;
  generateQATestCases: () => void;
  canContribute: boolean;
}) {
  return (
    <>
      <section className="planner-card">
        <div className="planner-section-header">
          <div>
            <div className="planner-label">QA Workspace</div>
            <div className="planner-subtle">Generate structured test cases, coverage analysis, regression scope, and QA readiness from an approved story.</div>
          </div>
          <button className="planner-button" onClick={generateQATestCases} disabled={loading || !canContribute || !storyInput.title.trim()}>Generate Test Cases</button>
        </div>
        <RefinementInput input={storyInput} setInput={setStoryInput} titlePlaceholder="Open critical fault event details" descriptionPlaceholder="Story description or outcome for QA validation." />
        <textarea
          className="planner-textarea compact"
          value={acceptanceCriteria}
          onChange={(event) => setAcceptanceCriteria(event.target.value)}
          placeholder="Acceptance criteria, one per line"
        />
      </section>
      {qaTestSuite ? <QAIntelligencePanel result={qaTestSuite} /> : (
        <section className="planner-card">
          <div className="planner-label">QA Readiness</div>
          <div className="planner-subtle">No test suite generated yet. Add or load a story, then generate test cases.</div>
          <div className="planner-summary-grid">
            <SummaryTile title="Test Case Generator" value="Ready" />
            <SummaryTile title="Coverage Analysis" value="Ready" />
            <SummaryTile title="Regression Scope" value="Ready" />
            <SummaryTile title="Defect Radar" value="Coming next" />
          </div>
        </section>
      )}
    </>
  );
}

function ExecutionContextBlock({ context }: { context: ExecutionContextResult }) {
  return (
    <section className="planner-card">
      <div className="planner-label">Execution Context</div>
      <SourceBadge metadata={context} />
      <div className="planner-status-grid">
        <Row label="Story Summary" value={context.story_summary || 'Not generated yet'} />
        <Row label="Execution Readiness" value={`${context.execution_readiness_result || context.execution_readiness || 'Not assessed'} (${context.execution_readiness_score || 0}%)`} />
        <Row label="Technology Stack" value={formatStack(context.technology_stack || EMPTY_STACK) || 'Not captured'} />
      </div>
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
      </div>
      {context.proposed_tasks?.length ? (
        <div className="planner-task">
          <div className="planner-label">Task Intelligence</div>
          <StructuredTaskList tasks={context.proposed_tasks} />
        </div>
      ) : null}
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
        <div className="planner-document-list">
          {documents.map((doc) => (
            <div className="planner-document-row" key={doc.label}>
              <span className={`planner-document-state ${doc.status}`}>{doc.status === 'available' ? '✓' : '⚠'}</span>
              <div>
                <strong>{doc.label}</strong>
                <small>{doc.path || 'Not Found'}</small>
              </div>
            </div>
          ))}
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
        <Row label="Context Size" value={formatNumber(metadata?.context_size)} />
        <Row label="Context After Compression" value={formatNumber(metadata?.context_after_compression)} />
        <Row label="Tokens Sent" value={metadata?.tokens_sent ? `${metadata.tokens_sent} / ${metadata.context_budget_tokens || 2500}` : 'n/a'} />
        <Row label="Model Limit" value={formatNumber(metadata?.model_context_limit)} />
        <Row label="Reserved Tokens" value={formatNumber(metadata?.reserved_tokens)} />
        <Row label="Compression Ratio" value={metadata?.compression_ratio !== undefined ? `${Math.round(metadata.compression_ratio * 100)}%` : 'n/a'} />
        <Row label="Final Prompt Tokens" value={metadata?.final_prompt_tokens ? `${metadata.final_prompt_tokens} / ${metadata.model_context_limit || 'n/a'}` : 'n/a'} />
        <Row label="Project Context Tokens" value={formatNumber(metadata?.project_context_tokens || metadata?.compressed_context_tokens)} />
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
        {featureResult ? <FeatureRefinementResult result={featureResult} /> : null}
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

function FeatureRefinementResult({ result }: { result: FeatureRefinement }) {
  const diagnostics = result.story_generation_diagnostics || {};
  return (
    <div className="planner-status-grid">
      <SourceBadge metadata={result} />
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

function StoryRefinementResult({ result }: { result: StoryRefinement }) {
  return (
    <div className="planner-status-grid">
      <SourceBadge metadata={result} />
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

function ListBlock({ title, items }: { title: string; items: string[] }) {
  const normalizedItems = Array.isArray(items) ? items : [String(items || '')].filter(Boolean);
  return (
    <div className="planner-task">
      <div className="planner-label">{title}</div>
      <ul className="planner-list">
        {(normalizedItems.length ? normalizedItems : ['Not identified yet']).map((item) => <li key={item}>{item}</li>)}
      </ul>
    </div>
  );
}

function CardList({ title, items }: { title: string; items: Array<{ title: string; description: string }> }) {
  return (
    <div className="planner-task">
      <div className="planner-label">{title}</div>
      {(items.length ? items : [{ title: 'No recommendation', description: 'Add more project or repository context.' }]).map((item) => (
        <div className="planner-task" key={item.title}>
          <strong>{item.title}</strong>
          <span>{item.description}</span>
        </div>
      ))}
    </div>
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
          <PromptBlock title="UI Prompt" value={prompts.ui_prompt} metadata={prompts} />
          <PromptBlock title="Dev Prompt" value={prompts.dev_prompt} metadata={prompts} />
          <PromptBlock title="QA Prompt" value={prompts.qa_prompt} metadata={prompts} />
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
            <li>Execution Packages</li>
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

function SummaryTile({ title, value }: { title: string; value: string }) {
  return (
    <div className="planner-summary-tile">
      <span>{title}</span>
      <strong>{value || 'Pending'}</strong>
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
  devPrompt?: PromptBuilderResult,
  uiPrompt?: PromptBuilderResult,
  qaPrompt?: PromptBuilderResult,
  copilotContext?: CopilotContextResult,
): string {
  const payload = {
    execution_context: executionContext,
    dev_prompt: devPrompt?.prompt || '',
    ui_prompt: uiPrompt?.prompt || '',
    qa_prompt: qaPrompt?.prompt || '',
    copilot_context: copilotContext?.context || '',
  };
  const params = new URLSearchParams({
    payload: btoa(unescape(encodeURIComponent(JSON.stringify(payload)))),
  });
  return `vscode://rathiesh.ai-gen-vscode/loadExecutionPackage?${params.toString()}`;
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

function featureDraftsFromEpic(result: EpicRefinement): ChildDraft[] {
  return result.recommended_features.map((feature, index) => ({
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
    acceptanceCriteria: story.acceptance_criteria?.length ? story.acceptance_criteria : [`${story.title} is visible, independently testable, and supports the approved user outcome.`],
    selected: true,
    status: 'preview',
  }));
}

function taskDraftsFromStory(result: StoryRefinement): ChildDraft[] {
  const tasks = result.proposed_tasks?.length ? result.proposed_tasks : fallbackStoryTasks(result);
  return tasks.map((task, index) => ({
    id: `task_${index + 1}`,
    type: 'Task',
    title: cleanGeneratedTitle(`${task.work_area ? `${task.work_area}: ` : ''}${task.title}`),
    description: task.description,
    acceptanceCriteria: task.acceptance_criteria?.length ? task.acceptance_criteria : result.acceptance_criteria,
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

function normalizePlannerItemType(type: string): 'Epic' | 'Feature' | 'Story' | 'Task' {
  const normalized = type.toLowerCase();
  if (normalized.includes('epic')) return 'Epic';
  if (normalized.includes('feature')) return 'Feature';
  if (normalized.includes('task')) return 'Task';
  return 'Story';
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

function defaultPermissionState(): PermissionState {
  return {
    role: 'viewer',
    user_display_name: '',
    user_name: '',
    mapped_group: 'Readers',
    azure_groups: [],
    status: 'fallback',
    warning: 'Azure DevOps group membership has not been resolved yet.',
  };
}

async function resolveCurrentUserPermission(projectContext?: AzureProjectContext): Promise<PermissionState> {
  const user = SDK.getUser();
  const userAny = user as typeof user & { subjectId?: string; uniqueName?: string; email?: string };
  try {
    const graphClient = getClient(GraphRestClient);
    const descriptor = await resolveUserGraphDescriptor(graphClient, userAny);
    let groupNames: string[] = [];
    if (descriptor) {
      groupNames = await collectAzureDevOpsGroupNames(graphClient, descriptor);
      if (!groupNames.length) {
        groupNames = await collectGroupsViaRestApi(descriptor);
      }
    }
    if (groupNames.length) {
      const mapping = mapGroupsToAIGenRole(groupNames, projectContext?.name || '');
      return {
        role: mapping.role,
        user_display_name: user.displayName || user.name || '',
        user_name: userAny.uniqueName || userAny.email || user.name || '',
        mapped_group: mapping.group,
        azure_groups: groupNames,
        status: 'resolved',
        warning: undefined,
        diagnostics: mapping.diagnostics,
      };
    }
    const ownerFallback = inferProjectOwnerPermission(userAny);
    if (ownerFallback) {
      return ownerFallback;
    }
    return {
      role: 'viewer',
      user_display_name: user.displayName || user.name || '',
      user_name: userAny.uniqueName || userAny.email || user.name || '',
      mapped_group: 'Readers',
      azure_groups: [],
      status: 'fallback',
      warning: descriptor
        ? 'Azure DevOps group membership returned no visible groups. Viewer access is applied.'
        : 'Azure DevOps user descriptor could not be resolved. Viewer access is applied.',
    };
  } catch (error) {
    const ownerFallback = inferProjectOwnerPermission(userAny);
    if (ownerFallback) {
      return {
        ...ownerFallback,
        warning: `${ownerFallback.warning} Graph lookup failed: ${error instanceof Error ? error.message : String(error)}`,
      };
    }
    return {
      role: 'viewer',
      user_display_name: user.displayName || user.name || '',
      user_name: userAny.uniqueName || userAny.email || user.name || '',
      mapped_group: 'Readers',
      azure_groups: [],
      status: 'fallback',
      warning: `Could not resolve Azure DevOps group membership. Viewer access is applied. ${error instanceof Error ? error.message : String(error)}`,
    };
  }
}

async function resolveUserGraphDescriptor(
  graphClient: GraphRestClient,
  user: { id?: string; descriptor?: string; subjectId?: string; name?: string; uniqueName?: string; email?: string },
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
  const accountName = String(SDK.getHost()?.name || '').toLowerCase();
  const identifiers = [user.uniqueName, user.email, user.name].map((value) => String(value || '').toLowerCase());
  const ownsOrganization = Boolean(accountName && identifiers.some((identifier) => identifier.startsWith(`${accountName}@`) || identifier === accountName));
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
      matched_groups: ['Project Administrators'],
      matched_roles: ['admin'],
      selected_role: 'admin',
      precedence_rule: 'organization_owner_fallback',
    },
  };
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
      const match = normalized.includes('project administrators');
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
      knowledge_governance: parsed.knowledge_governance,
      saved_at: parsed.saved_at || new Date().toISOString(),
    };
  } catch {
    return undefined;
  }
}

function writeProjectSession(session: ProjectSessionSnapshot): void {
  try {
    window.localStorage.setItem(PROJECT_SESSION_STORAGE_KEY, JSON.stringify(session));
  } catch {
    // Local persistence is best-effort; backend autosave still owns profile durability.
  }
}

function buildProjectSession(profile: ProjectProfile, activeTab: PlannerTab, lastAnalysisTimestamp: string, governance: KnowledgeGovernance): ProjectSessionSnapshot {
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
    knowledge_governance: governance,
    saved_at: now,
  };
}

function isPlannerTab(value: unknown): value is PlannerTab {
  return value === 'overview' || value === 'planning' || value === 'execution' || value === 'qa';
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
    { label: 'Execution Package Support', ready: true },
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
      detail: setup.complete ? (executionReady ? 'Execution package generated' : 'Ready to generate execution packages') : 'Complete project setup first',
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
