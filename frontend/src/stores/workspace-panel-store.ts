import type { StateCreator } from "zustand";
import type { AppState, WorkspacePanelSlice } from "./app-store-types";

const LOCAL_STORAGE_KEY = "arcreel_assistant_panel_open";

const getInitialAssistantPanelOpen = (): boolean => {
  if (typeof window === "undefined" || !window.localStorage) return true;
  const stored = localStorage.getItem(LOCAL_STORAGE_KEY);
  if (stored === null) return true;
  return stored === "true";
};

const safeSetLocalStorage = (value: boolean) => {
  if (typeof window !== "undefined" && window.localStorage) {
    localStorage.setItem(LOCAL_STORAGE_KEY, String(value));
  }
};

export const createWorkspacePanelSlice: StateCreator<
  AppState,
  [],
  [],
  WorkspacePanelSlice
> = (set) => ({
  assistantPanelOpen: getInitialAssistantPanelOpen(),
  toggleAssistantPanel: () =>
    set((state) => {
      const nextOpen = !state.assistantPanelOpen;
      safeSetLocalStorage(nextOpen);
      return { assistantPanelOpen: nextOpen };
    }),
  setAssistantPanelOpen: (open) => {
    safeSetLocalStorage(open);
    set({ assistantPanelOpen: open });
  },
  taskHudOpen: false,
  setTaskHudOpen: (open) => set({ taskHudOpen: open }),
});
