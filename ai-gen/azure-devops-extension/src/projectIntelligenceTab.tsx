import * as SDK from 'azure-devops-extension-sdk';
import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './storyPlanner.css';

const BASE_URL = 'https://ai-codegen-production.up.railway.app/project-intelligence';

type ProjectProfile = {
  project_description: string;
  applications: string[];
  technology_stack: string[];
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
  };
};

type PromptResult = {
  ui_prompt: string;
  dev_prompt: string;
  qa_prompt: string;
};

const EMPTY_PROFILE: ProjectProfile = {
  project_description: '',
  applications: [],
  technology_stack: [],
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
  },
};

function ProjectIntelligenceTab() {
  const [profile, setProfile] = useState<ProjectProfile>(EMPTY_PROFILE);
  const [storyTitle, setStoryTitle] = useState('');
  const [storyDescription, setStoryDescription] = useState('');
  const [acceptanceCriteria, setAcceptanceCriteria] = useState('');
  const [prompts, setPrompts] = useState<PromptResult | undefined>();
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
      setProfile(analyzed);
    }
  }

  async function saveProfile() {
    const saved = await withLoading('Saving project profile...', () => postJson<ProjectProfile>('/profile', { profile }));
    if (saved) {
      setProfile(saved);
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
          <div className="planner-subtitle">Capture project context for project-aware planning and story execution prompts.</div>
        </div>
        <button className="planner-button secondary" onClick={() => void saveProfile()} disabled={loading}>Save Profile</button>
      </header>

      {loading ? <div className="planner-banner">{message || 'Working...'}</div> : null}
      {error ? <div className="planner-error">{error}</div> : null}

      <section className="planner-card">
        <div className="planner-label">Project Description</div>
        <textarea
          className="planner-textarea"
          value={profile.project_description}
          onChange={(event) => setProfile({ ...profile, project_description: event.target.value })}
          placeholder="Describe the product, domain, business goals, users, and delivery context."
        />
        <div className="planner-actions">
          <button className="planner-button" onClick={() => void analyzeDescription()} disabled={loading || !profile.project_description.trim()}>
            Analyze Description
          </button>
        </div>
      </section>

      <section className="planner-card">
        <div className="planner-label">Applications</div>
        <textarea
          className="planner-textarea compact"
          value={profile.applications.join('\n')}
          onChange={(event) => updateProfileList('applications', event.target.value)}
          placeholder="Mobile App&#10;Backend&#10;Firmware&#10;Analytics"
        />
      </section>

      <section className="planner-card">
        <div className="planner-label">Technology Stack</div>
        <textarea
          className="planner-textarea compact"
          value={profile.technology_stack.join('\n')}
          onChange={(event) => updateProfileList('technology_stack', event.target.value)}
          placeholder="React&#10;TypeScript&#10;FastAPI&#10;Azure DevOps"
        />
      </section>

      <section className="planner-card">
        <div className="planner-label">UI Guidelines</div>
        <div className="planner-grid">
          <input className="planner-input" value={profile.ui_guidelines.primary_color} onChange={(event) => updateUiGuideline('primary_color', event.target.value)} placeholder="Primary color" />
          <input className="planner-input" value={profile.ui_guidelines.secondary_color} onChange={(event) => updateUiGuideline('secondary_color', event.target.value)} placeholder="Secondary color" />
          <input className="planner-input" value={profile.ui_guidelines.typography} onChange={(event) => updateUiGuideline('typography', event.target.value)} placeholder="Typography" />
          <input className="planner-input" value={profile.ui_guidelines.component_library} onChange={(event) => updateUiGuideline('component_library', event.target.value)} placeholder="Component library" />
        </div>
        <textarea
          className="planner-textarea compact"
          value={profile.ui_guidelines.accessibility_rules.join('\n')}
          onChange={(event) => updateUiGuidelineList('accessibility_rules', event.target.value)}
          placeholder="Accessibility rules, one per line"
        />
      </section>

      <section className="planner-card">
        <div className="planner-label">Repository Sources</div>
        <textarea
          className="planner-textarea compact"
          value={profile.repository_sources.join('\n')}
          onChange={(event) => updateProfileList('repository_sources', event.target.value)}
          placeholder="README.md&#10;docs/architecture.md&#10;openapi.yaml"
        />
        <div className="planner-subtle">Repository README scan coming next.</div>
      </section>

      <section className="planner-card">
        <div className="planner-label">Knowledge Profile Preview</div>
        <div className="planner-status-grid">
          <Row label="Domain" value={profile.knowledge_profile_preview.domain || 'Not analyzed yet'} />
          <Row label="Systems" value={profile.knowledge_profile_preview.systems.join(', ') || 'Not captured yet'} />
          <Row label="Standards" value={profile.knowledge_profile_preview.standards.join(', ') || 'Not captured yet'} />
          <Row label="Repository" value={profile.knowledge_profile_preview.repository_status} />
        </div>
      </section>

      <section className="planner-card">
        <div className="planner-label">Story Prompt Generation</div>
        <input className="planner-input" value={storyTitle} onChange={(event) => setStoryTitle(event.target.value)} placeholder="Story title" />
        <textarea className="planner-textarea compact" value={storyDescription} onChange={(event) => setStoryDescription(event.target.value)} placeholder="Story description" />
        <textarea className="planner-textarea compact" value={acceptanceCriteria} onChange={(event) => setAcceptanceCriteria(event.target.value)} placeholder="Acceptance criteria, one per line" />
        <div className="planner-actions">
          <button className="planner-button" onClick={() => void generatePrompts()} disabled={loading}>Generate Story Prompts</button>
        </div>
        {prompts ? (
          <div className="planner-status-grid">
            <PromptBlock title="UI Prompt" value={prompts.ui_prompt} />
            <PromptBlock title="Dev Prompt" value={prompts.dev_prompt} />
            <PromptBlock title="QA Prompt" value={prompts.qa_prompt} />
          </div>
        ) : null}
      </section>
    </main>
  );

  function updateProfileList(field: 'applications' | 'technology_stack' | 'repository_sources', value: string) {
    setProfile({ ...profile, [field]: splitLines(value) });
  }

  function updateUiGuideline(field: 'primary_color' | 'secondary_color' | 'typography' | 'component_library', value: string) {
    setProfile({ ...profile, ui_guidelines: { ...profile.ui_guidelines, [field]: value } });
  }

  function updateUiGuidelineList(field: 'accessibility_rules', value: string) {
    setProfile({ ...profile, ui_guidelines: { ...profile.ui_guidelines, [field]: splitLines(value) } });
  }
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

const rootNode = document.getElementById('root');
if (rootNode) {
  createRoot(rootNode).render(<ProjectIntelligenceTab />);
}
