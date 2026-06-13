/**
 * 檔案上傳、source 檔案、草稿、檔案 URL。
 */

import { API_BASE, throwIfNotOk, withAuth , getApi} from "./_http";
import { ACTION_ERROR_MESSAGES } from "./error-messages";
import type { DraftInfo, SuccessResponse } from "./types";

export const filesApi = {
  async uploadFile(
    projectName: string,
    uploadType: string,
    file: File,
    name: string | null = null,
  ): Promise<{ success: boolean; path: string; url: string }> {
    const formData = new FormData();
    formData.append("file", file);

    let url = `/projects/${encodeURIComponent(projectName)}/upload/${uploadType}`;
    if (name) {
      url += `?name=${encodeURIComponent(name)}`;
    }

    const response = await fetch(`${API_BASE}${url}`, withAuth({
      method: "POST",
      body: formData,
    }));

    await throwIfNotOk(response, ACTION_ERROR_MESSAGES.UPLOAD_FAILED);

    return response.json();
  },

  async listFiles(
    projectName: string,
  ): Promise<{ files: Record<string, { name: string; size: number; url: string }[]> }> {
    return getApi().request(
      `/projects/${encodeURIComponent(projectName)}/files`,
    );
  },

  getFileUrl(
    projectName: string,
    path: string,
    cacheBust?: number | string | null,
  ): string {
    const base = `${API_BASE}/files/${encodeURIComponent(projectName)}/${path}`;
    if (cacheBust == null || cacheBust === "") {
      return base;
    }

    return `${base}?v=${encodeURIComponent(String(cacheBust))}`;
  },

  // ==================== Source 檔案管理 ====================

  /** 獲取 source 檔案內容 */
  async getSourceContent(
    projectName: string,
    filename: string,
  ): Promise<string> {
    const response = await fetch(
      `${API_BASE}/projects/${encodeURIComponent(projectName)}/source/${encodeURIComponent(filename)}`,
      withAuth(),
    );
    await throwIfNotOk(response, ACTION_ERROR_MESSAGES.FETCH_FILE_FAILED);
    return response.text();
  },

  /** 儲存 source 檔案（新建或更新） */
  async saveSourceFile(
    projectName: string,
    filename: string,
    content: string,
  ): Promise<SuccessResponse> {
    const response = await fetch(
      `${API_BASE}/projects/${encodeURIComponent(projectName)}/source/${encodeURIComponent(filename)}`,
      withAuth({
        method: "PUT",
        headers: { "Content-Type": "text/plain" },
        body: content,
      }),
    );
    await throwIfNotOk(response, ACTION_ERROR_MESSAGES.SAVE_FILE_FAILED);
    return response.json();
  },

  /** 刪除 source 檔案 */
  async deleteSourceFile(
    projectName: string,
    filename: string,
  ): Promise<SuccessResponse> {
    const response = await fetch(
      `${API_BASE}/projects/${encodeURIComponent(projectName)}/source/${encodeURIComponent(filename)}`,
      withAuth({ method: "DELETE" }),
    );
    await throwIfNotOk(response, ACTION_ERROR_MESSAGES.DELETE_FILE_FAILED);
    return response.json();
  },

  // ==================== 草稿檔案管理 ====================

  /** 獲取專案的所有草稿 */
  async listDrafts(
    projectName: string,
  ): Promise<{ drafts: DraftInfo[] }> {
    return getApi().request(
      `/projects/${encodeURIComponent(projectName)}/drafts`,
    );
  },

  /** 獲取草稿內容 */
  async getDraftContent(
    projectName: string,
    episode: number,
    stepNum: number,
  ): Promise<string> {
    const response = await fetch(
      `${API_BASE}/projects/${encodeURIComponent(projectName)}/drafts/${episode}/step${stepNum}`,
      withAuth(),
    );
    await throwIfNotOk(response, ACTION_ERROR_MESSAGES.FETCH_DRAFT_FAILED);
    return response.text();
  },

  /** 儲存草稿內容 */
  async saveDraft(
    projectName: string,
    episode: number,
    stepNum: number,
    content: string,
  ): Promise<SuccessResponse> {
    const response = await fetch(
      `${API_BASE}/projects/${encodeURIComponent(projectName)}/drafts/${episode}/step${stepNum}`,
      withAuth({
        method: "PUT",
        headers: { "Content-Type": "text/plain" },
        body: content,
      }),
    );
    await throwIfNotOk(response, ACTION_ERROR_MESSAGES.SAVE_DRAFT_FAILED);
    return response.json();
  },

  /** 刪除草稿 */
  async deleteDraft(
    projectName: string,
    episode: number,
    stepNum: number,
  ): Promise<SuccessResponse> {
    return getApi().request(
      `/projects/${encodeURIComponent(projectName)}/drafts/${episode}/step${stepNum}`,
      { method: "DELETE" },
    );
  },

  /** 刪除參考圖 */
  async deleteReferenceImage(
    projectName: string,
    resourceType: string,
    resourceId: string,
  ): Promise<SuccessResponse> {
    const response = await fetch(
      `${API_BASE}/projects/${encodeURIComponent(projectName)}/reference-image/${encodeURIComponent(resourceType)}/${encodeURIComponent(resourceId)}`,
      withAuth({ method: "DELETE" }),
    );
    await throwIfNotOk(response, "移除參考圖失敗");
    return response.json();
  },
};
