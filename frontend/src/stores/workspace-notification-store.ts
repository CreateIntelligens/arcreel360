import type { StateCreator } from "zustand";
import type { WorkspaceNotification, WorkspaceNotificationInput } from "@/types";
import type { AppState, WorkspaceNotificationSlice } from "./app-store-types";

const MAX_WORKSPACE_NOTIFICATIONS = 40;

function buildWorkspaceNotification(
  input: WorkspaceNotificationInput,
): WorkspaceNotification {
  return {
    id: `${Date.now()}-${Math.random()}`,
    text: input.text,
    tone: input.tone ?? "info",
    created_at: Date.now(),
    read: input.read ?? false,
    target: input.target ?? null,
  };
}

export const createWorkspaceNotificationSlice: StateCreator<
  AppState,
  [],
  [],
  WorkspaceNotificationSlice
> = (set) => ({
  toast: null,
  pushToast: (text, tone = "info", options) =>
    set((state) => ({
      toast: { id: `${Date.now()}-${Math.random()}`, text, tone },
      workspaceNotifications: [
        buildWorkspaceNotification({
          text,
          tone,
          target: options?.target ?? null,
        }),
        ...state.workspaceNotifications,
      ].slice(0, MAX_WORKSPACE_NOTIFICATIONS),
    })),
  clearToast: () => set({ toast: null }),
  workspaceNotifications: [],
  pushWorkspaceNotification: (input) =>
    set((state) => ({
      workspaceNotifications: [
        buildWorkspaceNotification(input),
        ...state.workspaceNotifications,
      ].slice(0, MAX_WORKSPACE_NOTIFICATIONS),
    })),
  markWorkspaceNotificationRead: (id) =>
    set((state) => ({
      workspaceNotifications: state.workspaceNotifications.map((item) =>
        item.id === id ? { ...item, read: true } : item
      ),
    })),
  markAllWorkspaceNotificationsRead: () =>
    set((state) => ({
      workspaceNotifications: state.workspaceNotifications.map((item) =>
        item.read ? item : { ...item, read: true }
      ),
    })),
  removeWorkspaceNotification: (id) =>
    set((state) => ({
      workspaceNotifications: state.workspaceNotifications.filter((item) => item.id !== id),
    })),
  clearWorkspaceNotifications: () => set({ workspaceNotifications: [] }),
});
