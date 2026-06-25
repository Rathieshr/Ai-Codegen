import { create } from 'zustand';

export type ReadinessStatus = 'Ready' | 'Needs Refresh' | 'Pending' | 'Blocked';

interface ProjectState {
  engineeringReadiness: {
    repository: ReadinessStatus;
    planning: ReadinessStatus;
    execution: ReadinessStatus;
    qa: ReadinessStatus;
  };
  setEngineeringReadiness: (data: Partial<ProjectState['engineeringReadiness']>) => void;
}

export const useProjectStore = create<ProjectState>((set) => ({
  engineeringReadiness: {
    repository: 'Needs Refresh',
    planning: 'Needs Refresh',
    execution: 'Needs Refresh',
    qa: 'Needs Refresh',
  },
  setEngineeringReadiness: (data) =>
    set((state) => ({
      engineeringReadiness: { ...state.engineeringReadiness, ...data }
    })),
}));
