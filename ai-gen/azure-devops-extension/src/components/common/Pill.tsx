import * as React from 'react';

export interface PillProps {
  label?: string;
  value: string | React.ReactNode;
  color?: 'default' | 'primary' | 'success' | 'warning' | 'error';
}

export function Pill({ label, value, color = 'default' }: PillProps) {
  let bgColor = 'var(--hei-info-bg)';
  let textColor = 'var(--hei-text-primary)';
  
  if (color === 'primary') {
    bgColor = 'var(--hei-primary)';
    textColor = 'var(--hei-surface)';
  } else if (color === 'success') {
    bgColor = 'var(--hei-success-bg)';
    textColor = 'var(--hei-success)';
  } else if (color === 'warning') {
    bgColor = 'var(--hei-warning-bg)';
    textColor = 'var(--hei-warning)';
  } else if (color === 'error') {
    bgColor = 'var(--hei-error-bg)';
    textColor = 'var(--hei-error)';
  }

  return (
    <div style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: 'var(--hei-spacing-xs)',
      background: bgColor,
      color: textColor,
      padding: '2px 8px',
      borderRadius: '12px',
      fontSize: 'var(--hei-font-size-xs)',
      fontWeight: 600,
      whiteSpace: 'nowrap',
      border: color === 'default' ? '1px solid var(--hei-border)' : '1px solid transparent'
    }}>
      {label && <span style={{ opacity: 0.8, fontWeight: 400 }}>{label}:</span>}
      <span>{value}</span>
    </div>
  );
}
