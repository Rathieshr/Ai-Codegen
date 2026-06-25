import * as React from 'react';
import { Card, StatusBadge } from '../../components/common';

export type FunnelStage = 'generation' | 'refinement' | 'approval' | 'creation';

export interface PlanningFunnelProps {
  currentStage: FunnelStage;
  itemType: string;
  isApprovalPending: boolean;
  hasChildren: boolean;
  onStageSelect: (stage: FunnelStage) => void;
}

export function PlanningFunnel({ currentStage, itemType, isApprovalPending, hasChildren, onStageSelect }: PlanningFunnelProps) {
  const stages: Array<{ id: FunnelStage; label: string; description: string; status?: string }> = [
    { 
      id: 'generation', 
      label: '1. Generation', 
      description: `Provide context to generate the ${itemType}.`,
      status: 'complete'
    },
    { 
      id: 'refinement', 
      label: '2. Refinement', 
      description: `Review AI recommendations and adjust scope.`,
      status: 'active'
    },
    { 
      id: 'approval', 
      label: '3. Approval', 
      description: `Finalize the ${itemType} definition.`,
      status: isApprovalPending ? 'pending' : 'pending'
    },
    { 
      id: 'creation', 
      label: `4. Create ${itemType === 'Epic' ? 'Features' : 'Stories'}`, 
      description: `Push to ADO and generate child items.`,
      status: hasChildren ? 'complete' : 'pending'
    }
  ];

  return (
    <Card>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--hei-spacing-md)' }}>
        <h3 style={{ margin: 0 }}>Planning Funnel</h3>
        <div style={{ 
          display: 'grid', 
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', 
          gap: 'var(--hei-spacing-md)' 
        }}>
          {stages.map((stage, idx) => (
            <div 
              key={stage.id}
              onClick={() => onStageSelect(stage.id)}
              style={{
                padding: 'var(--hei-spacing-md)',
                borderRadius: 'var(--hei-radius-md)',
                border: `1px solid ${currentStage === stage.id ? 'var(--hei-primary)' : 'var(--hei-border)'}`,
                background: currentStage === stage.id ? 'var(--hei-primary-subtle)' : 'var(--hei-background)',
                cursor: 'pointer',
                transition: 'all 0.2s ease',
                display: 'flex',
                flexDirection: 'column',
                gap: 'var(--hei-spacing-xs)'
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontWeight: 600, color: currentStage === stage.id ? 'var(--hei-primary)' : 'var(--hei-text)' }}>
                  {stage.label}
                </span>
                {stage.status === 'complete' && <StatusBadge label="Ready" type="success" />}
                {stage.status === 'pending' && <StatusBadge label="Not Ready" type="default" />}
              </div>
              <span style={{ fontSize: 'var(--hei-font-size-sm)', color: 'var(--hei-text-secondary)' }}>
                {stage.description}
              </span>
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}
