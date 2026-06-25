import { create } from 'zustand';

export interface RepositoryDrift {
  knowledgeVersion: string;
  newModules: number;
  modifiedFlows: number;
  architectureChanges: number;
  documentationChanges: number;
}

interface RepositoryState {
  repositoryDrift: RepositoryDrift | null;
  setRepositoryDrift: (drift: RepositoryDrift) => void;
}

export const useRepositoryStore = create<RepositoryState>((set) => ({
  repositoryDrift: {
    knowledgeVersion: 'v1.4.2',
    newModules: 2,
    modifiedFlows: 1,
    architectureChanges: 0,
    documentationChanges: 3,
  },
  setRepositoryDrift: (drift) => set({ repositoryDrift: drift }),
}));
