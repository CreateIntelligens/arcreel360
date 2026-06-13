import { create } from "zustand";
import { API } from "@/api";
import { getToken, setToken as saveToken, clearToken } from "@/utils/auth";

interface AuthState {
  token: string | null;
  username: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  initialize: () => void;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  setLoading: (loading: boolean) => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  token: null,
  username: null,
  isAuthenticated: false,
  isLoading: true,

  initialize: () => {
    const token = getToken();
    if (token) {
      set({ token, isAuthenticated: true, isLoading: false });
    } else {
      set({ isLoading: false });
    }
  },

  login: async (username, password) => {
    const { access_token: token } = await API.auth.login(username, password);
    saveToken(token);
    set({
      token,
      username,
      isAuthenticated: true,
      isLoading: false,
    });
  },

  logout: () => {
    clearToken();
    set({ token: null, username: null, isAuthenticated: false });
  },

  setLoading: (isLoading) => set({ isLoading }),
}));
