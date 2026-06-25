import * as React from 'react';

export interface PrimaryButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  children: React.ReactNode;
}

export function PrimaryButton({ children, style, ...props }: PrimaryButtonProps) {
  return (
    <button
      {...props}
      style={{
        background: 'var(--hei-primary)',
        color: 'var(--hei-surface)',
        border: 'none',
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
      onMouseOver={(e) => e.currentTarget.style.background = 'var(--hei-primary-hover)'}
      onMouseOut={(e) => e.currentTarget.style.background = 'var(--hei-primary)'}
    >
      {children}
    </button>
  );
}
