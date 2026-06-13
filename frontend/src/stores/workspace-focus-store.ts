import type { StateCreator } from "zustand";
import type { AppState, WorkspaceFocusSlice } from "./app-store-types";

export const createWorkspaceFocusSlice: StateCreator<
  AppState,
  [],
  [],
  WorkspaceFocusSlice
> = (set) => ({
  focusedContext: null,
  setFocusedContext: (ctx) => set({ focusedContext: ctx }),

  scrollTarget: null,
  triggerScrollTo: (target) =>
    set({
      scrollTarget: {
        request_id: target.request_id ?? `${Date.now()}-${Math.random()}`,
        type: target.type,
        id: target.id,
        route: target.route ?? "",
        highlight: true,
        highlight_style: target.highlight_style ?? "flash",
        expires_at: target.expires_at ?? Date.now() + 3000,
      },
    }),
  clearScrollTarget: (requestId) =>
    set((state) => {
      if (!requestId || state.scrollTarget?.request_id === requestId) {
        return { scrollTarget: null };
      }
      return state;
    }),
  assistantToolActivitySuppressed: false,
  setAssistantToolActivitySuppressed: (suppressed) =>
    set({ assistantToolActivitySuppressed: suppressed }),
});
