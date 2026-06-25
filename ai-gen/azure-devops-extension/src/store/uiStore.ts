import { create } from 'zustand';

export type WorkspaceId = 'Overview' | 'Planning' | 'Execution' | 'QA' | 'Admin';

interface UIState {
  activeWorkspace: WorkspaceId;
  setActiveWorkspace: (workspaceId: WorkspaceId) => void;
  
  featureFlags: {
    ENABLE_NEW_UI: boolean;
    ENABLE_CONTEXT_CAPSULE: boolean;
    ENABLE_EXECUTION_PACKAGE_V2: boolean;
    ENABLE_REPOSITORY_DRIFT: boolean;
    ENABLE_KNOWLEDGE_REGISTRY: boolean;
  };
  setFeatureFlag: (flag: keyof UIState['featureFlags'], value: boolean) => void;
}

export const useUIStore = create<UIState>((set) => ({
  activeWorkspace: 'Overview',
  setActiveWorkspace: (workspaceId) => set({ activeWorkspace: workspaceId }),
  
  featureFlags: {
    ENABLE_NEW_UI: true,
    ENABLE_CONTEXT_CAPSULE: false,
    ENABLE_EXECUTION_PACKAGE_V2: false,
    ENABLE_REPOSITORY_DRIFT: false,
    ENABLE_KNOWLEDGE_REGISTRY: false,
  },
  setFeatureFlag: (flag, value) => 
    set((state) => ({ 
      featureFlags: { ...state.featureFlags, [flag]: value } 
    })),
}));
