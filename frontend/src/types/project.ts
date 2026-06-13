/**
 * Project-related type definitions.
 *
 * Maps to backend models in:
 * - lib/project_manager.py (ProjectOverview, project.json structure)
 * - lib/status_calculator.py (ProjectStatus, EpisodeMeta computed fields)
 * - server/routers/projects.py (ProjectSummary list response)
 */

export interface ProjectOverview {
  synopsis: string;
  genre: string;
  theme: string;
  world_setting: string;
  generated_at?: string;
}

export interface Character {
  description: string;
  character_sheet?: string;
  voice_style?: string;
  reference_image?: string; // TODO: 未來若支援三視圖（正/側/背），可擴充為 reference_images?: string[] 預留空間
  image_backend?: string | null;
}

export interface Clue {
  description: string;
  importance: "major" | "minor";
  clue_sheet?: string;
  reference_image?: string; // TODO: 同樣可擴充為 reference_images?: string[] 預留空間
  image_backend?: string | null;
}

/**
 * 場景（scene）實體。對應 project.json 的 `scenes` 欄位。
 * 舊專案可能沒有此欄位（ProjectData.scenes 為 optional）。
 */
export interface Scene {
  description: string;
  scene_sheet?: string;
  scene_ref?: string;
  image_backend?: string | null;
}

export interface AspectRatio {
  characters?: string;
  clues?: string;
  storyboard?: string;
  video?: string;
}

export interface ProgressCategory {
  total: number;
  completed: number;
}

export interface EpisodesSummary {
  total: number;
  scripted: number;
  in_production: number;
  completed: number;
}

export interface EpisodeOverrides {
  video_backend?: string | null;
  image_backend?: string | null;
  video_resolution?: string | null;
  image_size?: string | null;
  duration_seconds?: number | null;
}

/** Injected by StatusCalculator.calculate_project_status at read time */
export interface ProjectStatus {
  current_phase: "setup" | "lorebook" | "scripting" | "storyboard" | "video" | "completed";
  phase_progress: number;
  characters: ProgressCategory;
  clues: ProgressCategory;
  scenes: ProgressCategory;
  episodes_summary: EpisodesSummary;
}

export interface EpisodeMeta {
  episode: number;
  title: string;
  script_file: string;
  /** Display order (lower = earlier). Falls back to `episode` when absent. */
  order?: number;
  overrides?: EpisodeOverrides;
  /** Injected by StatusCalculator at read time */
  scenes_count?: number;
  /** Injected by StatusCalculator at read time */
  script_status?: "none" | "segmented" | "generated";
  /** Injected by StatusCalculator at read time */
  status?: "draft" | "scripted" | "in_production" | "completed" | "missing";
  /** Injected by StatusCalculator at read time */
  duration_seconds?: number;
  /** Injected by StatusCalculator at read time */
  storyboards?: ProgressCategory;
  /** Injected by StatusCalculator at read time */
  videos?: ProgressCategory;
}

export interface ProjectData {
  title: string;
  content_mode: "narration" | "drama";
  style: string;
  style_image?: string;
  style_description?: string;
  overview?: ProjectOverview;
  aspect_ratio?: string | AspectRatio;  // 新專案為 string，舊專案可能為 dict
  default_duration?: number | null;     // 新增
  episodes: EpisodeMeta[];
  characters: Record<string, Character>;
  clues: Record<string, Clue>;
  /** 舊專案沒有此欄位，讀取時可能為 undefined */
  scenes?: Record<string, Scene>;
  /** Injected by StatusCalculator.enrich_project at read time */
  status?: ProjectStatus;
  video_backend?: string | null;
  video_model_settings?: Record<string, { resolution?: string | null }>;
  image_backend?: string | null;
  video_generate_audio?: boolean | null;
  text_backend_script?: string | null;
  text_backend_overview?: string | null;
  text_backend_style?: string | null;
  metadata?: {
    created_at: string;
    updated_at: string;
  };
}

/**
 * Summary shape returned by GET /api/v1/projects (list endpoint).
 *
 * Note: `status` may be an empty object `{}` when the project
 * has no project.json or encounters an error during loading.
 */
export interface ProjectSummary {
  name: string;
  title: string;
  style: string;
  thumbnail: string | null;
  status: ProjectStatus | Record<string, never>;
}

export type ImportConflictPolicy = "prompt" | "rename" | "overwrite";

export interface ArchiveDiagnostic {
  code: string;
  message: string;
  location?: string;
}

export interface ImportSuccessDiagnostics {
  auto_fixed: ArchiveDiagnostic[];
  warnings: ArchiveDiagnostic[];
}

export interface ImportFailureDiagnostics {
  blocking: ArchiveDiagnostic[];
  auto_fixable: ArchiveDiagnostic[];
  warnings: ArchiveDiagnostic[];
}

export interface ExportDiagnostics {
  blocking: ArchiveDiagnostic[];
  auto_fixed: ArchiveDiagnostic[];
  warnings: ArchiveDiagnostic[];
}

export interface ImportProjectResponse {
  success: boolean;
  project_name: string;
  project: ProjectData;
  warnings: string[];
  conflict_resolution: "none" | "renamed" | "overwritten";
  diagnostics: ImportSuccessDiagnostics;
}
