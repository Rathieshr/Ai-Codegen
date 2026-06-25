import * as React from 'react';

export interface AccordionProps {
  title: React.ReactNode;
  children: React.ReactNode;
  defaultExpanded?: boolean;
}

export function Accordion({ title, children, defaultExpanded = false }: AccordionProps) {
  const [expanded, setExpanded] = React.useState(defaultExpanded);

  return (
    <div style={{ border: '1px solid var(--hei-border)', borderRadius: 'var(--hei-radius)', marginBottom: '8px' }}>
      <button 
        onClick={() => setExpanded(!expanded)}
        style={{
          width: '100%',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '12px 16px',
          background: 'var(--hei-background-subtle)',
          border: 'none',
          cursor: 'pointer',
          textAlign: 'left',
          fontSize: '14px',
          fontWeight: 600,
          color: 'var(--hei-text-primary)'
        }}
      >
        <span>{title}</span>
        <span>{expanded ? '▼' : '▶'}</span>
      </button>
      {expanded && (
        <div style={{ padding: '16px', borderTop: '1px solid var(--hei-border)', background: 'var(--hei-background)' }}>
          {children}
        </div>
      )}
    </div>
  );
}
