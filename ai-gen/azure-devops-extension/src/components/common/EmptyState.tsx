import * as React from 'react';

export interface EmptyStateProps {
  title: string;
  description: string;
  icon?: React.ReactNode;
  action?: React.ReactNode;
}

export function EmptyState({ title, description, icon, action }: EmptyStateProps) {
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: 'var(--hei-spacing-xl)',
      background: 'var(--hei-bg)',
      border: '1px dashed var(--hei-border)',
      borderRadius: 'var(--hei-radius)',
      textAlign: 'center',
      gap: 'var(--hei-spacing-md)'
    }}>
      {icon && <div style={{ fontSize: '32px', color: 'var(--hei-text-muted)' }}>{icon}</div>}
      <div>
        <h4 style={{ margin: '0 0 var(--hei-spacing-xs) 0', color: 'var(--hei-text-primary)' }}>{title}</h4>
        <p style={{ margin: 0, color: 'var(--hei-text-secondary)', fontSize: 'var(--hei-font-size-sm)' }}>{description}</p>
      </div>
      {action && <div>{action}</div>}
    </div>
  );
}
