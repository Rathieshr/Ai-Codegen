import * as SDK from 'azure-devops-extension-sdk';
import { CommonServiceIds, IProjectPageService } from 'azure-devops-extension-api/Common/CommonServices';
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
  recommended_features: Array<{ title: string; description: string; acceptance_criteria?: string[] }>;
};

type FeatureRefinement = ProviderMetadata & {
  feature_summary: string;
  affected_modules: string[];
  affected_flows: string[];
  dependencies: string[];
  risks: string[];
  recommended_stories: Array<{ title: string; description: string }>;
};

type StoryRefinement = ProviderMetadata & {
  story_summary: string;
  acceptance_criteria: string[];
  affected_applications: string[];
  affected_modules: string[];
  affected_flows: string[];
  dependencies: string[];
  risks: string[];
  ui_considerations: string[];
  technical_considerations: string[];
  qa_considerations: string[];
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
  const [activeTab, setActiveTab] = useState<'project' | 'planner' | 'developer'>('project');
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
  const [editingProfile, setEditingProfile] = useState(false);
  const [showQuickStart, setShowQuickStart] = useState(true);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState('Loading Project Intelligence...');
  const [error, setError] = useState('');
  const [saveStatus, setSaveStatus] = useState<'saved' | 'saving' | 'unsaved' | 'error'>('saved');
  const initializedRef = useRef(false);
  const lastSavedProfileRef = useRef('');
  const latestProvider = latestProviderMetadata([copilotContext, qaPrompt, uiPrompt, devPrompt, executionContext, storyImpact, featureImpact, epicImpact, storyResult, featureResult, epicResult, prompts]);

  useEffect(() => {
    SDK.init({ loaded: false, applyTheme: true });
    SDK.ready().then(async () => {
      SDK.notifyLoadSucceeded();
      try {
        const loaded = await getProfile();
        const projectContext = await loadAzureProjectContext();
        const seeded = seedProfileFromAzureProject(loaded, projectContext);
        const seededChanged = JSON.stringify(seeded) !== JSON.stringify(loaded);
        if (seededChanged) {
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
        setEditingProfile(!seeded.project_name.trim());
        setShowQuickStart(!seeded.project_name.trim() && !seeded.project_description.trim());
        const workItem = await loadCurrentWorkItem();
        if (workItem) {
          setCurrentWorkItem(workItem);
          seedPlannerFromWorkItem(workItem);
        }
        void loadAdoProjects(seeded);
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
  }, [profile]);

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
    const analyzed = await withLoading('Analyzing project description...', () => postJson<ProjectProfile>('/analyze-description', {
      description: profile.project_description,
    }));
    if (analyzed) {
      setProfile(mergeProfile(profile, analyzed));
    }
  }

  async function saveProfile() {
    const saved = await withLoading('Saving project profile...', () => postJson<ProjectProfile>('/profile', { profile }));
    if (saved) {
      setProfile(saved);
      lastSavedProfileRef.current = JSON.stringify(saved);
      setSaveStatus('saved');
      setEditingProfile(false);
    }
  }

  async function analyzeProject() {
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
      lastSavedProfileRef.current = JSON.stringify(analyzed);
      setSaveStatus('saved');
      setEditingProfile(false);
      setShowQuickStart(false);
      setActiveTab('planner');
    }
  }

  async function generatePrompts() {
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
    const result = await withLoading('Refining story with Project Intelligence...', () => postJson<StoryRefinement>('/refine-story', {
      profile,
      knowledge_profile: profile.knowledge_registry,
      story: storyInput,
    }));
    if (result) {
      setStoryResult(result);
    }
  }

  async function buildExecutionPackage() {
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
      setActiveTab('developer');
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
    console.log('[DEBUG] loadRepositories called:', { adoProject, hasSourceProfile: !!sourceProfile, storedProject: getAdoMapping(profile).ado_project });
    if (!adoProject) {
      setRepositories([]);
      setBranches([]);
      setRepositoryLoadMessage('Select an Azure DevOps project first.');
      return;
    }
    try {
      const repos = await fetchAdoRepositories(adoProject);
      console.log('[DEBUG] Fetched repositories:', { count: repos.length, repos });
      const visibleRepos = (repos || []).filter((repo) => repo.id && repo.name);
      console.log('[DEBUG] Visible repositories after filter:', { count: visibleRepos.length, visibleRepos });
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
    const selectedRepo = profile.repository_connection.repository_id;
    if (!selectedRepo || !repositories.some((repo) => repo.id === selectedRepo)) {
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
    }
  }

  async function discoverRepositoryDocuments() {
    const selectedRepo = profile.repository_connection.repository_id;
    if (!selectedRepo || !repositories.some((repo) => repo.id === selectedRepo)) {
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
    if (selectedRepo && repositories.some((repo) => repo.id === selectedRepo)) {
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
    if (profile.repository_connection.repository_id && !repositories.some((repo) => repo.id === profile.repository_connection.repository_id)) {
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
    }
  }

  return (
    <main className="planner-shell">
      <header className="planner-header">
        <div>
          <div className="planner-title">Project Intelligence Preview</div>
          <div className="planner-subtitle">
            {editingProfile
              ? 'Start with a project name and repository. Project Intelligence can fill in the rest.'
              : 'Project-aware context is ready for backlog refinement and story execution prompts.'}
          </div>
          <div className={`planner-save-status ${saveStatus}`}>{saveStatusLabel(saveStatus)}</div>
        </div>
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
      </header>

      {loading ? <div className="planner-banner">{message || 'Working...'}</div> : null}
      {error ? <div className="planner-error">{error}</div> : null}

      <WorkflowTabs activeTab={activeTab} onChange={setActiveTab} />

      {activeTab === 'project' ? (
        <>
          <ProjectHealthDashboard profile={profile} />
          <ProjectProfileCompletion profile={profile} />
          {showQuickStart ? (
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
          {!editingProfile && profile.project_name.trim() ? (
            <ProjectProfileSummary profile={profile} />
          ) : null}
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
          />
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
          <KnowledgeProfilePreview profile={profile} />
          <StandardsAndGuidelinesSummary profile={profile} />
          <ProjectIntelligenceProviderDiagnostics metadata={latestProvider} />
          <RoadmapCard />
        </>
      ) : null}

      {activeTab === 'planner' ? (
        <AIPlannerWorkspace
          profile={profile}
          loading={loading}
          currentWorkItem={currentWorkItem}
          childDrafts={childDrafts}
          creationLog={creationLog}
          providerMetadata={latestProvider}
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
        />
      ) : null}

      {activeTab === 'developer' ? (
        <DeveloperWorkspace
          executionContext={executionContext}
          devPrompt={devPrompt}
          uiPrompt={uiPrompt}
          qaPrompt={qaPrompt}
          copilotContext={copilotContext}
          onGenerate={() => void buildExecutionPackage()}
          loading={loading}
        />
      ) : null}
    </main>
  );
}

function WorkflowTabs({
  activeTab,
  onChange,
}: {
  activeTab: 'project' | 'planner' | 'developer';
  onChange: (tab: 'project' | 'planner' | 'developer') => void;
}) {
  const tabs: Array<{ id: 'project' | 'planner' | 'developer'; label: string; subtitle: string }> = [
    { id: 'project', label: 'Project Intelligence', subtitle: 'Setup and knowledge' },
    { id: 'planner', label: 'AI Planner', subtitle: 'Epic to task flow' },
    { id: 'developer', label: 'Developer Workspace', subtitle: 'Execution prompts' },
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

function StandardsAndGuidelinesSummary({ profile }: { profile: ProjectProfile }) {
  return (
    <section className="planner-card">
      <div className="planner-label">Development Standards & UI Guidelines</div>
      <div className="planner-grid">
        <ListBlock title="Architecture Patterns" items={profile.development_standards.architecture_patterns} />
        <ListBlock title="Coding Guidelines" items={profile.development_standards.coding_guidelines} />
        <ListBlock title="Security Requirements" items={profile.development_standards.security_requirements} />
        <ListBlock title="Testing Requirements" items={profile.development_standards.testing_requirements} />
      </div>
      <div className="planner-status-grid">
        <Row label="UI Guidelines" value={summarizeUiGuidelines(profile)} />
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
  selectedItemType,
  onItemTypeChange,
  epicInput,
  featureInput,
  storyInput,
  acceptanceCriteria,
  epicResult,
  featureResult,
  storyResult,
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
}: {
  profile: ProjectProfile;
  loading: boolean;
  currentWorkItem?: AdoWorkItem;
  childDrafts: ChildDraft[];
  creationLog: string[];
  providerMetadata?: ProviderMetadata;
  selectedItemType: 'Epic' | 'Feature' | 'Story' | 'Task';
  onItemTypeChange: (type: 'Epic' | 'Feature' | 'Story' | 'Task') => void;
  epicInput: { title: string; description: string };
  featureInput: { title: string; description: string };
  storyInput: { title: string; description: string };
  acceptanceCriteria: string;
  epicResult?: EpicRefinement;
  featureResult?: FeatureRefinement;
  storyResult?: StoryRefinement;
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
}) {
  const readOnly = currentWorkItem?.state.toLowerCase() === 'closed';
  return (
    <>
      <WorkItemContextCard workItem={currentWorkItem} />
      <section className="planner-card">
        <div className="planner-label">AI Planner</div>
        <div className="planner-subtle">Work through planning in delivery order: Epic, Feature, Story, then Task execution.</div>
        <KnowledgeRegistryNotice profile={profile} />
        {profileCompletion(profile).percent < 70 ? (
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
            <button className="planner-button secondary" onClick={refineEpic} disabled={loading || !epicInput.title.trim()}>Refine Epic</button>
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
            <button className="planner-button secondary" onClick={refineFeature} disabled={loading || !featureInput.title.trim()}>Refine Feature</button>
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
            <button className="planner-button secondary" onClick={refineStory} disabled={loading || !storyInput.title.trim()}>Refine Story</button>
            <button className="planner-button" onClick={generateChildren} disabled={loading || readOnly || !storyInput.title.trim()}>Generate Tasks</button>
            <button className="planner-button secondary" onClick={buildExecutionPackage} disabled={loading || !storyInput.title.trim()}>Generate Execution Package</button>
          </div>
          {storyResult ? (
            <div className="planner-status-grid">
              <StoryRefinementResult result={storyResult} />
              <GeneratedTasksPreview story={storyResult} />
            </div>
          ) : null}
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
            <button className="planner-button" onClick={buildExecutionPackage} disabled={loading || !storyInput.title.trim()}>Generate Execution Package</button>
          </div>
          {storyResult ? <GeneratedTasksPreview story={storyResult} /> : null}
        </section>
      ) : null}
      <GeneratedChildWorkItems
        drafts={childDrafts}
        creationLog={creationLog}
        currentWorkItem={currentWorkItem}
        providerMetadata={providerMetadata}
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
  loading,
  onSelectionChange,
  onCreateSelected,
}: {
  drafts: ChildDraft[];
  creationLog: string[];
  currentWorkItem?: AdoWorkItem;
  providerMetadata?: ProviderMetadata;
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
              disabled={draft.status === 'created'}
              onChange={(event) => onSelectionChange(draft.id, event.target.checked)}
            />
            <strong>{draft.type}: {draft.title}</strong>
          </label>
          <span>{draft.description}</span>
          <ListBlock title="Acceptance Criteria" items={draft.acceptanceCriteria} />
          <div className="planner-subtle">
            Status: {draft.status}
            {draft.azureId ? ` #${draft.azureId}` : ''}
            {draft.error ? ` - ${draft.error}` : ''}
          </div>
        </div>
      ))}
      <div className="planner-actions">
        <button className="planner-button secondary" onClick={() => drafts.forEach((draft) => onSelectionChange(draft.id, true))} disabled={loading}>Select All</button>
        <button className="planner-button secondary" onClick={() => drafts.forEach((draft) => onSelectionChange(draft.id, false))} disabled={loading}>Skip All</button>
        <button className="planner-button" onClick={onCreateSelected} disabled={loading || !selectedCount}>Create Selected</button>
      </div>
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

function GeneratedTasksPreview({ story }: { story: StoryRefinement }) {
  const tasks = [
    {
      title: 'UI Task',
      description: story.ui_considerations.join(' ') || 'Confirm UI behavior, states, accessibility, and validation copy for the approved story.',
    },
    {
      title: 'Dev Task',
      description: story.technical_considerations.join(' ') || 'Implement the approved story inside the affected modules and flows.',
    },
    {
      title: 'QA Task',
      description: story.qa_considerations.join(' ') || 'Prepare manual and regression checks for the approved acceptance criteria.',
    },
  ];
  return (
    <div className="planner-task">
      <div className="planner-label">Generated Tasks</div>
      {tasks.map((task) => (
        <div className="planner-task" key={task.title}>
          <strong>{task.title}</strong>
          <span>{task.description}</span>
        </div>
      ))}
    </div>
  );
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
}: {
  executionContext?: ExecutionContextResult;
  devPrompt?: PromptBuilderResult;
  uiPrompt?: PromptBuilderResult;
  qaPrompt?: PromptBuilderResult;
  copilotContext?: CopilotContextResult;
  onGenerate: () => void;
  loading: boolean;
}) {
  const hasPackage = Boolean(executionContext || devPrompt || uiPrompt || qaPrompt || copilotContext);
  const vsCodeUri = executionContext ? buildVsCodeExecutionPackageUri(executionContext, devPrompt, uiPrompt, qaPrompt, copilotContext) : '';
  return (
    <>
      <section className="planner-card">
        <div className="planner-label">Developer Workspace</div>
        <div className="planner-subtle">Execution-ready context for VS Code, Copilot, or manual implementation.</div>
        <div className="planner-actions">
          <button className="planner-button" onClick={onGenerate} disabled={loading}>Generate Execution Package</button>
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
  const readiness = profileReadinessBreakdown(profile);
  return (
    <section className="planner-card">
      <div className="planner-label">Project Intelligence Readiness</div>
      <div className="planner-health-grid">
        {readiness.map((section) => (
          <HealthCard key={section.title} title={section.title} status={section.status} detail={`${section.percent}%${section.missing.length ? ` missing ${section.missing.join(', ')}` : ' ready'}`} />
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
        <HealthCard title="Execution Readiness" status={execution.label === 'Ready' ? 'Ready' : execution.score >= 40 ? 'Partial' : 'Missing'} detail={`${execution.score}% ${execution.label}`} />
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

function KnowledgeProfilePreview({ profile }: { profile: ProjectProfile }) {
  const modules = registryModuleDetails(profile);
  const flows = registryFlowDetails(profile);
  const components = registryComponentDetails(profile);
  const architecture = profile.knowledge_registry.architecture_notes.length
    ? profile.knowledge_registry.architecture_notes
    : profile.readme_analysis.architecture_notes;
  const standards = profile.knowledge_registry.standards.length
    ? profile.knowledge_registry.standards
    : profile.knowledge_profile_preview.standards;
  return (
    <section className="planner-card">
      <div className="planner-label">Knowledge Profile Preview</div>
      <div className="planner-status-grid">
        <Row label="Project Name" value={profile.project_name || 'Not captured yet'} />
        <Row label="Domain" value={profile.domain || profile.knowledge_profile_preview.domain || 'Not analyzed yet'} />
        <Row label="Project Type" value={profile.project_type || 'Not captured yet'} />
        <Row label="Applications" value={formatApplications(profile.applications) || 'Not captured yet'} />
        <Row label="Technology Summary" value={technologySummary(profile) || 'Not captured yet'} />
        <Row label="Source Files" value={profile.knowledge_registry.source_files.join(', ') || profile.repository_sources.join(', ') || 'Pending repository analysis'} />
        <Row label="Repository Status" value={profile.knowledge_profile_preview.repository_status} />
        <Row label="Project Intelligence Readiness" value={profile.knowledge_profile_preview.readiness || readiness(profile)} />
      </div>
      <div className="planner-grid">
        <RegistryModuleCard modules={modules} />
        <RegistryFlowCard flows={flows} />
        <RegistryComponentCard components={components} />
        <ListBlock title="Architecture" items={architecture.length ? architecture : ['Pending repository analysis']} />
        <ListBlock title="Standards" items={standards.length ? standards : ['Pending repository analysis']} />
      </div>
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
}) {
  const selectedRepositoryLoaded = repositories.some((repo) => repo.id === profile.repository_connection.repository_id);
  const mapping = getAdoMapping(profile);
  return (
    <section className="planner-card">
      <div className="planner-label">Repository Intelligence</div>
      <div className="planner-subtle">
        {showConnectionControls
          ? 'Connect Azure Repos and analyze known documentation files.'
          : 'Repository selection lives in Quick Start. Use this area only for README/docs discovery and manual fallback.'}
      </div>
      {showConnectionControls ? (
        <>
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
        <button className="planner-button" onClick={onAnalyzeReadme} disabled={loading || !selectedRepositoryLoaded}>
          Analyze README
        </button>
        <button className="planner-button secondary" onClick={onDiscoverDocuments} disabled={loading || !selectedRepositoryLoaded}>
          Discover Documents
        </button>
        <button className="planner-button" onClick={onAnalyzeDocuments} disabled={loading || (!selectedRepositoryLoaded && !Object.values(repositoryDocuments).some((content) => content.trim()))}>
          Analyze Documents
        </button>
      </div>
      <div className="planner-task">
        <div className="planner-label">Known Documentation Files</div>
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
        <Row label="README Analysis" value={profile.readme_analysis.summary || 'Pending'} />
        <Row label="Architecture Discovery" value={(profile.knowledge_registry.architecture_notes || profile.readme_analysis.architecture_notes).join(', ') || 'Pending'} />
        <Row label="Flow Discovery" value={profile.knowledge_registry.flows.join(', ') || 'Pending'} />
        <Row label="Module Discovery" value={profile.knowledge_registry.modules.join(', ') || 'Pending'} />
        <Row label="Source Files" value={profile.knowledge_registry.source_files.join(', ') || profile.repository_sources.join(', ') || 'Pending'} />
      </div>
      <div className="planner-subtle">Only known documentation ingestion is enabled in this preview. Full repository scans are intentionally not included.</div>
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
        <Row label="Execution Readiness Score" value={`${execution.score}% - ${execution.label}`} />
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
  return (
    <div className="planner-status-grid">
      <SourceBadge metadata={result} />
      <Row label="Feature Summary" value={result.feature_summary} />
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
  return (
    <div className="planner-task">
      <div className="planner-label">{title}</div>
      <ul className="planner-list">
        {(items.length ? items : ['Not identified yet']).map((item) => <li key={item}>{item}</li>)}
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
      <div className="planner-label">Roadmap</div>
      <div className="planner-grid">
        <div>
          <div className="planner-label">Completed</div>
          <ul className="planner-list">
            <li>Project Profile</li>
            <li>Project Intelligence</li>
            <li>Repository Intelligence</li>
            <li>Knowledge Registry</li>
            <li>AI Planner Workflow</li>
            <li>Developer Workspace</li>
          </ul>
        </div>
        <div>
          <div className="planner-label">Coming Next</div>
          <ul className="planner-list">
            <li>Copilot Deep Integration</li>
            <li>PR Validation</li>
            <li>Story Coverage Validation</li>
            <li>Teams Agent</li>
            <li>Autonomous Planning Agent</li>
          </ul>
        </div>
      </div>
    </section>
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
  console.log('[DEBUG] Fetching repositories:', { adoProject, url });
  const response = await getJson<{ repositories?: GitRepository[]; error?: string }>(url);
  console.log('[DEBUG] Repositories response:', { count: response.repositories?.length || 0, response });
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
    acceptanceCriteria: feature.acceptance_criteria?.length ? feature.acceptance_criteria : ['Feature supports the approved epic outcome.'],
    selected: true,
    status: 'preview',
  }));
}

function storyDraftsFromFeature(result: FeatureRefinement): ChildDraft[] {
  return result.recommended_stories.map((story, index) => ({
    id: `story_${index + 1}`,
    type: 'User Story',
    title: story.title,
    description: story.description,
    acceptanceCriteria: [
      `${story.title} is visible and testable.`,
      ...result.affected_flows.slice(0, 3).map((flow) => `${flow} flow is covered end to end.`),
    ],
    selected: true,
    status: 'preview',
  }));
}

function taskDraftsFromStory(result: StoryRefinement): ChildDraft[] {
  const tasks = [
    { title: `Design ${result.story_summary}`, description: result.ui_considerations.join(' ') || 'Confirm UI states and interaction behavior.' },
    { title: `Implement ${result.story_summary}`, description: result.technical_considerations.join(' ') || 'Implement the approved behavior in the affected modules.' },
    { title: `Test ${result.story_summary}`, description: result.qa_considerations.join(' ') || 'Validate acceptance criteria and regression coverage.' },
  ];
  return tasks.map((task, index) => ({
    id: `task_${index + 1}`,
    type: 'Task',
    title: cleanGeneratedTitle(task.title),
    description: task.description,
    acceptanceCriteria: result.acceptance_criteria,
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

function profileCompletion(profile: ProjectProfile): { percent: number; missing: string[] } {
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
    percent: Math.round((readyCount / checks.length) * 100),
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
