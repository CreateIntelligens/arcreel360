/**
 * 任務佇列 API + SSE 流式。
 */

import type { TaskItem, TaskStats } from "@/types";
import { API_BASE, getApi, withAuthQuery } from "./_http";
import type {
  TaskCancelAllPreviewResponse,
  TaskCancelPreviewResponse,
  TaskListFilters,
  TaskStreamOptions,
  TaskStreamSnapshotPayload,
  TaskStreamTaskPayload,
} from "./types";

export const tasksApi = {
  async getTask(taskId: string): Promise<TaskItem> {
    return getApi().request(`/tasks/${encodeURIComponent(taskId)}`);
  },

  async listTasks(
    filters: TaskListFilters = {},
  ): Promise<{ items: TaskItem[]; total: number; page: number; page_size: number }> {
    const params = new URLSearchParams();
    if (filters.projectName) params.append("project_name", filters.projectName);
    if (filters.status) params.append("status", filters.status);
    if (filters.taskType) params.append("task_type", filters.taskType);
    if (filters.source) params.append("source", filters.source);
    if (filters.page) params.append("page", String(filters.page));
    if (filters.pageSize) params.append("page_size", String(filters.pageSize));
    const query = params.toString();
    return getApi().request(`/tasks${query ? "?" + query : ""}`);
  },

  async listProjectTasks(
    projectName: string,
    filters: Omit<TaskListFilters, "projectName"> = {},
  ): Promise<{ items: TaskItem[]; total: number; page: number; page_size: number }> {
    const params = new URLSearchParams();
    if (filters.status) params.append("status", filters.status);
    if (filters.taskType) params.append("task_type", filters.taskType);
    if (filters.source) params.append("source", filters.source);
    if (filters.page) params.append("page", String(filters.page));
    if (filters.pageSize) params.append("page_size", String(filters.pageSize));
    const query = params.toString();
    return getApi().request(
      `/projects/${encodeURIComponent(projectName)}/tasks${query ? "?" + query : ""}`,
    );
  },

  async getTaskStats(
    projectName: string | null = null,
  ): Promise<TaskStats> {
    const params = new URLSearchParams();
    if (projectName) params.append("project_name", projectName);
    const query = params.toString();
    return getApi().request(`/tasks/stats${query ? "?" + query : ""}`);
  },

  async cancelPreview(taskId: string): Promise<TaskCancelPreviewResponse> {
    return getApi().request(
      `/tasks/${encodeURIComponent(taskId)}/cancel-preview`,
    );
  },

  async cancelTask(
    taskId: string,
  ): Promise<{ cancelled: TaskItem[]; skipped_running: TaskItem[] }> {
    return getApi().request(`/tasks/${encodeURIComponent(taskId)}/cancel`, {
      method: "POST",
    });
  },

  async cancelAllPreview(
    projectName: string,
  ): Promise<TaskCancelAllPreviewResponse> {
    return getApi().request(
      `/projects/${encodeURIComponent(projectName)}/tasks/cancel-all-preview`,
    );
  },

  async cancelAllQueued(
    projectName: string,
  ): Promise<{ cancelled_count: number; skipped_running_count: number }> {
    return getApi().request(
      `/projects/${encodeURIComponent(projectName)}/tasks/cancel-all`,
      {
        method: "POST",
      },
    );
  },

  openTaskStream(options: TaskStreamOptions = {}): EventSource {
    const params = new URLSearchParams();
    if (options.projectName)
      params.append("project_name", options.projectName);
    const parsedLastEventId = Number(options.lastEventId);
    if (Number.isFinite(parsedLastEventId) && parsedLastEventId > 0) {
      params.append("last_event_id", String(parsedLastEventId));
    }

    const query = params.toString();
    const url = withAuthQuery(`${API_BASE}/tasks/stream${query ? "?" + query : ""}`);
    const source = new EventSource(url);

    const parsePayload = (event: MessageEvent): unknown | null => {
      try {
        return JSON.parse(event.data || "{}");
      } catch (err) {
        console.error("解析 SSE 資料失敗:", err, event.data);
        return null;
      }
    };

    source.addEventListener("snapshot", (event) => {
      const payload = parsePayload(event as MessageEvent);
      if (payload && typeof options.onSnapshot === "function") {
        options.onSnapshot(
          payload as TaskStreamSnapshotPayload,
          event as MessageEvent,
        );
      }
    });

    source.addEventListener("task", (event) => {
      const payload = parsePayload(event as MessageEvent);
      if (payload && typeof options.onTask === "function") {
        options.onTask(
          payload as TaskStreamTaskPayload,
          event as MessageEvent,
        );
      }
    });

    source.onerror = (event: Event) => {
      if (typeof options.onError === "function") {
        options.onError(event);
      }
    };

    return source;
  },
};
