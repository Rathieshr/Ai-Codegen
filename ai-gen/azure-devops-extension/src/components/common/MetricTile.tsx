import * as React from 'react';

export interface MetricTileProps {
  label: string;
  value: string | number;
  icon?: React.ReactNode;
}

export function MetricTile({ label, value, icon }: MetricTileProps) {
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      gap: 'var(--hei-spacing-xs)',
      padding: 'var(--hei-spacing-md)',
      background: 'var(--hei-bg)',
      borderRadius: 'var(--hei-radius)',
      border: '1px solid var(--hei-border)'
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--hei-spacing-sm)' }}>
        {icon && <span style={{ color: 'var(--hei-text-muted)' }}>{icon}</span>}
        <span style={{ fontSize: 'var(--hei-font-size-sm)', color: 'var(--hei-text-secondary)', fontWeight: 600 }}>{label}</span>
      </div>
      <div style={{ fontSize: 'var(--hei-font-size-xxl)', fontWeight: 700, color: 'var(--hei-text-primary)' }}>
        {value}
      </div>
    </div>
  );
}
