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
  logoDarkSrc?: string;
  busy?: boolean;
  headerActions?: ReactNode;
  hideSidebar?: boolean;
  forcedTheme?: WorkspacePreferences['theme'];
  children: ReactNode;
  onNavigate: (item: WorkspaceNavigationItem) => void;
  onPreferencesChange: (changes: Partial<WorkspacePreferences>) => void;
  onSearch?: (query: string) => Promise<CommandPaletteResult[]>;
  onCommand?: (commandId: string) => void;
};

export type CommandPaletteResult = { id: string; category: string; title: string; subtitle: string; route: string; entityId?: string; score?: number };
type PaletteEntry = CommandPaletteResult & { commandId?: string };
const EMPTY_SEARCH = async (): Promise<CommandPaletteResult[]> => [];
const NOOP_COMMAND = () => undefined;

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
  logoSrc = 'static/hei-icon-light.png',
  logoDarkSrc = 'static/hei-icon-dark.png',
  busy,
  headerActions,
  hideSidebar = false,
  forcedTheme,
  children,
  onNavigate,
  onPreferencesChange,
  onSearch = EMPTY_SEARCH,
  onCommand = NOOP_COMMAND,
}: Props) {
  const storedPreferences = workspace?.preferences || FALLBACK_PREFERENCES;
  const preferences = forcedTheme ? { ...storedPreferences, theme: forcedTheme } : storedPreferences;
  const navigation = workspace?.navigation?.length ? workspace.navigation : fallbackNavigation(roleLabel);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [paletteQuery, setPaletteQuery] = useState('');
  const [remoteResults, setRemoteResults] = useState<CommandPaletteResult[]>([]);
  const [paletteLoading, setPaletteLoading] = useState(false);
  const [activeResult, setActiveResult] = useState(0);
  const [recentIds, setRecentIds] = useState<string[]>(() => readStoredList('hei.palette.recent'));
  const [pinnedIds, setPinnedIds] = useState<string[]>(() => readStoredList('hei.palette.pinned'));
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);
  const activeItem = navigation.find((item) => item.id === activeNavigationId) || navigation[0];
  const availableItems = useMemo(() => navigation.filter((item) => item.enabled), [navigation]);
  const commands = useMemo(() => buildCommands(navigation, activeNavigationId), [navigation, activeNavigationId]);
  const paletteResults = useMemo(() => {
    const query = paletteQuery.trim();
    const local = query ? commands.filter((item) => fuzzyMatch(query, `${item.title} ${item.subtitle}`)) : suggestedCommands(commands, pinnedIds, recentIds, activeNavigationId);
    return dedupeEntries([...local, ...remoteResults]).slice(0, 80);
  }, [commands, paletteQuery, remoteResults, pinnedIds, recentIds, activeNavigationId]);

  useEffect(() => {
    document.documentElement.dataset.heiTheme = preferences.theme;
    document.documentElement.dataset.heiDensity = preferences.density;
  }, [preferences.theme, preferences.density]);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setPaletteOpen(true);
      }
      if (event.key === '/' && document.activeElement?.tagName !== 'INPUT' && document.activeElement?.tagName !== 'TEXTAREA') {
        event.preventDefault();
        setPaletteOpen(true);
      }
      if (event.key === 'Escape') {
        setPaletteOpen(false);
        setNotificationsOpen(false);
        setPaletteQuery('');
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  useEffect(() => {
    if (!paletteOpen) return;
    window.setTimeout(() => searchRef.current?.focus(), 0);
  }, [paletteOpen]);

  useEffect(() => {
    if (!paletteOpen || paletteQuery.trim().length < 2) { setRemoteResults([]); setPaletteLoading(false); return; }
    let active = true;
    setPaletteLoading(true);
    const timer = window.setTimeout(() => void onSearch(paletteQuery.trim()).then((items) => { if (active) setRemoteResults(items); }).catch(() => { if (active) setRemoteResults([]); }).finally(() => { if (active) setPaletteLoading(false); }), 180);
    return () => { active = false; window.clearTimeout(timer); };
  }, [paletteOpen, paletteQuery, onSearch]);

  useEffect(() => { setActiveResult(0); }, [paletteQuery, paletteResults.length]);

  function select(item: WorkspaceNavigationItem) {
    if (!item.enabled) return;
    onNavigate(item);
    setPaletteQuery('');
    setPaletteOpen(false);
  }

  function runEntry(entry: PaletteEntry) {
    if (entry.commandId) onCommand(entry.commandId);
    else {
      const target = navigation.find((item) => item.id === entry.route);
      if (target) onNavigate(target);
    }
    const next = [entry.id, ...recentIds.filter((id) => id !== entry.id)].slice(0, 10);
    setRecentIds(next); storeList('hei.palette.recent', next);
    setPaletteOpen(false); setPaletteQuery(''); setRemoteResults([]);
  }

  function togglePin(entry: PaletteEntry) {
    const next = pinnedIds.includes(entry.id) ? pinnedIds.filter((id) => id !== entry.id) : [entry.id, ...pinnedIds].slice(0, 12);
    setPinnedIds(next); storeList('hei.palette.pinned', next);
  }

  return (
    <div className={`hei-command-shell ${preferences.sidebarCollapsed ? 'sidebar-collapsed' : ''}${hideSidebar ? ' without-sidebar' : ''}`}>
      <header className="hei-command-header">
        <div className="hei-command-brand">
          <span className="hei-command-brand-icon">
            <img className="hei-brand-logo-light" src={logoSrc} alt="Hubbell Engineering Intelligence" />
            <img className="hei-brand-logo-dark" src={logoDarkSrc} alt="" aria-hidden="true" />
          </span>
          <div>
            <strong>HEI</strong>
            <span>Engineering Command Center</span>
          </div>
        </div>
        <button className="hei-global-search" type="button" onClick={() => setPaletteOpen(true)} aria-label="Search HEI and open command palette">
          <span>Search HEI or run a command</span><kbd>{isMacPlatform() ? 'Cmd K' : 'Ctrl K'}</kbd>
        </button>
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
              {!forcedTheme ? <label>Theme
                <select value={preferences.theme} onChange={(event) => onPreferencesChange({ theme: event.target.value as WorkspacePreferences['theme'] })}>
                  <option value="system">System</option><option value="light">Light</option><option value="dark">Dark</option><option value="high-contrast">High Contrast</option>
                </select>
              </label> : null}
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

      {!hideSidebar ? <aside className="hei-command-sidebar" aria-label="HEI workspace navigation">
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
      </aside> : null}

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
            <div className="hei-palette-search">
              <input ref={searchRef} value={paletteQuery} onChange={(event) => setPaletteQuery(event.target.value)} placeholder="Search commands, work items, files, APIs, memory..." aria-label="Search the HEI engineering platform" onKeyDown={(event) => {
                if (event.key === 'ArrowDown') { event.preventDefault(); setActiveResult((value) => Math.min(value + 1, Math.max(0, paletteResults.length - 1))); }
                if (event.key === 'ArrowUp') { event.preventDefault(); setActiveResult((value) => Math.max(0, value - 1)); }
                if (event.key === 'Enter' && paletteResults[activeResult]) { event.preventDefault(); runEntry(paletteResults[activeResult]); }
              }} />
              <kbd>ESC</kbd>
            </div>
            <div className="hei-palette-context"><span>{paletteQuery ? `${paletteResults.length} results` : `Suggested for ${activeItem?.label || 'HEI'}`}</span>{paletteLoading ? <small>Searching platform...</small> : <small>↑↓ navigate · Enter open · Pin to keep</small>}</div>
            <div className="hei-palette-results" role="listbox" aria-label="Command palette results">
              {paletteResults.map((entry, index) => (
                <div className={`hei-palette-result ${index === activeResult ? 'active' : ''}`} key={entry.id} role="option" aria-selected={index === activeResult}>
                  <button type="button" onMouseEnter={() => setActiveResult(index)} onClick={() => runEntry(entry)}>
                    <span><small>{entry.category}</small><strong>{entry.title}</strong></span><em>{entry.subtitle}</em>
                  </button>
                  <button className="hei-palette-pin" type="button" onClick={() => togglePin(entry)} aria-label={`${pinnedIds.includes(entry.id) ? 'Unpin' : 'Pin'} ${entry.title}`}>{pinnedIds.includes(entry.id) ? 'Pinned' : 'Pin'}</button>
                </div>
              ))}
              {!paletteResults.length && !paletteLoading ? <div className="hei-palette-empty"><strong>No matching engineering context</strong><span>Try a work item ID, service, file, repository, or command.</span></div> : null}
            </div>
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

function buildCommands(navigation: WorkspaceNavigationItem[], activeId: string): PaletteEntry[] {
  const routes = navigation.filter((item) => item.enabled).map((item) => ({ id: `command:open-${item.id}`, category: item.id === 'settings' ? 'Settings' : 'Commands', title: item.id === 'agents' ? 'Open Agent Center' : `Open ${item.label}`, subtitle: item.id === activeId ? 'Current workspace' : 'Navigate workspace', route: item.id, commandId: `open:${item.id}` }));
  const quick: PaletteEntry[] = [
    { id: 'command:new-requirement', category: 'Commands', title: 'New Requirement', subtitle: 'Start an engineering requirement', route: 'new-requirement', commandId: 'open:new-requirement' },
    { id: 'command:sync-repository', category: 'Commands', title: 'Sync Repository', subtitle: 'Run repository synchronization', route: 'repository', commandId: 'sync-repository' },
    { id: 'command:open-planning', category: 'Commands', title: 'Open Planning', subtitle: 'Requirements, recommendations, and approvals', route: 'planning', commandId: 'open:planning' },
    { id: 'command:open-execution', category: 'Commands', title: 'Open Execution', subtitle: 'Implementation packages and runtime', route: 'execution', commandId: 'open:execution' },
    { id: 'command:open-activity', category: 'Commands', title: 'Open Activity', subtitle: 'Engineering activity and correlation traces', route: 'activity', commandId: 'open:activity' },
    { id: 'command:refresh-dashboard', category: 'Commands', title: 'Refresh Dashboard', subtitle: 'Reload operational engineering state', route: 'overview', commandId: 'refresh-dashboard' },
    { id: 'command:generate-planning-pack', category: 'Commands', title: 'Generate Planning Pack', subtitle: 'Open requirement intake', route: 'new-requirement', commandId: 'open:new-requirement' },
    { id: 'command:open-repository', category: 'Commands', title: 'Open Repository', subtitle: 'Repository snapshots and engineering graph', route: 'repository', commandId: 'open:repository' },
    { id: 'command:current-sprint', category: 'Commands', title: 'Open Current Sprint', subtitle: 'Azure DevOps sprint intelligence', route: 'azure-devops', commandId: 'open:azure-devops' },
    { id: 'command:open-agents', category: 'Commands', title: 'Open Agent Center', subtitle: 'Agent jobs, health, and failures', route: 'agents', commandId: 'open:agents' },
  ];
  return dedupeEntries([...quick, ...routes]);
}

function suggestedCommands(items: PaletteEntry[], pinned: string[], recent: string[], activeId: string) {
  const priority = [...pinned, ...recent, `command:open-${activeId}`];
  return [...priority.map((id) => items.find((item) => item.id === id)).filter(Boolean) as PaletteEntry[], ...items].filter((item, index, values) => values.findIndex((value) => value.id === item.id) === index).slice(0, 14);
}
function dedupeEntries(items: PaletteEntry[]) { return items.filter((item, index) => items.findIndex((value) => value.id === item.id) === index); }
function fuzzyMatch(query: string, value: string) { let index = 0; const source = value.toLowerCase(); for (const character of query.toLowerCase()) { index = source.indexOf(character, index); if (index < 0) return false; index += 1; } return true; }
function readStoredList(key: string): string[] { try { const value = JSON.parse(localStorage.getItem(key) || '[]'); return Array.isArray(value) ? value.filter((item) => typeof item === 'string') : []; } catch { return []; } }
function storeList(key: string, value: string[]) { try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* Storage is optional in restricted hosts. */ } }
function isMacPlatform() { return typeof navigator !== 'undefined' && String(navigator.platform || navigator.userAgent || '').toLowerCase().includes('mac'); }
