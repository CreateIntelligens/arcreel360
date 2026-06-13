/**
 * 預置供應商管理 API。
 */

import type {
  ProviderConfigDetail,
  ProviderInfo,
  ProviderTestResult,
} from "@/types";
import { getApi } from "./_http";
export const providersApi = {
  /** 獲取所有 provider 列表及狀態。 */
  async getProviders(): Promise<{ providers: ProviderInfo[] }> {
    return getApi().request("/providers");
  },

  /** 獲取指定 provider 的配置詳情（含欄位列表）。 */
  async getProviderConfig(id: string): Promise<ProviderConfigDetail> {
    return getApi().request(`/providers/${encodeURIComponent(id)}/config`);
  },

  /** 更新指定 provider 的配置欄位。 */
  async patchProviderConfig(
    id: string,
    patch: Record<string, string | null>,
  ): Promise<void> {
    return getApi().request(`/providers/${encodeURIComponent(id)}/config`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    });
  },

  /** 測試指定 provider 的連線。 */
  async testProviderConnection(
    id: string,
    credentialId?: number,
  ): Promise<ProviderTestResult> {
    const params = credentialId != null ? `?credential_id=${credentialId}` : "";
    return getApi().request(`/providers/${encodeURIComponent(id)}/test${params}`, {
      method: "POST",
    });
  },
};
