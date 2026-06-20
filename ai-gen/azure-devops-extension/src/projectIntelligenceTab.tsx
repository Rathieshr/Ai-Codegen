import * as SDK from 'azure-devops-extension-sdk';
import { CommonServiceIds, IProjectPageService } from 'azure-devops-extension-api/Common/CommonServices';
import { getClient } from 'azure-devops-extension-api/Common/Client';
import { GitRestClient } from 'azure-devops-extension-api/Git/GitClient';
import { GitRepository, GitVersionOptions, GitVersionType } from 'azure-devops-extension-api/Git/Git';
import React, { useEffect, useState } from 'react';
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

type ProjectProfile = {
  onboarding_completed?: boolean;
  project_name: string;
  domain: string;
  project_type: string;
  project_description: string;
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
    flows: string[];
    components: string[];
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

type PromptResult = {
  ui_prompt: string;
  dev_prompt: string;
  qa_prompt: string;
};

type EpicRefinement = {
  business_goal: string;
  business_outcomes: string[];
  users: string[];
  applications: string[];
  constraints: string[];
  risks: string[];
  dependencies: string[];
  recommended_features: Array<{ title: string; description: string }>;
};

type FeatureRefinement = {
  feature_summary: string;
  affected_modules: string[];
  affected_flows: string[];
  dependencies: string[];
  risks: string[];
  recommended_stories: Array<{ title: string; description: string }>;
};

type StoryRefinement = {
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

type StoryImpact = {
  affected_applications: string[];
  affected_modules: string[];
  affected_flows: string[];
  affected_components: string[];
  dependencies: string[];
  risks: string[];
  integration_points: string[];
  recommended_reviewers: string[];
};

type FeatureImpact = {
  affected_applications: string[];
  affected_modules: string[];
  affected_flows: string[];
  cross_team_dependencies: string[];
  integration_points: string[];
  risks: string[];
};

type EpicImpact = {
  affected_applications: string[];
  affected_modules: string[];
  affected_flows: string[];
  program_dependencies: string[];
  risks: string[];
  recommended_rollout_strategy: string[];
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
  project_name: '',
  domain: '',
  project_type: '',
  project_description: '',
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
  const [profile, setProfile] = useState<ProjectProfile>(EMPTY_PROFILE);
  const [storyTitle, setStoryTitle] = useState('');
  const [storyDescription, setStoryDescription] = useState('');
  const [acceptanceCriteria, setAcceptanceCriteria] = useState('');
  const [prompts, setPrompts] = useState<PromptResult | undefined>();
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
  const [repositories, setRepositories] = useState<GitRepository[]>([]);
  const [branches, setBranches] = useState<string[]>([]);
  const [editingProfile, setEditingProfile] = useState(false);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState('Loading Project Intelligence...');
  const [error, setError] = useState('');

  useEffect(() => {
    SDK.init({ loaded: false, applyTheme: true });
    SDK.ready().then(async () => {
      SDK.notifyLoadSucceeded();
      try {
        const loaded = await getProfile();
        setProfile(loaded);
        setEditingProfile(!isProfileComplete(loaded));
        void loadRepositories();
        setError('');
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : 'Unable to load project profile.');
      } finally {
        setLoading(false);
        setMessage('');
      }
    }).catch((initError) => {
      const text = initError instanceof Error ? initError.message : 'Unable to initialize Azure DevOps SDK.';
      setLoading(false);
      setMessage('');
      setError(text);
      void SDK.notifyLoadFailed(text);
    });
  }, []);

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
      setEditingProfile(false);
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

  async function loadRepositories() {
    try {
      const projectName = await getProjectName();
      const client = getClient(GitRestClient);
      const repos = await client.getRepositories(projectName);
      setRepositories(repos || []);
    } catch {
      setError('Could not load Azure DevOps repositories. You can still use the saved Project Intelligence profile.');
    }
  }

  async function selectRepository(repositoryId: string) {
    const selected = repositories.find((repo) => repo.id === repositoryId);
    const nextProfile = {
      ...profile,
      repository_connection: {
        ...profile.repository_connection,
        repository_id: selected?.id || repositoryId,
        repository_name: selected?.name || '',
        status: selected ? 'Repository selected' : profile.repository_connection.status,
      },
    };
    setProfile(nextProfile);
    setBranches([]);
    if (!selected?.id) {
      return;
    }
    try {
      const projectName = await getProjectName();
      const client = getClient(GitRestClient);
      const stats = await client.getBranches(selected.id, projectName);
      const branchNames = (stats || []).map((branch) => String(branch.name || '')).filter(Boolean);
      setBranches(branchNames);
      const defaultBranch = normalizeBranchName(selected.defaultBranch || '') || branchNames[0] || '';
      setProfile({
        ...nextProfile,
        repository_connection: {
          ...nextProfile.repository_connection,
          branch: defaultBranch,
          status: 'Repository connected',
        },
      });
    } catch {
      setError('Repository selected, but branches could not be loaded.');
    }
  }

  async function analyzeReadme() {
    const selectedRepo = profile.repository_connection.repository_id;
    if (!selectedRepo) {
      setError('Select a repository before analyzing README.');
      return;
    }
    const analyzed = await withLoading('Loading and analyzing README...', async () => {
      const projectName = await getProjectName();
      const client = getClient(GitRestClient);
      const readmePath = profile.repository_connection.readme_path || '/README.md';
      const branch = profile.repository_connection.branch || 'main';
      const buffer = await client.getItemContent(
        selectedRepo,
        readmePath,
        projectName,
        undefined,
        undefined,
        true,
        undefined,
        false,
        { version: branch, versionOptions: GitVersionOptions.None, versionType: GitVersionType.Branch },
        true,
      );
      const readmeContent = new TextDecoder('utf-8').decode(buffer);
      return postJson<ProjectProfile>('/analyze-readme', {
        profile,
        readme_content: readmeContent,
        repository: {
          id: selectedRepo,
          name: profile.repository_connection.repository_name,
          branch,
          readme_path: readmePath,
        },
      });
    });
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
              ? 'Set up project context once, then use it quietly inside planning, prompts, and validation.'
              : 'Project-aware context is ready for backlog refinement and story execution prompts.'}
          </div>
        </div>
        {editingProfile ? (
          <button className="planner-button secondary" onClick={() => void saveProfile()} disabled={loading || !profile.project_description.trim()}>
            Finish Setup
          </button>
        ) : (
          <button className="planner-button secondary" onClick={() => setEditingProfile(true)} disabled={loading}>
            Edit Project Profile
          </button>
        )}
      </header>

      {loading ? <div className="planner-banner">{message || 'Working...'}</div> : null}
      {error ? <div className="planner-error">{error}</div> : null}

      {editingProfile ? (
        <OnboardingForm
          profile={profile}
          loading={loading}
          onProfileChange={setProfile}
          onAnalyze={() => void analyzeDescription()}
          onSave={() => void saveProfile()}
        />
      ) : (
        <ProjectProfileSummary profile={profile} />
      )}

      <KnowledgeProfilePreview profile={profile} />
      <RefinementReadinessDashboard
        profile={profile}
        epicResult={epicResult}
        featureResult={featureResult}
        storyResult={storyResult}
        hasImpact={Boolean(epicImpact || featureImpact || storyImpact)}
      />
      <RepositoryIntelligenceCard
        profile={profile}
        repositories={repositories}
        branches={branches}
        loading={loading}
        onSelectRepository={(repositoryId) => void selectRepository(repositoryId)}
        onProfileChange={setProfile}
        onAnalyzeReadme={() => void analyzeReadme()}
      />
      <ProjectRefinementCards
        loading={loading}
        epicInput={epicInput}
        featureInput={featureInput}
        storyInput={storyInput}
        epicResult={epicResult}
        featureResult={featureResult}
        storyResult={storyResult}
        setEpicInput={setEpicInput}
        setFeatureInput={setFeatureInput}
        setStoryInput={setStoryInput}
        refineEpic={() => void refineEpic()}
        refineFeature={() => void refineFeature()}
        refineStory={() => void refineStory()}
      />
      <ImpactAnalysisDashboard
        loading={loading}
        epicInput={epicImpactInput}
        featureInput={featureImpactInput}
        storyInput={storyImpactInput}
        epicImpact={epicImpact}
        featureImpact={featureImpact}
        storyImpact={storyImpact}
        setEpicInput={setEpicImpactInput}
        setFeatureInput={setFeatureImpactInput}
        setStoryInput={setStoryImpactInput}
        analyzeEpic={() => void analyzeEpicImpact()}
        analyzeFeature={() => void analyzeFeatureImpact()}
        analyzeStory={() => void analyzeStoryImpact()}
      />
      <StoryPromptGeneration
        loading={loading}
        storyTitle={storyTitle}
        storyDescription={storyDescription}
        acceptanceCriteria={acceptanceCriteria}
        prompts={prompts}
        setStoryTitle={setStoryTitle}
        setStoryDescription={setStoryDescription}
        setAcceptanceCriteria={setAcceptanceCriteria}
        generatePrompts={() => void generatePrompts()}
      />
      <RoadmapCard />
    </main>
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
        <div className="planner-grid" key={`${application.name}-${index}`}>
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
    onProfileChange({ ...profile, applications: updated.filter((item) => item.name.trim()) });
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
  return (
    <section className="planner-card">
      <div className="planner-label">Knowledge Profile Preview</div>
      <div className="planner-status-grid">
        <Row label="Project Name" value={profile.project_name || 'Not captured yet'} />
        <Row label="Domain" value={profile.domain || profile.knowledge_profile_preview.domain || 'Not analyzed yet'} />
        <Row label="Project Type" value={profile.project_type || 'Not captured yet'} />
        <Row label="Applications" value={formatApplications(profile.applications) || 'Not captured yet'} />
        <Row label="Technology Summary" value={formatStack(profile.technology_stack) || 'Not captured yet'} />
        <Row label="Detected Modules" value={profile.knowledge_registry.modules.join(', ') || 'Pending README analysis'} />
        <Row label="Detected Flows" value={profile.knowledge_registry.flows.join(', ') || 'Pending README analysis'} />
        <Row label="Architecture Summary" value={profile.readme_analysis.architecture_notes.join(', ') || 'Pending README analysis'} />
        <Row label="Repository Status" value={profile.knowledge_profile_preview.repository_status} />
        <Row label="Project Intelligence Readiness" value={profile.knowledge_profile_preview.readiness || readiness(profile)} />
      </div>
    </section>
  );
}

function RepositoryIntelligenceCard({
  profile,
  repositories,
  branches,
  loading,
  onSelectRepository,
  onProfileChange,
  onAnalyzeReadme,
}: {
  profile: ProjectProfile;
  repositories: GitRepository[];
  branches: string[];
  loading: boolean;
  onSelectRepository: (repositoryId: string) => void;
  onProfileChange: (profile: ProjectProfile) => void;
  onAnalyzeReadme: () => void;
}) {
  return (
    <section className="planner-card">
      <div className="planner-label">Repository Intelligence</div>
      <div className="planner-grid">
        <select className="planner-input" value={profile.repository_connection.repository_id} onChange={(event) => onSelectRepository(event.target.value)}>
          <option value="">Select Azure DevOps repository</option>
          {repositories.map((repo) => <option key={repo.id} value={repo.id}>{repo.name}</option>)}
        </select>
        <select
          className="planner-input"
          value={profile.repository_connection.branch}
          onChange={(event) => onProfileChange({
            ...profile,
            repository_connection: { ...profile.repository_connection, branch: event.target.value, status: 'Repository connected' },
          })}
        >
          <option value="">Select branch</option>
          {branches.map((branch) => <option key={branch} value={branch}>{branch}</option>)}
          {profile.repository_connection.branch && !branches.includes(profile.repository_connection.branch) ? (
            <option value={profile.repository_connection.branch}>{profile.repository_connection.branch}</option>
          ) : null}
        </select>
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
      <div className="planner-actions">
        <button className="planner-button" onClick={onAnalyzeReadme} disabled={loading || !profile.repository_connection.repository_id}>
          Analyze README
        </button>
      </div>
      <div className="planner-status-grid">
        <Row label="Repository" value={profile.repository_connection.repository_name || 'Not connected'} />
        <Row label="Branch" value={profile.repository_connection.branch || 'Not selected'} />
        <Row label="Status" value={profile.repository_connection.status || 'Not connected'} />
        <Row label="README Analysis" value={profile.readme_analysis.summary || 'Pending'} />
        <Row label="Architecture Discovery" value={profile.readme_analysis.architecture_notes.join(', ') || 'Pending'} />
        <Row label="Flow Discovery" value={profile.knowledge_registry.flows.join(', ') || 'Pending'} />
        <Row label="Module Discovery" value={profile.knowledge_registry.modules.join(', ') || 'Pending'} />
      </div>
      <div className="planner-subtle">Only README ingestion is enabled in this preview. Full repository scans are intentionally not included.</div>
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
          <PromptBlock title="UI Prompt" value={prompts.ui_prompt} />
          <PromptBlock title="Dev Prompt" value={prompts.dev_prompt} />
          <PromptBlock title="QA Prompt" value={prompts.qa_prompt} />
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
            <li>Story Prompt Generation</li>
            <li>Repository Intelligence</li>
            <li>Epic Intelligence</li>
            <li>Feature Intelligence</li>
            <li>Story Intelligence</li>
            <li>Impact Analysis</li>
          </ul>
        </div>
        <div>
          <div className="planner-label">Coming Next</div>
          <ul className="planner-list">
            <li>VS Code Intelligence</li>
            <li>Copilot Context Builder</li>
            <li>PR Validation</li>
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

function PromptBlock({ title, value }: { title: string; value: string }) {
  return (
    <div className="planner-task">
      <div className="planner-label">{title}</div>
      <pre className="planner-prompt">{value}</pre>
    </div>
  );
}

async function getProfile(): Promise<ProjectProfile> {
  const response = await fetch(`${BASE_URL}/profile`);
  if (!response.ok) {
    throw new Error(await response.text() || `Backend returned HTTP ${response.status}`);
  }
  return response.json() as Promise<ProjectProfile>;
}

async function postJson<T>(path: string, body: Record<string, unknown>): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(await response.text() || `Backend returned HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

function splitLines(value: string): string[] {
  return value.split(/\n|,/).map((item) => item.trim()).filter(Boolean);
}

function isProfileComplete(profile: ProjectProfile): boolean {
  return Boolean(profile.onboarding_completed || profile.project_description.trim());
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

function readiness(profile: ProjectProfile): string {
  const hasDescription = Boolean(profile.project_description.trim());
  const hasApplications = profile.applications.length > 0;
  const hasStack = STACK_FIELDS.some((field) => profile.technology_stack[field].length > 0);
  const hasStandards = Object.values(profile.development_standards).some((items) => items.length > 0);
  const hasRegistry = profile.knowledge_registry.modules.length > 0 || profile.knowledge_registry.flows.length > 0;
  if (hasDescription && hasApplications && hasStack && (hasStandards || hasRegistry)) {
    return 'Advanced';
  }
  if (hasDescription && hasApplications && hasStack) {
    return 'Intermediate';
  }
  return 'Basic';
}

function executionReadiness(profile: ProjectProfile, hasImpact: boolean): { score: number; label: string; breakdown: string } {
  const projectProfile = profile.project_description.trim() ? 25 : 0;
  const repository = profile.repository_connection.status === 'README analyzed' ? 25 : 0;
  const registry = profile.knowledge_registry.modules.length || profile.knowledge_registry.flows.length ? 20 : 0;
  const impact = hasImpact ? 15 : 0;
  const standards = Object.values(profile.development_standards).some((items) => items.length > 0) ? 15 : 0;
  const score = projectProfile + repository + registry + impact + standards;
  const label = score >= 85 ? 'Execution Ready' : score >= 65 ? 'Advanced' : score >= 40 ? 'Intermediate' : 'Basic';
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
