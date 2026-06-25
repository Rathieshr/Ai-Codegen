import { create } from 'zustand';

interface ExecutionState {
  currentWorkItem: any; // We'll type this later
  activePackageId: string | null;
  setExecutionState: (data: Partial<ExecutionState>) => void;
}

export const useExecutionStore = create<ExecutionState>((set) => ({
  currentWorkItem: null,
  activePackageId: null,
  setExecutionState: (data) => set((state) => ({ ...state, ...data })),
}));
