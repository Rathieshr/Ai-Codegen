export type PlannerStage =
  | 'refined_story'
  | 'acceptance_criteria'
  | 'tasks'
  | 'azure_devops_creation'
  | 'success';

export type PlannerTask = {
  id: string;
  title: string;
  description: string;
  estimated_effort?: string;
  status: 'pending' | 'creating' | 'created' | 'failed';
  azure_work_item_id?: number | null;
  error?: string | null;
};

export type PlannerSession = {
  session_id: string;
  requirement: string;
  current_stage: PlannerStage;
  source_work_item_id?: number | null;
  source_work_item_type?: string;
  planner_kind?: 'epic' | 'feature' | 'user_story' | 'story';
  story: {
    title: string;
    description: string;
    business_value: string;
  };
  acceptance_criteria: string[];
  tasks: PlannerTask[];
  code_generation_prompt: string;
  question: string;
  user_input_hint: string;
  story_approved: boolean;
  acceptance_approved: boolean;
  tasks_approved: boolean;
  created_story_id?: number | null;
  created_story_status?: 'pending' | 'creating' | 'created' | 'failed';
  created_story_error?: string | null;
  created_tasks: Array<{
    id?: string;
    title: string;
    status: 'pending' | 'creating' | 'created' | 'failed';
    azure_work_item_id?: number | null;
    error?: string | null;
  }>;
  created_summary?: {
    story?: {
      azure_work_item_id?: number | null;
      status?: string;
      error?: string | null;
    };
    tasks?: Array<{
      id?: string;
      title: string;
      status: string;
      azure_work_item_id?: number | null;
      error?: string | null;
    }>;
  };
  error_message?: string;
  updated_at?: string;
};

export type WorkItemContext = {
  id: number;
  title: string;
  type: string;
  description: string;
  acceptanceCriteria: string;
  comments: string[];
  project: string;
  collectionUri?: string;
};

export type CreationPreview = {
  session_id: string;
  current_stage: string;
  preview: {
    mode?: 'epic' | 'feature' | 'user_story' | 'story';
    parent_work_item_id?: number | null;
    parent_work_item_type?: string;
    story: {
      type: string;
      title: string;
      description: string;
      business_value: string;
      acceptance_criteria: string[];
      fields: Record<string, string | null>;
    } | null;
    tasks: Array<{
      id: string;
      type: string;
      title: string;
      description: string;
      estimated_effort?: string;
      fields: Record<string, string | null>;
    }>;
  };
};

export type PlannerViewState = {
  loading: boolean;
  loadingMessage: string;
  error: string;
  session?: PlannerSession;
  workItem?: WorkItemContext;
  preview?: CreationPreview;
  activity?: string[];
};
