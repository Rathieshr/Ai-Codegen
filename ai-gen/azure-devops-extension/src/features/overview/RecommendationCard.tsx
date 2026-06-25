import * as React from 'react';
import { Card, SectionHeader, InfoRow, StatusBadge, PrimaryButton } from '../../components/common';
import { useWorkflowStore } from '../../store/workflowStore';
import { useUIStore, WorkspaceId } from '../../store/uiStore';

export function RecommendationCard() {
  const recommendation = useWorkflowStore(state => state.aiRecommendation);
  const setActiveWorkspace = useUIStore(state => state.setActiveWorkspace);

  if (!recommendation) return null;

  return (
    <Card style={{ borderLeft: '4px solid var(--hei-primary)' }}>
      <div className="hei-flex-col hei-gap-md" style={{ marginBottom: 'var(--hei-spacing-md)' }}>
        <SectionHeader 
          title="Recommended Next Action" 
          action={<StatusBadge label="Actionable" type="success" />} 
        />
        <h2 style={{ margin: 0, fontSize: 'var(--hei-font-size-xl)' }}>
          {recommendation.action}
        </h2>
        <p style={{ margin: 0, color: 'var(--hei-text-secondary)' }}>
          {recommendation.reason}
        </p>
      </div>

      <div style={{ background: 'var(--hei-bg)', padding: 'var(--hei-spacing-md)', borderRadius: 'var(--hei-radius)', marginBottom: 'var(--hei-spacing-md)', display: 'flex', flexDirection: 'column', gap: 'var(--hei-spacing-sm)' }}>
        <InfoRow label="Estimated Time" value={recommendation.estimatedTime} />
        <InfoRow label="Estimated Tokens" value={recommendation.estimatedTokens} />
        <InfoRow label="Engineering Impact" value={
          <span style={{ color: 'var(--hei-success)', fontWeight: 600 }}>{recommendation.engineeringImpact}</span>
        } />
      </div>

      <PrimaryButton onClick={() => setActiveWorkspace(recommendation.workspaceId as WorkspaceId)}>
        Go to {recommendation.workspaceId}
      </PrimaryButton>
    </Card>
  );
}
