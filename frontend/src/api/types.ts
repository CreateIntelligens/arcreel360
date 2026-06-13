/**
 * API 模組相關的輔助型別定義。
 *
 * 這些 type 都會從 `@/api` 重新匯出，外部 import 路徑不變。
 */

import type {
  TaskItem,
  TaskStats,
  ProjectChangeBatchPayload,
  ProjectEventSnapshotPayload,
} from "@/types";

/** Version metadata returned by the versions API. */
export interface VersionInfo {
  version: number;
  filename: string;
  created_at: string;
  file_size: number;
  is_current: boolean;
  file_url?: string;
  prompt?: string;
  model?: string;
  provider?: string;
  aspect_ratio?: string;
  image_size?: string;
  resolution?: string;
  duration_seconds?: number;
  negative_prompt?: string;
  reference_images?: { name: string; label?: string }[];
  source_clips?: string[];
  restored_from?: number;
}

/** Options for `API.openTaskStream`. */
export interface TaskStreamOptions {
  projectName?: string;
  lastEventId?: number | string;
  onSnapshot?: (payload: TaskStreamSnapshotPayload, event: MessageEvent) => void;
  onTask?: (payload: TaskStreamTaskPayload, event: MessageEvent) => void;
  onError?: (event: Event) => void;
}

export interface TaskStreamSnapshotPayload {
  tasks: TaskItem[];
  stats: TaskStats;
}

export interface TaskStreamTaskPayload {
  action: "created" | "updated";
  task: TaskItem;
  stats: TaskStats;
}

export interface TaskCancelPreviewItem {
  task_id: string;
  task_type: string;
  resource_id: string;
}

export interface TaskCancelPreviewResponse {
  task: TaskCancelPreviewItem;
  cascaded: TaskCancelPreviewItem[];
}

export interface TaskCancelAllPreviewResponse {
  queued_count: number;
}

export interface ProjectEventStreamOptions {
  projectName: string;
  onSnapshot?: (payload: ProjectEventSnapshotPayload, event: MessageEvent) => void;
  onChanges?: (payload: ProjectChangeBatchPayload, event: MessageEvent) => void;
  onError?: (event: Event) => void;
}

/** Filters for `API.listTasks` and `API.listProjectTasks`. */
export interface TaskListFilters {
  projectName?: string;
  status?: string;
  taskType?: string;
  source?: string;
  page?: number;
  pageSize?: number;
}

/** Filters for `API.getUsageStats` and `API.getUsageCalls`. */
export interface UsageStatsFilters {
  projectName?: string;
  startDate?: string;
  endDate?: string;
}

export interface UsageCallsFilters {
  projectName?: string;
  callType?: string;
  status?: string;
  startDate?: string;
  endDate?: string;
  page?: number;
  pageSize?: number;
}

/** Generic success response used by many endpoints. */
export interface SuccessResponse {
  success: boolean;
  message?: string;
}

/** Draft metadata returned by listDrafts. */
export interface DraftInfo {
  episode: number;
  step: number;
  filename: string;
  modified_at: string;
}

export interface EpisodeSplitBreakpoint {
  offset: number;
  char: string;
  type: "sentence" | "paragraph";
  distance: number;
}

export interface EpisodeSplitPeekResponse {
  total_chars: number;
  target_chars: number;
  target_offset: number;
  context_before: string;
  context_after: string;
  nearby_breakpoints: EpisodeSplitBreakpoint[];
}

export interface EpisodeSplitResponse {
  episode: number;
  episode_file: string;
  remaining_file: string;
  part_before_chars: number;
  part_after_chars: number;
  split_pos: number;
  anchor_match_count: number;
}

/**
 * `this` 在 mixin function 中的型別表示，提供 `request()` 入口。
 * domain 模組宣告 method 時用 `function (this: ApiThis, ...)`。
 */
export interface ApiThis {
  request<T = unknown>(endpoint: string, options?: RequestInit): Promise<T>;
}
