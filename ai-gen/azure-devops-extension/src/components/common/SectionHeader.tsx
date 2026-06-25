import * as React from 'react';

export interface SectionHeaderProps {
  title: string;
  action?: React.ReactNode;
}

export function SectionHeader({ title, action }: SectionHeaderProps) {
  return (
    <div style={{
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      borderBottom: '1px solid var(--hei-border)',
      paddingBottom: 'var(--hei-spacing-sm)',
      margin: 'var(--hei-spacing-lg) 0 var(--hei-spacing-md) 0'
    }}>
      <h3 style={{ margin: 0, fontSize: 'var(--hei-font-size-lg)', fontWeight: 600, color: 'var(--hei-text-primary)' }}>
        {title}
      </h3>
      {action && <div>{action}</div>}
    </div>
  );
}
