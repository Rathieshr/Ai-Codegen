import * as React from 'react';

export interface InfoRowProps {
  label: React.ReactNode;
  value: React.ReactNode;
}

export function InfoRow({ label, value }: InfoRowProps) {
  return (
    <div style={{ display: 'flex', marginBottom: '8px', fontSize: '13px' }}>
      <div style={{ width: '140px', color: 'var(--hei-text-secondary)', fontWeight: 600 }}>
        {label}
      </div>
      <div style={{ flex: 1, color: 'var(--hei-text-primary)' }}>
        {value}
      </div>
    </div>
  );
}
