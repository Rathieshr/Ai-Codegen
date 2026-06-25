import * as React from 'react';
import { Card } from '../../components/common';

export interface ChildDraft {
  id: string;
  title: string;
  description: string;
  type: string;
}

export interface PlanningCreationPreviewProps {
  parentItemType: string;
  childDrafts: ChildDraft[];
  onDraftSelectionChange: (id: string, selected: boolean) => void;
}

export function PlanningCreationPreview({
  parentItemType,
  childDrafts,
  onDraftSelectionChange
}: PlanningCreationPreviewProps) {
  const childType = parentItemType === 'Epic' ? 'Features' : 'User Stories';

  if (!childDrafts || childDrafts.length === 0) {
    return (
      <Card>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: 'var(--hei-spacing-xl)' }}>
          <h3 style={{ margin: '0 0 var(--hei-spacing-sm) 0' }}>No {childType} Generated Yet</h3>
          <p style={{ color: 'var(--hei-text-secondary)', margin: 0 }}>
            Approve the {parentItemType} to generate recommended child items.
          </p>
        </div>
      </Card>
    );
  }

  return (
    <Card>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--hei-spacing-lg)' }}>
        <h3 style={{ margin: 0 }}>Review Recommended {childType}</h3>
        <p style={{ color: 'var(--hei-text-secondary)', margin: '0 0 var(--hei-spacing-md) 0' }}>
          Select the items you want to push to Azure DevOps. You can edit them later.
        </p>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--hei-spacing-sm)' }}>
          {childDrafts.map((draft) => (
            <div 
              key={draft.id} 
              style={{
                display: 'flex',
                gap: 'var(--hei-spacing-md)',
                padding: 'var(--hei-spacing-md)',
                border: '1px solid var(--hei-border)',
                borderRadius: 'var(--hei-radius-md)',
                background: 'var(--hei-background)'
              }}
            >
              <input 
                type="checkbox" 
                defaultChecked={true} 
                onChange={(e) => onDraftSelectionChange(draft.id, e.target.checked)}
                style={{ marginTop: '4px' }}
              />
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--hei-spacing-xs)' }}>
                <span style={{ fontWeight: 600, fontSize: 'var(--hei-font-size-md)' }}>{draft.title}</span>
                <span style={{ fontSize: 'var(--hei-font-size-sm)', color: 'var(--hei-text-secondary)' }}>{draft.description}</span>
                <span style={{ 
                  fontSize: '11px', 
                  background: 'var(--hei-background-subtle)', 
                  padding: '2px 6px', 
                  borderRadius: '4px', 
                  width: 'fit-content' 
                }}>
                  {draft.type}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}
