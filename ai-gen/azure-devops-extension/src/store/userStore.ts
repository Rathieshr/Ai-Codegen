import { create } from 'zustand';

interface UserState {
  profile: {
    name: string;
    email: string;
    role: string;
  } | null;
  setUserProfile: (profile: UserState['profile']) => void;
}

export const useUserStore = create<UserState>((set) => ({
  profile: null,
  setUserProfile: (profile) => set({ profile }),
}));
