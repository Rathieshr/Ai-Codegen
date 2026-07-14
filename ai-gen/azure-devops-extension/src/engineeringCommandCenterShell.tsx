import React, { ReactNode, useEffect, useMemo, useRef, useState } from 'react';

export type WorkspaceNavigationItem = {
  id: string;
  label: string;
  target: string;
  icon: string;
  enabled: boolean;
  future?: boolean;
  lazy?: boolean;
};

export type WorkspacePreferences = {
  userId: string;
  theme: 'system' | 'light' | 'dark' | 'high-contrast';
  density: 'comfortable' | 'compact';
  sidebarCollapsed: boolean;
  defaultWorkspace: string;
  notificationsEnabled: boolean;
  commandPaletteEnabled: boolean;
  updatedAt?: string;
};

export type EngineeringWorkspace = {
  workspaceId: string;
  name: string;
  description: string;
  version: string;
  currentUser: { userId: string; role: string };
  preferences: WorkspacePreferences;
  navigation: WorkspaceNavigationItem[];
  capabilities: Record<string, unknown>;
  status: { state: string; message: string; checkedAt: string };
  notifications: Array<{ id?: string; title?: string; message?: string; severity?: string; target?: string }>;
};

type Props = {
  workspace?: EngineeringWorkspace;
  activeNavigationId: string;
  projectName: string;
  userName: string;
  roleLabel: string;
  logoSrc?: string;
  busy?: boolean;
  headerActions?: ReactNode;
  children: ReactNode;
  onNavigate: (item: WorkspaceNavigationItem) => void;
  onPreferencesChange: (changes: Partial<WorkspacePreferences>) => void;
};

const FALLBACK_NAVIGATION: WorkspaceNavigationItem[] = [
  { id: 'overview', label: 'Overview', target: 'overview', icon: 'O', enabled: true },
  { id: 'planning', label: 'Planning', target: 'planning', icon: 'P', enabled: true, lazy: true },
  { id: 'repository', label: 'Repository', target: 'admin', icon: 'R', enabled: true, lazy: true },
  { id: 'execution', label: 'Execution', target: 'execution', icon: 'E', enabled: true, lazy: true },
  { id: 'approvals', label: 'Approvals', target: 'governance', icon: 'A', enabled: true, lazy: true },
  { id: 'azure-devops', label: 'Azure DevOps', target: 'admin', icon: 'D', enabled: true, lazy: true },
  { id: 'agents', label: 'Agents', target: 'agents', icon: 'G', enabled: true, lazy: true },
  { id: 'activity', label: 'Activity', target: 'diagnostics', icon: 'A', enabled: true, lazy: true },
  { id: 'health', label: 'Health', target: 'diagnostics', icon: 'H', enabled: true, lazy: true },
  { id: 'settings', label: 'Settings', target: 'admin', icon: 'S', enabled: true, lazy: true },
  { id: 'portfolio', label: 'Portfolio', target: 'overview', icon: 'P', enabled: false, future: true },
  { id: 'memory', label: 'Memory', target: 'memory', icon: 'M', enabled: true, lazy: true },
  { id: 'administration', label: 'Administration', target: 'admin', icon: 'A', enabled: true, lazy: true },
];

const FALLBACK_PREFERENCES: WorkspacePreferences = {
  userId: 'current-user', theme: 'system', density: 'comfortable', sidebarCollapsed: false,
  defaultWorkspace: 'overview', notificationsEnabled: true, commandPaletteEnabled: true,
};

export function EngineeringCommandCenterShell({
  workspace,
  activeNavigationId,
  projectName,
  userName,
  roleLabel,
  logoSrc = 'static/hei-logo.png',
  busy,
  headerActions,
  children,
  onNavigate,
  onPreferencesChange,
}: Props) {
  const preferences = workspace?.preferences || FALLBACK_PREFERENCES;
  const navigation = workspace?.navigation?.length ? workspace.navigation : fallbackNavigation(roleLabel);
  const [search, setSearch] = useState('');
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);
  const activeItem = navigation.find((item) => item.id === activeNavigationId) || navigation[0];
  const availableItems = useMemo(() => navigation.filter((item) => item.enabled), [navigation]);
  const searchResults = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return [];
    return navigation.filter((item) => item.label.toLowerCase().includes(query)).slice(0, 6);
  }, [navigation, search]);

  useEffect(() => {
    document.documentElement.dataset.heiTheme = preferences.theme;
    document.documentElement.dataset.heiDensity = preferences.density;
  }, [preferences.theme, preferences.density]);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setPaletteOpen((value) => !value);
      }
      if (event.key === '/' && document.activeElement?.tagName !== 'INPUT' && document.activeElement?.tagName !== 'TEXTAREA') {
        event.preventDefault();
        searchRef.current?.focus();
      }
      if (event.key === 'Escape') {
        setPaletteOpen(false);
        setNotificationsOpen(false);
        setSearch('');
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  function select(item: WorkspaceNavigationItem) {
    if (!item.enabled) return;
    onNavigate(item);
    setSearch('');
    setPaletteOpen(false);
  }

  return (
    <div className={`hei-command-shell ${preferences.sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
      <header className="hei-command-header">
        <div className="hei-command-brand">
          <img src={logoSrc} alt="Hubbell Engineering Intelligence" />
          <div>
            <strong>HEI</strong>
            <span>Engineering Command Center</span>
          </div>
        </div>
        <div className="hei-global-search" role="search">
          <label htmlFor="hei-global-search">Global search</label>
          <input
            id="hei-global-search"
            ref={searchRef}
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search workspaces and commands"
            aria-label="Search HEI workspaces and commands"
          />
          <kbd>Ctrl K</kbd>
          {searchResults.length ? (
            <div className="hei-search-results" role="listbox">
              {searchResults.map((item) => (
                <button key={item.id} type="button" onClick={() => select(item)} disabled={!item.enabled}>
                  <span>{item.label}</span><small>{item.enabled ? 'Open workspace' : 'Future'}</small>
                </button>
              ))}
            </div>
          ) : null}
        </div>
        <div className="hei-command-header-actions">
          <label className="hei-workspace-switcher">
            <span>Workspace</span>
            <select value={activeItem?.id || 'overview'} onChange={(event) => {
              const item = navigation.find((entry) => entry.id === event.target.value);
              if (item) select(item);
            }} aria-label="Switch HEI workspace">
              {availableItems.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
            </select>
          </label>
          <button className="hei-header-icon" type="button" onClick={() => setPaletteOpen(true)} aria-label="Open command palette">Commands</button>
          <button className="hei-header-icon" type="button" onClick={() => setNotificationsOpen((value) => !value)} aria-expanded={notificationsOpen} aria-label="Open notifications">
            Notices {workspace?.notifications?.length ? `(${workspace.notifications.length})` : ''}
          </button>
          <details className="hei-user-menu">
            <summary aria-label="Open user menu"><span>{initials(userName)}</span><strong>{userName || 'HEI User'}</strong></summary>
            <div>
              <strong>{userName || 'HEI User'}</strong>
              <small>{roleLabel}</small>
              <label>Theme
                <select value={preferences.theme} onChange={(event) => onPreferencesChange({ theme: event.target.value as WorkspacePreferences['theme'] })}>
                  <option value="system">System</option><option value="light">Light</option><option value="dark">Dark</option><option value="high-contrast">High Contrast</option>
                </select>
              </label>
              <label>Density
                <select value={preferences.density} onChange={(event) => onPreferencesChange({ density: event.target.value as WorkspacePreferences['density'] })}>
                  <option value="comfortable">Comfortable</option><option value="compact">Compact</option>
                </select>
              </label>
            </div>
          </details>
          {headerActions}
        </div>
        {notificationsOpen ? (
          <aside className="hei-notification-area" aria-label="Notifications">
            <strong>Notifications</strong>
            {workspace?.notifications?.length ? workspace.notifications.map((item, index) => (
              <button key={item.id || index} type="button" onClick={() => {
                const target = navigation.find((entry) => entry.id === item.target);
                if (target) select(target);
                setNotificationsOpen(false);
              }} disabled={!item.target}>
                <strong>{item.title || 'HEI update'}</strong><span>{item.message || ''}</span>
              </button>
            )) : <p>No new notifications.</p>}
          </aside>
        ) : null}
      </header>

      <aside className="hei-command-sidebar" aria-label="HEI workspace navigation">
        <button
          type="button"
          className="hei-sidebar-toggle"
          onClick={() => onPreferencesChange({ sidebarCollapsed: !preferences.sidebarCollapsed })}
          aria-label={preferences.sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {preferences.sidebarCollapsed ? 'Expand' : 'Collapse'}
        </button>
        <nav>
          {navigation.map((item) => (
            <button
              key={item.id}
              type="button"
              className={activeNavigationId === item.id ? 'active' : ''}
              onClick={() => select(item)}
              disabled={!item.enabled}
              aria-current={activeNavigationId === item.id ? 'page' : undefined}
              title={preferences.sidebarCollapsed ? item.label : undefined}
            >
              <span className="hei-nav-icon" aria-hidden="true">{item.icon.slice(0, 1).toUpperCase()}</span>
              <span className="hei-nav-label">{item.label}</span>
              {item.future ? <small>Future</small> : null}
            </button>
          ))}
        </nav>
      </aside>

      <section className="hei-command-content" aria-label={`${activeItem?.label || 'HEI'} workspace`} aria-busy={busy}>
        <div className="hei-content-heading">
          <div><span>{projectName || 'Current project'}</span><strong>{activeItem?.label || 'Overview'}</strong></div>
          <small>{workspace?.description || 'Engineering Operating Console'}</small>
        </div>
        {children}
      </section>

      <footer className="hei-command-statusbar" aria-label="HEI status">
        <span className={`hei-status-dot ${(workspace?.status.state || 'ready').toLowerCase()}`} aria-hidden="true" />
        <strong>{workspace?.status.message || 'HEI services available'}</strong>
        <span>Project: {projectName || 'Not selected'}</span>
        <span>Role: {roleLabel}</span>
        <span>Workspace: {activeItem?.label || 'Overview'}</span>
        <span className="hei-status-version">HEI {workspace?.version || '7.1'}</span>
      </footer>

      {paletteOpen ? (
        <div className="hei-command-palette-backdrop" role="presentation" onMouseDown={() => setPaletteOpen(false)}>
          <section className="hei-command-palette" role="dialog" aria-modal="true" aria-label="HEI command palette" onMouseDown={(event) => event.stopPropagation()}>
            <div><strong>Command Palette</strong><button type="button" onClick={() => setPaletteOpen(false)} aria-label="Close command palette">Close</button></div>
            {navigation.map((item) => (
              <button key={item.id} type="button" onClick={() => select(item)} disabled={!item.enabled}>
                <span>Open {item.label}</span><small>{item.future ? 'Future workspace' : item.lazy ? 'Loads on selection' : 'Available now'}</small>
              </button>
            ))}
          </section>
        </div>
      ) : null}
    </div>
  );
}

function initials(value: string): string {
  const parts = value.trim().split(/\s+/).filter(Boolean);
  return (parts.length ? parts.slice(0, 2).map((part) => part[0]).join('') : 'HE').toUpperCase();
}

function fallbackNavigation(roleLabel: string): WorkspaceNavigationItem[] {
  const normalized = roleLabel.toLowerCase();
  const isAdmin = normalized.includes('admin');
  const isContributor = isAdmin || normalized.includes('contributor');
  return FALLBACK_NAVIGATION.filter((item) => {
    if (['repository', 'settings', 'administration'].includes(item.id)) return isAdmin;
    if (['approvals', 'agents'].includes(item.id)) return isContributor;
    return true;
  });
}
