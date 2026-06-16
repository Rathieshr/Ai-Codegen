import * as SDK from 'azure-devops-extension-sdk';
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
      <RepositoryIntelligenceCard />
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
        <Row label="Repository Status" value={profile.knowledge_profile_preview.repository_status} />
        <Row label="Project Intelligence Readiness" value={profile.knowledge_profile_preview.readiness || readiness(profile)} />
      </div>
    </section>
  );
}

function RepositoryIntelligenceCard() {
  return (
    <section className="planner-card">
      <div className="planner-label">Repository Intelligence</div>
      <div className="planner-status-grid">
        <Row label="README Analysis" value="Pending" />
        <Row label="Architecture Discovery" value="Pending" />
        <Row label="Flow Discovery" value="Pending" />
        <Row label="Module Discovery" value="Pending" />
      </div>
      <div className="planner-subtle">Repository README scan coming next.</div>
    </section>
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
          </ul>
        </div>
        <div>
          <div className="planner-label">Coming Next</div>
          <ul className="planner-list">
            <li>Repository Intelligence</li>
            <li>Epic Intelligence</li>
            <li>Feature Intelligence</li>
            <li>Story Intelligence</li>
            <li>VS Code Integration</li>
            <li>PR Validation</li>
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
  if (hasDescription && hasApplications && hasStack && hasStandards) {
    return 'Advanced';
  }
  if (hasDescription && hasApplications && hasStack) {
    return 'Intermediate';
  }
  return 'Basic';
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
