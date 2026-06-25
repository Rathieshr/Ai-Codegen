import * as React from 'react';

export interface CardProps {
  children: React.ReactNode;
  style?: React.CSSProperties;
  className?: string;
}

export function Card({ children, style, className = '' }: CardProps) {
  return (
    <div 
      className={`hei-card ${className}`}
      style={style}
    >
      {children}
    </div>
  );
}
