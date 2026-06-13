/**
 * 系統配置。
 */

import type { GetSystemConfigResponse, SystemConfigPatch } from "@/types";
import { getApi } from "./_http";
export const systemApi = {
  async getSystemConfig(): Promise<GetSystemConfigResponse> {
    return getApi().request("/system/config");
  },

  async updateSystemConfig(
    patch: SystemConfigPatch,
  ): Promise<GetSystemConfigResponse> {
    return getApi().request("/system/config", {
      method: "PATCH",
      body: JSON.stringify(patch),
    });
  },
};
