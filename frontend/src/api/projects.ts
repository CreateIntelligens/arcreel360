/**
 * 專案 CRUD、匯入匯出、概述、樣式參考圖。
 */

import type {
  ProjectData,
  ProjectSummary,
  ImportConflictPolicy,
  ImportProjectResponse,
  ProjectOverview,
  EpisodeScript,
} from "@/types";
import {
  API_BASE,
  ApiError,
  getApi,
  handleUnauthorized,
  normalizeDiagnosticsBucket,
  normalizeExportDiagnostics,
  normalizeImportFailureDiagnostics,
  throwIfNotOk,
  withAuth,
} from "./_http";
import { ACTION_ERROR_MESSAGES, ERROR_MESSAGES } from "./error-messages";
import type { EpisodeSplitPeekResponse,
  EpisodeSplitResponse,
  SuccessResponse,
} from "./types";
import type { ExportDiagnostics } from "@/types";

export const projectsApi = {
  async listProjects(): Promise<{ projects: ProjectSummary[] }> {
    return getApi().request("/projects");
  },

  async createProject(
    title: string,
    style: string = "",
    contentMode: string = "narration",
    aspectRatio: string = "9:16",
    defaultDuration: number | null = null,
  ): Promise<{ success: boolean; name: string; project: ProjectData }> {
    return getApi().request("/projects", {
      method: "POST",
      body: JSON.stringify({
        title,
        style,
        content_mode: contentMode,
        aspect_ratio: aspectRatio,
        default_duration: defaultDuration,
      }),
    });
  },

  async getProject(
    name: string,
  ): Promise<{
    project: ProjectData;
    scripts: Record<string, EpisodeScript>;
    asset_fingerprints?: Record<string, number>;
  }> {
    return getApi().request(`/projects/${encodeURIComponent(name)}`);
  },

  async updateProject(
    name: string,
    updates: Partial<ProjectData>,
  ): Promise<{ success: boolean; project: ProjectData }> {
    if ("content_mode" in updates) {
      throw new ApiError({
        code: "PROJECT_CONTENT_MODE_IMMUTABLE",
        message: ERROR_MESSAGES.PROJECT_CONTENT_MODE_IMMUTABLE,
      });
    }
    return getApi().request(`/projects/${encodeURIComponent(name)}`, {
      method: "PATCH",
      body: JSON.stringify(updates),
    });
  },

  async deleteProject(name: string): Promise<SuccessResponse> {
    return getApi().request(`/projects/${encodeURIComponent(name)}`, {
      method: "DELETE",
    });
  },

  async peekEpisodeSplit(
    name: string,
    body: { source: string; target_chars: number; context?: number },
  ): Promise<EpisodeSplitPeekResponse> {
    return getApi().request(
      `/projects/${encodeURIComponent(name)}/episodes/peek`,
      { method: "POST", body: JSON.stringify(body) },
    );
  },

  async splitEpisode(
    name: string,
    body: {
      source: string;
      episode: number;
      target_chars: number;
      anchor: string;
      context?: number;
      title?: string;
    },
  ): Promise<EpisodeSplitResponse> {
    return getApi().request(
      `/projects/${encodeURIComponent(name)}/episodes/split`,
      { method: "POST", body: JSON.stringify(body) },
    );
  },

  async requestExportToken(
    projectName: string,
    scope: "full" | "current" = "full",
  ): Promise<{ download_token: string; expires_in: number; diagnostics: ExportDiagnostics }> {
    const payload = await getApi().request<{
      download_token: string;
      expires_in: number;
      diagnostics?: unknown;
    }>(
      `/projects/${encodeURIComponent(projectName)}/export/token?scope=${encodeURIComponent(scope)}`,
      { method: "POST" },
    );
    return {
      download_token: payload.download_token,
      expires_in: payload.expires_in,
      diagnostics: normalizeExportDiagnostics(payload.diagnostics),
    };
  },

  getExportDownloadUrl(
    projectName: string,
    downloadToken: string,
    scope: "full" | "current" = "full",
  ): string {
    return `${API_BASE}/projects/${encodeURIComponent(projectName)}/export?download_token=${encodeURIComponent(downloadToken)}&scope=${encodeURIComponent(scope)}`;
  },

  /** 構造剪映草稿下載 URL */
  getJianyingDraftDownloadUrl(
    projectName: string,
    episode: number,
    draftPath: string,
    downloadToken: string,
    jianyingVersion: string = "6",
  ): string {
    return `${API_BASE}/projects/${encodeURIComponent(projectName)}/export/jianying-draft?episode=${encodeURIComponent(episode)}&draft_path=${encodeURIComponent(draftPath)}&download_token=${encodeURIComponent(downloadToken)}&jianying_version=${encodeURIComponent(jianyingVersion)}`;
  },

  async importProject(
    file: File,
    conflictPolicy: ImportConflictPolicy = "prompt",
  ): Promise<ImportProjectResponse> {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("conflict_policy", conflictPolicy);

    const response = await fetch(
      `${API_BASE}/projects/import`,
      withAuth({
        method: "POST",
        body: formData,
      }),
    );

    if (!response.ok) {
      handleUnauthorized(response);

      const payload = await response
        .json()
        .catch(() => ({ detail: response.statusText, errors: [], warnings: [] }));
      const payloadRecord = payload && typeof payload === "object"
        ? payload as Record<string, unknown>
        : {};
      const detail = typeof payloadRecord.detail === "string"
        ? payloadRecord.detail
        : "匯入失敗";
      const error = new ApiError({
        code: "IMPORT_FAILED",
        message: detail,
        status: response.status,
        detail,
        errors: Array.isArray(payloadRecord.errors)
          ? payloadRecord.errors.filter((item): item is string => typeof item === "string")
          : [],
        warnings: Array.isArray(payloadRecord.warnings)
          ? payloadRecord.warnings.filter((item): item is string => typeof item === "string")
          : [],
        conflict_project_name: typeof payloadRecord.conflict_project_name === "string"
          ? payloadRecord.conflict_project_name
          : undefined,
        diagnostics: normalizeImportFailureDiagnostics(payloadRecord.diagnostics),
      });
      throw error;
    }

    const payload = await response.json();
    return {
      ...payload,
      diagnostics: {
        auto_fixed: normalizeDiagnosticsBucket(payload?.diagnostics?.auto_fixed),
        warnings: normalizeDiagnosticsBucket(payload?.diagnostics?.warnings),
      },
    };
  },

  // ==================== 專案概述管理 ====================

  /** 使用 AI 生成專案概述 */
  async generateOverview(
    projectName: string,
    options: { model?: string | null; instruction?: string | null } = {},
  ): Promise<{ success: boolean; overview: ProjectOverview }> {
    return getApi().request(
      `/projects/${encodeURIComponent(projectName)}/generate-overview`,
      {
        method: "POST",
        body: JSON.stringify({
          model: options.model || null,
          instruction: options.instruction || null,
        }),
      },
    );
  },

  /** 更新專案概述（手動編輯） */
  async updateOverview(
    projectName: string,
    updates: Partial<ProjectOverview>,
  ): Promise<SuccessResponse> {
    return getApi().request(
      `/projects/${encodeURIComponent(projectName)}/overview`,
      {
        method: "PATCH",
        body: JSON.stringify(updates),
      },
    );
  },

  // ==================== 風格參考圖 ====================

  /** 上傳風格參考圖 */
  async uploadStyleImage(
    projectName: string,
    file: File,
  ): Promise<{
    success: boolean;
    style_image: string;
    style_description: string;
    url: string;
  }> {
    const formData = new FormData();
    formData.append("file", file);

    const response = await fetch(
      `${API_BASE}/projects/${encodeURIComponent(projectName)}/style-image`,
      withAuth({
        method: "POST",
        body: formData,
      }),
    );

    await throwIfNotOk(response, ACTION_ERROR_MESSAGES.UPLOAD_FAILED);

    return response.json();
  },

  /** 刪除風格參考圖 */
  async deleteStyleImage(
    projectName: string,
  ): Promise<SuccessResponse> {
    return getApi().request(
      `/projects/${encodeURIComponent(projectName)}/style-image`,
      { method: "DELETE" },
    );
  },

  /** 更新風格描述 */
  async updateStyleDescription(
    projectName: string,
    styleDescription: string,
  ): Promise<SuccessResponse> {
    return getApi().request(
      `/projects/${encodeURIComponent(projectName)}/style-description`,
      {
        method: "PATCH",
        body: JSON.stringify({ style_description: styleDescription }),
      },
    );
  },

  /** 更新專案風格標籤 */
  async updateStyle(
    projectName: string,
    style: string,
  ): Promise<SuccessResponse> {
    return getApi().request(
      `/projects/${encodeURIComponent(projectName)}/style`,
      {
        method: "PATCH",
        body: JSON.stringify({ style }),
      },
    );
  },

  /** 利用 AI 從原文與概述中提取設定集實體 */
  async extractLorebook(
    projectName: string,
    body: {
      model?: string | null;
      entity_type: "character" | "clue" | "scene";
      instruction?: string;
    },
  ): Promise<{
    success: boolean;
    data: {
      characters?: Array<{ name: string; description: string; voice_style?: string }>;
      clues?: Array<{ name: string; description: string; importance: string }>;
      scenes?: Array<{ name: string; description: string }>;
    };
  }> {
    return getApi().request(
      `/projects/${encodeURIComponent(projectName)}/lorebook/extract`,
      {
        method: "POST",
        body: JSON.stringify(body),
      },
    );
  },

  /** 批次新增角色 */
  async batchCreateCharacters(
    projectName: string,
    items: Array<{ name: string; description: string; voice_style?: string }>,
  ): Promise<{ success: boolean; characters: Record<string, any> }> {
    return getApi().request(
      `/projects/${encodeURIComponent(projectName)}/characters/batch_create`,
      {
        method: "POST",
        body: JSON.stringify({ items }),
      },
    );
  },

  /** 批次新增道具 */
  async batchCreateClues(
    projectName: string,
    items: Array<{ name: string; description: string; importance?: string }>,
  ): Promise<{ success: boolean; clues: Record<string, any> }> {
    return getApi().request(
      `/projects/${encodeURIComponent(projectName)}/clues/batch_create`,
      {
        method: "POST",
        body: JSON.stringify({ items }),
      },
    );
  },

  /** 批次新增場景 */
  async batchCreateScenes(
    projectName: string,
    items: Array<{ name: string; description: string }>,
  ): Promise<{ success: boolean; scenes: Record<string, any> }> {
    return getApi().request(
      `/projects/${encodeURIComponent(projectName)}/project-scenes/batch_create`,
      {
        method: "POST",
        body: JSON.stringify({ items }),
      },
    );
  },
};
