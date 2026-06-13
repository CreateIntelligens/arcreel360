/**
 * 費用估算 API。
 */

import type { CostEstimateResponse } from "@/types";
import { getApi } from "./_http";
export const costApi = {
  /** 獲取專案費用估算。 */
  async getCostEstimate(projectName: string): Promise<CostEstimateResponse> {
    return getApi().request(`/projects/${encodeURIComponent(projectName)}/cost-estimate`);
  },
};
