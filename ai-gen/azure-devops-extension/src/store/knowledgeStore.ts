import { create } from 'zustand';

interface KnowledgeState {
  healthStatus: string;
  lastUpdated: string;
  setKnowledgeState: (data: Partial<KnowledgeState>) => void;
}

export const useKnowledgeStore = create<KnowledgeState>((set) => ({
  healthStatus: 'Unknown',
  lastUpdated: 'Never',
  setKnowledgeState: (data) => set((state) => ({ ...state, ...data })),
}));
