import React from 'react';
import { PipelineStageState, PipelineState } from '../api';
import EpicPlanningRenderer from './epicPlanningRenderer';
import FeaturePlanningRenderer from './featurePlanningRenderer';
import StoryDeliveryRenderer from './storyDeliveryRenderer';
import TaskExecutionRenderer from './taskExecutionRenderer';
import BugFixRenderer from './bugFixRenderer';
import QaTaskRenderer from './qaTaskRenderer';
import UiTaskRenderer from './uiTaskRenderer';
import SpikeRenderer from './spikeRenderer';

export type WorkspaceRendererProps = {
  pipeline?: PipelineState;
  currentStageName: string;
  currentStage?: PipelineStageState;
  currentSummary: string;
  nextAction: string;
  stageOwner: string;
  timelineItems: string[];
  blockingIssues: string[];
  commentWarning?: string;
  commentSyncWarning?: string;
  contextWarnings: string[];
  actionBar: React.ReactNode;
  feedbackPanel: React.ReactNode;
  stagePanel: React.ReactNode;
  draftPanel: React.ReactNode;
  childTaskPanel: React.ReactNode;
  handoffPanel: React.ReactNode;
  retryCommentSync?: () => void;
  loading: boolean;
};

export type WorkspaceRendererComponent = (props: WorkspaceRendererProps) => React.ReactElement;

const RENDERERS: Record<string, WorkspaceRendererComponent> = {
  epic_planning: EpicPlanningRenderer,
  feature_planning: FeaturePlanningRenderer,
  story_delivery: StoryDeliveryRenderer,
  task_execution: TaskExecutionRenderer,
  bug_fix: BugFixRenderer,
  qa_task: QaTaskRenderer,
  ui_task: UiTaskRenderer,
  spike: SpikeRenderer,
};

export function selectWorkspaceRenderer(templateName?: string): WorkspaceRendererComponent {
  return RENDERERS[String(templateName || '').trim()] || StoryDeliveryRenderer;
}

export function SummaryGrid({
  title,
  summary,
  status,
  owner,
  nextAction,
}: {
  title: string;
  summary: string;
  status: string;
  owner: string;
  nextAction: string;
}) {
  return (
    <div className="ai-gen-stage-summary">
      <div className="ai-gen-stage-summary-main">
        <div className="ai-gen-stage-title-row">
          <h3>{title}</h3>
          <span className={`ai-gen-badge ${status || 'unknown'}`}>{status || 'unknown'}</span>
        </div>
        <p className="ai-gen-summary-text">{summary}</p>
        <div className="ai-gen-stage-meta">
          <span><strong>Owner:</strong> {owner}</span>
          <span><strong>Status:</strong> {status || 'unknown'}</span>
        </div>
      </div>
      <div className="ai-gen-stage-sidebar">
        <div className="ai-gen-card-label">Next action</div>
        <div>{nextAction}</div>
      </div>
    </div>
  );
}

export function TemplateWorkspaceShell({
  props,
  title,
  summary,
  extra,
}: {
  props: WorkspaceRendererProps;
  title: string;
  summary: string;
  extra?: React.ReactNode;
}) {
  return (
    <>
      <SummaryGrid
        title={title}
        summary={summary}
        status={props.currentStage?.status || 'unknown'}
        owner={props.stageOwner}
        nextAction={props.nextAction}
      />
      {props.timelineItems.length ? (
        <details className="ai-gen-detail-block">
          <summary>Activity Timeline</summary>
          <ul className="ai-gen-list">
            {props.timelineItems.map((item) => <li key={item}>{item}</li>)}
          </ul>
        </details>
      ) : null}
      {props.commentWarning ? <div className="ai-gen-warning">{props.commentWarning}</div> : null}
      {props.commentSyncWarning ? (
        <div className="ai-gen-warning">
          <div>{props.commentSyncWarning}</div>
          {props.retryCommentSync ? (
            <div className="ai-gen-actions ai-gen-actions-compact">
              <button className="ai-gen-button secondary" onClick={props.retryCommentSync} disabled={props.loading}>Retry Comment Sync</button>
            </div>
          ) : null}
        </div>
      ) : null}
      {props.contextWarnings.length ? (
        <div className="ai-gen-warning">
          <div className="ai-gen-key">Context Warnings</div>
          <ul className="ai-gen-list">
            {props.contextWarnings.map((item) => <li key={item}>{item}</li>)}
          </ul>
        </div>
      ) : null}
      {props.blockingIssues.length ? (
        <div className="ai-gen-warning">
          <div className="ai-gen-key">Blocking issues</div>
          <ul className="ai-gen-list">
            {props.blockingIssues.map((issue) => <li key={issue}>{issue}</li>)}
          </ul>
        </div>
      ) : null}
      {extra}
      {props.actionBar}
      {props.feedbackPanel}
      {props.stagePanel}
      {props.draftPanel}
      {props.childTaskPanel}
      {props.handoffPanel}
    </>
  );
}

export function OutputList({ title, items }: { title: string; items: string[] }) {
  if (!items.length) {
    return null;
  }
  return (
    <div className="ai-gen-subsection">
      <div className="ai-gen-key">{title}</div>
      <ul className="ai-gen-list">
        {items.map((item) => <li key={item}>{item}</li>)}
      </ul>
    </div>
  );
}
