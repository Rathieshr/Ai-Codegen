import * as React from 'react';

export interface SkeletonLoaderProps {
  width?: string;
  height?: string;
  borderRadius?: string;
  style?: React.CSSProperties;
}

export function SkeletonLoader({ 
  width = '100%', 
  height = '20px', 
  borderRadius = 'var(--hei-radius)',
  style 
}: SkeletonLoaderProps) {
  return (
    <div
      style={{
        width,
        height,
        borderRadius,
        background: 'linear-gradient(90deg, #f3f2f1 25%, #edebe9 50%, #f3f2f1 75%)',
        backgroundSize: '200% 100%',
        animation: 'hei-shimmer 1.5s infinite',
        ...style
      }}
    />
  );
}
