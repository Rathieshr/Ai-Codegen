import * as React from 'react';
import { useUIStore, WorkspaceId } from '../../store/uiStore';

const WORKSPACES: { id: WorkspaceId; label: string }[] = [
  { id: 'Overview', label: 'Command Center' },
  { id: 'Planning', label: 'Planning' },
  { id: 'Execution', label: 'Execution' },
  { id: 'QA', label: 'QA Intelligence' },
  { id: 'Admin', label: 'Administration' }
];

export function TopNavigation() {
  const activeWorkspace = useUIStore(state => state.activeWorkspace);
  const setActiveWorkspace = useUIStore(state => state.setActiveWorkspace);

  return (
    <nav style={{
      display: 'flex',
      gap: 'var(--hei-spacing-xl)',
      padding: '0 var(--hei-spacing-lg)',
      borderBottom: '1px solid var(--hei-border)',
      background: 'var(--hei-surface)'
    }}>
      {WORKSPACES.map(ws => {
        const isActive = activeWorkspace === ws.id;
        return (
          <button
            key={ws.id}
            onClick={() => setActiveWorkspace(ws.id)}
            onMouseOver={(e) => {
              if (!isActive) e.currentTarget.style.color = 'var(--hei-primary)';
            }}
            onMouseOut={(e) => {
              if (!isActive) e.currentTarget.style.color = 'var(--hei-text-secondary)';
            }}
            style={{
              background: 'none',
              border: 'none',
              borderBottom: isActive ? '3px solid var(--hei-yellow)' : '3px solid transparent',
              color: isActive ? 'var(--hei-text-primary)' : 'var(--hei-text-secondary)',
              padding: '16px 0 13px 0', /* 3px border */
              fontSize: 'var(--hei-font-size-md)',
              fontWeight: isActive ? 600 : 400,
              cursor: 'pointer',
              transition: 'color 0.2s ease, border-color 0.2s ease'
            }}
          >
            {ws.label}
          </button>
        );
      })}
    </nav>
  );
}
