import * as React from 'react';
import { PageHeader } from '../../components/common';
import { useUIStore } from '../../store/uiStore';
import { PlanningFunnel, FunnelStage } from './PlanningFunnel';
import { PlanningStageEditor } from './PlanningStageEditor';
import { PlanningControls } from './PlanningControls';
import { PlanningCreationPreview } from './PlanningCreationPreview';

export interface PlanningWorkspaceProps {
  legacyComponent?: React.ReactNode;
  planningProps?: any;
}

export function PlanningWorkspace({ legacyComponent, planningProps }: PlanningWorkspaceProps) {
  const isNewPlanningEnabled = useUIStore(state => state.featureFlags.ENABLE_NEW_UI);
  const [currentStage, setCurrentStage] = React.useState<FunnelStage>('generation');

  if (!isNewPlanningEnabled && legacyComponent) {
    return <>{legacyComponent}</>;
  }

  if (!planningProps) {
    return <div>Loading planning workspace...</div>;
  }

  // Destructure state passed down from ProjectIntelligenceTab
  const {
    itemType,
    epicInput,
    featureInput,
    storyInput,
    epicResult,
    featureResult,
    storyResult,
    childDrafts,
    approvalWorkflow,
    loading,
    setEpicInput,
    setFeatureInput,
    setStoryInput,
    setAcceptanceCriteria,
    refineEpic,
    refineFeature,
    refineStory,
    approveEpic,
    approveFeature,
    approveStories,
    generateChildren,
    updateDraftSelection,
    createSelectedChildren
  } = planningProps;

  // Resolve current active state based on item type
  const isEpic = itemType === 'Epic';
  const isFeature = itemType === 'Feature';
  
  const currentInput = isEpic ? epicInput : isFeature ? featureInput : storyInput;
  const currentResult = isEpic ? epicResult : isFeature ? featureResult : storyResult;
  const setInput = isEpic ? setEpicInput : isFeature ? setFeatureInput : setStoryInput;
  const refineAction = isEpic ? refineEpic : isFeature ? refineFeature : refineStory;
  const approveAction = isEpic ? approveEpic : isFeature ? approveFeature : approveStories;
  
  // Wait, approval workflow has keys like 'epic', 'feature', 'features'.
  // isApprovalPending logic is simple: if result exists, we can approve.
  const isApprovalPending = currentResult !== undefined;
  const hasChildren = childDrafts && childDrafts.length > 0;

  return (
    <div style={{ paddingBottom: '120px' }}>
      <PageHeader 
        title="Planning" 
        description={`Refining requirements from ${itemType} definition to engineering execution.`}
      />
      
      <div style={{ display: 'grid', gridTemplateColumns: '250px 1fr', gap: 'var(--hei-spacing-xl)', marginTop: 'var(--hei-spacing-xl)' }}>
        <div>
          <div style={{ position: 'sticky', top: '24px' }}>
            <PlanningFunnel 
              currentStage={currentStage}
              itemType={itemType}
              isApprovalPending={isApprovalPending}
              hasChildren={hasChildren}
              onStageSelect={setCurrentStage}
            />
          </div>
        </div>

        <div>
          {currentStage !== 'creation' ? (
            <PlanningStageEditor 
              itemType={itemType}
              inputTitle={currentInput.title}
              inputDescription={currentInput.description}
              onTitleChange={(val) => setInput({ ...currentInput, title: val })}
              onDescriptionChange={(val) => setInput({ ...currentInput, description: val })}
              result={currentResult}
            />
          ) : (
            <PlanningCreationPreview 
              parentItemType={itemType}
              childDrafts={childDrafts}
              onDraftSelectionChange={updateDraftSelection}
            />
          )}

          <PlanningControls 
            currentStage={currentStage}
            itemType={itemType}
            loading={loading}
            canApprove={isApprovalPending}
            canGenerateChildren={hasChildren}
            onRefine={refineAction}
            onApprove={approveAction}
            onGenerateChildren={generateChildren}
            onNextStage={() => {
              if (currentStage === 'generation') setCurrentStage('refinement');
              else if (currentStage === 'refinement') setCurrentStage('approval');
              else if (currentStage === 'approval') setCurrentStage('creation');
            }}
          />
        </div>
      </div>
    </div>
  );
}
