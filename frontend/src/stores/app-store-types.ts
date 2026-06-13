import type {
  WorkspaceFocusTarget,
  WorkspaceFocusTargetInput,
  WorkspaceNotification,
  WorkspaceNotificationInput,
  WorkspaceNotificationTarget,
} from "@/types";

export interface Toast {
  id: string;
  text: string;
  tone: "info" | "success" | "error" | "warning";
}

export interface ToastOptions {
  target?: WorkspaceNotificationTarget | null;
}

export interface FocusedContext {
  type: "character" | "clue" | "segment";
  id: string;
}

export interface WorkspaceFocusSlice {
  focusedContext: FocusedContext | null;
  setFocusedContext: (ctx: FocusedContext | null) => void;
  scrollTarget: WorkspaceFocusTarget | null;
  triggerScrollTo: (target: WorkspaceFocusTargetInput) => void;
  clearScrollTarget: (requestId?: string) => void;
  assistantToolActivitySuppressed: boolean;
  setAssistantToolActivitySuppressed: (suppressed: boolean) => void;
}

export interface WorkspaceNotificationSlice {
  toast: Toast | null;
  pushToast: (text: string, tone?: Toast["tone"], options?: ToastOptions) => void;
  clearToast: () => void;
  workspaceNotifications: WorkspaceNotification[];
  pushWorkspaceNotification: (input: WorkspaceNotificationInput) => void;
  markWorkspaceNotificationRead: (id: string) => void;
  markAllWorkspaceNotificationsRead: () => void;
  removeWorkspaceNotification: (id: string) => void;
  clearWorkspaceNotifications: () => void;
}

export interface WorkspacePanelSlice {
  assistantPanelOpen: boolean;
  toggleAssistantPanel: () => void;
  setAssistantPanelOpen: (open: boolean) => void;
  taskHudOpen: boolean;
  setTaskHudOpen: (open: boolean) => void;
}

export interface WorkspaceCacheSlice {
  sourceFilesVersion: number;
  invalidateSourceFiles: () => void;
  entityRevisions: Record<string, number>;
  invalidateEntities: (keys: string[]) => void;
  invalidateAllEntities: () => void;
  getEntityRevision: (key: string) => number;
}

export type AppState =
  & WorkspaceFocusSlice
  & WorkspaceNotificationSlice
  & WorkspacePanelSlice
  & WorkspaceCacheSlice;
