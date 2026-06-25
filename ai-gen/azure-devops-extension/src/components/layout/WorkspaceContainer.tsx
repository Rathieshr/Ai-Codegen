import * as React from 'react';

export interface WorkspaceContainerProps {
  children: React.ReactNode;
}

export function WorkspaceContainer({ children }: WorkspaceContainerProps) {
  return (
    <main className="hei-container hei-grid" style={{ flex: 1, overflowY: 'auto' }}>
      {children}
    </main>
  );
}
