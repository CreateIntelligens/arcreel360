/**
 * API Key 管理。
 */

import type { ApiKeyInfo, CreateApiKeyResponse } from "@/types";
import { getApi } from "./_http";
export const apiKeysApi = {
  /** 列出所有 API Key（不含完整 key）。 */
  async listApiKeys(): Promise<ApiKeyInfo[]> {
    return getApi().request("/api-keys");
  },

  /** 建立新 API Key，返回含完整 key 的響應（僅此一次）。 */
  async createApiKey(
    name: string,
    expiresDays?: number,
  ): Promise<CreateApiKeyResponse> {
    return getApi().request("/api-keys", {
      method: "POST",
      body: JSON.stringify({ name, expires_days: expiresDays ?? null }),
    });
  },

  /** 刪除（吊銷）指定 API Key。 */
  async deleteApiKey(keyId: number): Promise<void> {
    return getApi().request(`/api-keys/${keyId}`, { method: "DELETE" });
  },
};
