/**
 * 資源版本歷史與回滾。
 */

import type { SuccessResponse, VersionInfo } from "./types";
import { getApi } from "./_http";

export const versionsApi = {
  /**
   * 獲取資源版本列表
   * @param projectName - 專案名稱
   * @param resourceType - 資源型別 (storyboards, videos, characters, clues, scenes)
   * @param resourceId - 資源 ID
   */
  async getVersions(
    projectName: string,
    resourceType: string,
    resourceId: string,
  ): Promise<{
    resource_type: string;
    resource_id: string;
    current_version: number;
    versions: VersionInfo[];
  }> {
    return getApi().request(
      `/projects/${encodeURIComponent(projectName)}/versions/${encodeURIComponent(resourceType)}/${encodeURIComponent(resourceId)}`,
    );
  },

  /**
   * 還原到指定版本
   */
  async restoreVersion(
    projectName: string,
    resourceType: string,
    resourceId: string,
    version: number,
  ): Promise<SuccessResponse & { file_path?: string; asset_fingerprints?: Record<string, number> }> {
    return getApi().request(
      `/projects/${encodeURIComponent(projectName)}/versions/${encodeURIComponent(resourceType)}/${encodeURIComponent(resourceId)}/restore/${version}`,
      { method: "POST" },
    );
  },
};
