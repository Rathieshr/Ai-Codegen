import * as React from 'react';
import { Card } from '../../components/common';

export interface PlanningStageEditorProps {
  itemType: string;
  inputTitle: string;
  inputDescription: string;
  onTitleChange: (value: string) => void;
  onDescriptionChange: (value: string) => void;
  result?: any;
}

export function PlanningStageEditor({ 
  itemType, 
  inputTitle, 
  inputDescription, 
  onTitleChange, 
  onDescriptionChange,
  result
}: PlanningStageEditorProps) {
  return (
    <Card>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--hei-spacing-lg)' }}>
        <h3 style={{ margin: 0 }}>{itemType} Definition</h3>
        
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--hei-spacing-sm)' }}>
          <label style={{ fontWeight: 600, fontSize: 'var(--hei-font-size-sm)' }}>Title</label>
          <input
            type="text"
            value={inputTitle}
            onChange={(e) => onTitleChange(e.target.value)}
            placeholder={`Enter ${itemType.toLowerCase()} title...`}
            style={{
              padding: 'var(--hei-spacing-md)',
              border: '1px solid var(--hei-border)',
              borderRadius: 'var(--hei-radius-sm)',
              fontSize: 'var(--hei-font-size-md)',
              width: '100%'
            }}
          />
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--hei-spacing-sm)' }}>
          <label style={{ fontWeight: 600, fontSize: 'var(--hei-font-size-sm)' }}>Description & Context</label>
          <textarea
            value={inputDescription}
            onChange={(e) => onDescriptionChange(e.target.value)}
            placeholder={`Describe the ${itemType.toLowerCase()} requirements, scope, and technical context...`}
            rows={5}
            style={{
              padding: 'var(--hei-spacing-md)',
              border: '1px solid var(--hei-border)',
              borderRadius: 'var(--hei-radius-sm)',
              fontSize: 'var(--hei-font-size-md)',
              width: '100%',
              resize: 'vertical',
              fontFamily: 'var(--hei-font-family)'
            }}
          />
        </div>

        {result && (
          <div style={{ marginTop: 'var(--hei-spacing-lg)', borderTop: '1px solid var(--hei-border)', paddingTop: 'var(--hei-spacing-lg)' }}>
            <h4 style={{ margin: '0 0 var(--hei-spacing-md) 0' }}>AI Generated Refinement</h4>
            <div style={{ background: 'var(--hei-background-subtle)', padding: 'var(--hei-spacing-md)', borderRadius: 'var(--hei-radius-md)' }}>
              <pre style={{ margin: 0, whiteSpace: 'pre-wrap', fontFamily: 'var(--hei-font-family)' }}>
                {result.refined_description || JSON.stringify(result, null, 2)}
              </pre>
            </div>
          </div>
        )}
      </div>
    </Card>
  );
}
