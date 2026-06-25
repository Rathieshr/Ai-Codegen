import { create } from 'zustand';

export interface AIRecommendation {
  action: string;
  reason: string;
  estimatedTime: string;
  estimatedTokens: string;
  engineeringImpact: string;
  workspaceId: string;
}

interface WorkflowState {
  aiRecommendation: AIRecommendation | null;
  setAIRecommendation: (recommendation: AIRecommendation | null) => void;
}

export const useWorkflowStore = create<WorkflowState>((set) => ({
  aiRecommendation: {
    action: 'Generate Tasks',
    reason: 'Story is approved but no tasks exist.',
    estimatedTime: '5s',
    estimatedTokens: '1,500',
    engineeringImpact: 'Unblocks execution phase.',
    workspaceId: 'Planning',
  },
  setAIRecommendation: (recommendation) => set({ aiRecommendation: recommendation }),
}));
