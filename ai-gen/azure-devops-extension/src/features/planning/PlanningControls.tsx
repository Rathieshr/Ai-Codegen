import * as React from 'react';
import { Card } from '../../components/common';
import { FunnelStage } from './PlanningFunnel';

export interface PlanningControlsProps {
  currentStage: FunnelStage;
  itemType: string;
  loading: boolean;
  canApprove: boolean;
  canGenerateChildren: boolean;
  onRefine: () => void;
  onApprove: () => void;
  onGenerateChildren: () => void;
  onNextStage: () => void;
}

export function PlanningControls({
  currentStage,
  itemType,
  loading,
  canApprove,
  canGenerateChildren,
  onRefine,
  onApprove,
  onGenerateChildren,
  onNextStage
}: PlanningControlsProps) {
  
  const renderActions = () => {
    switch (currentStage) {
      case 'generation':
        return (
          <button 
            className="hei-btn hei-btn-primary" 
            onClick={() => { onRefine(); onNextStage(); }} 
            disabled={loading}
          >
            {loading ? 'Generating...' : `Generate ${itemType} Draft`}
          </button>
        );
      case 'refinement':
        return (
          <>
            <button className="hei-btn hei-btn-secondary" onClick={onRefine} disabled={loading}>
              Regenerate Draft
            </button>
            <button 
              className="hei-btn hei-btn-primary" 
              onClick={() => { onApprove(); onNextStage(); }} 
              disabled={loading || !canApprove}
            >
              {loading ? 'Approving...' : 'Approve & Continue'}
            </button>
          </>
        );
      case 'approval':
        return (
          <>
            <button 
              className="hei-btn hei-btn-primary" 
              onClick={() => { onGenerateChildren(); onNextStage(); }} 
              disabled={loading || !canGenerateChildren}
            >
              {loading ? 'Generating...' : `Generate ${itemType === 'Epic' ? 'Features' : 'Stories'}`}
            </button>
          </>
        );
      case 'creation':
        return (
          <button className="hei-btn hei-btn-primary" disabled={loading}>
            Create in Azure DevOps
          </button>
        );
      default:
        return null;
    }
  };

  return (
    <Card style={{ 
      marginTop: 'var(--hei-spacing-lg)', 
      position: 'sticky', 
      bottom: '24px', 
      zIndex: 10,
      boxShadow: 'var(--hei-shadow-md)',
      background: 'var(--hei-background)',
      border: '1px solid var(--hei-primary-subtle)'
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ color: 'var(--hei-text-secondary)', fontSize: 'var(--hei-font-size-sm)' }}>
          {loading && <span>Platform is thinking...</span>}
        </div>
        <div style={{ display: 'flex', gap: 'var(--hei-spacing-md)' }}>
          {renderActions()}
        </div>
      </div>
    </Card>
  );
}
