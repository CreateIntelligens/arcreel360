import { create } from "zustand";
import type { AppState } from "./app-store-types";
import { createWorkspaceCacheSlice } from "./workspace-cache-store";
import { createWorkspaceFocusSlice } from "./workspace-focus-store";
import { createWorkspaceNotificationSlice } from "./workspace-notification-store";
import { createWorkspacePanelSlice } from "./workspace-panel-store";

export const useAppStore = create<AppState>()((...args) => ({
  ...createWorkspaceFocusSlice(...args),
  ...createWorkspaceNotificationSlice(...args),
  ...createWorkspacePanelSlice(...args),
  ...createWorkspaceCacheSlice(...args),
}));
