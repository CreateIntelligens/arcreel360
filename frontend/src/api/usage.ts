/**
 * 用量統計 API。
 */

import type { UsageStatsResponse } from "@/types";
import { getApi } from "./_http";
import type { UsageCallsFilters, UsageStatsFilters } from "./types";

export const usageApi = {
  /** 獲取統計摘要 */
  async getUsageStats(
    filters: UsageStatsFilters = {},
  ): Promise<Record<string, unknown>> {
    const params = new URLSearchParams();
    if (filters.projectName)
      params.append("project_name", filters.projectName);
    if (filters.startDate) params.append("start_date", filters.startDate);
    if (filters.endDate) params.append("end_date", filters.endDate);
    const query = params.toString();
    return getApi().request(`/usage/stats${query ? "?" + query : ""}`);
  },

  /** 獲取呼叫記錄列表 */
  async getUsageCalls(
    filters: UsageCallsFilters = {},
  ): Promise<Record<string, unknown>> {
    const params = new URLSearchParams();
    if (filters.projectName)
      params.append("project_name", filters.projectName);
    if (filters.callType) params.append("call_type", filters.callType);
    if (filters.status) params.append("status", filters.status);
    if (filters.startDate) params.append("start_date", filters.startDate);
    if (filters.endDate) params.append("end_date", filters.endDate);
    if (filters.page) params.append("page", String(filters.page));
    if (filters.pageSize) params.append("page_size", String(filters.pageSize));
    const query = params.toString();
    return getApi().request(`/usage/calls${query ? "?" + query : ""}`);
  },

  /** 獲取有呼叫記錄的專案列表 */
  async getUsageProjects(): Promise<{ projects: string[] }> {
    return getApi().request("/usage/projects");
  },

  /**
   * 獲取按 provider 分組的用量統計。
   * @param params - 可選篩選：provider、start、end（ISO 日期字串）
   */
  async getUsageStatsGrouped(
    params: { provider?: string; start?: string; end?: string } = {},
  ): Promise<UsageStatsResponse> {
    const searchParams = new URLSearchParams();
    searchParams.append("group_by", "provider");
    if (params.provider) searchParams.append("provider", params.provider);
    if (params.start) searchParams.append("start_date", params.start);
    if (params.end) searchParams.append("end_date", params.end);
    return getApi().request(`/usage/stats?${searchParams.toString()}`);
  },
};
