import * as React from 'react';

export type StatusType = 'success' | 'warning' | 'error' | 'info' | 'default';

export interface StatusBadgeProps {
  label: string;
  type?: StatusType;
}

export function StatusBadge({ label, type = 'default' }: StatusBadgeProps) {
  const getColorStyle = (): React.CSSProperties => {
    switch (type) {
      case 'success':
        return { backgroundColor: 'var(--hei-success-bg)', color: 'var(--hei-success)' };
      case 'warning':
        return { backgroundColor: 'var(--hei-warning-bg)', color: 'var(--hei-warning)' };
      case 'error':
        return { backgroundColor: 'var(--hei-error-bg)', color: 'var(--hei-error)' };
      case 'info':
        return { backgroundColor: 'var(--hei-info-bg)', color: 'var(--hei-info)' };
      default:
        return { backgroundColor: 'var(--hei-info-bg)', color: 'var(--hei-text-primary)' };
    }
  };

  return (
    <span style={{
      ...getColorStyle(),
      padding: '2px 8px',
      borderRadius: '12px',
      fontSize: '12px',
      fontWeight: 600,
      display: 'inline-flex',
      alignItems: 'center',
    }}>
      {label}
    </span>
  );
}
