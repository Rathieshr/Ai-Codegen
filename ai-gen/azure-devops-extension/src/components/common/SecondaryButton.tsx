import * as React from 'react';

export interface SecondaryButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  children: React.ReactNode;
}

export function SecondaryButton({ children, style, ...props }: SecondaryButtonProps) {
  return (
    <button
      {...props}
      style={{
        background: 'transparent',
        color: 'var(--hei-text-primary)',
        border: '1px solid var(--hei-border)',
        borderRadius: 'var(--hei-radius)',
        padding: '6px 16px',
        fontSize: 'var(--hei-font-size-md)',
        fontWeight: 600,
        cursor: 'pointer',
        transition: 'background 0.2s',
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 'var(--hei-spacing-sm)',
        ...style
      }}
      onMouseOver={(e) => e.currentTarget.style.background = 'var(--hei-bg)'}
      onMouseOut={(e) => e.currentTarget.style.background = 'transparent'}
    >
      {children}
    </button>
  );
}
