import * as React from 'react';
import { Pill } from '../common/Pill';

export function StickyContextBar() {
  return (
    <div style={{
      position: 'sticky',
      top: 0,
      zIndex: 10,
      background: 'var(--hei-surface)',
      borderBottom: '1px solid var(--hei-border)',
      padding: 'var(--hei-spacing-sm) var(--hei-spacing-lg)',
      display: 'flex',
      gap: 'var(--hei-spacing-md)',
      alignItems: 'center',
      boxShadow: 'var(--hei-shadow-sm)',
      flexWrap: 'wrap'
    }}>
      <Pill label="Work Item" value="Loading..." color="primary" />
      <Pill label="State" value="Loading..." />
      <Pill label="Role" value="Developer" />
      <div style={{ flex: 1 }} />
      <Pill label="Knowledge" value="vLatest" color="success" />
      <Pill label="Repository" value="Analyzed" color="success" />
      <Pill label="Action" value="Ready to Generate" color="warning" />
    </div>
  );
}
