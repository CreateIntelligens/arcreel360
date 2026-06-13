/**
 * Task queue type definitions.
 *
 * Maps to backend models in:
 * - lib/generation_queue.py (GenerationQueue task schema, get_task_stats)
 * - webui/server/routers/tasks.py (API responses)
 */

export type TaskStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";
export type TaskMediaType = "image" | "video";
export type TaskType = "storyboard" | "video" | "character" | "clue" | "scene";

export interface TaskItem {
  task_id: string;
  project_name: string;
  task_type: TaskType;
  media_type: TaskMediaType;
  resource_id: string;
  script_file: string | null;
  /** Parsed from payload_json in the SQLite row */
  payload: Record<string, unknown>;
  status: TaskStatus;
  result: Record<string, unknown> | null;
  error_message: string | null;
  source: "webui" | "agent";
  cancelled_by?: "user" | "cascade" | null;
  queued_at: string;
  started_at: string | null;
  finished_at: string | null;
  updated_at: string;
}

export interface TaskStats {
  queued: number;
  running: number;
  succeeded: number;
  failed: number;
  cancelled: number;
  total: number;
}
