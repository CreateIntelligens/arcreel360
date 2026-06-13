/**
 * 自定義供應商 API。
 */

import type {
  CustomProviderCreateRequest,
  CustomProviderInfo,
  CustomProviderModelInfo,
  CustomProviderModelInput,
  DiscoveredModel,
} from "@/types";
import { getApi } from "./_http";
export const customProvidersApi = {
  async listCustomProviders(
  ): Promise<{ providers: CustomProviderInfo[] }> {
    return getApi().request("/custom-providers");
  },

  async createCustomProvider(
    data: CustomProviderCreateRequest,
  ): Promise<CustomProviderInfo> {
    return getApi().request("/custom-providers", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async getCustomProvider(id: number): Promise<CustomProviderInfo> {
    return getApi().request(`/custom-providers/${id}`);
  },

  async updateCustomProvider(
    id: number,
    data: Partial<Omit<CustomProviderCreateRequest, "api_format" | "models">>,
  ): Promise<void> {
    return getApi().request(`/custom-providers/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    });
  },

  async fullUpdateCustomProvider(
    id: number,
    data: { display_name: string; base_url: string; api_key?: string; models: CustomProviderModelInput[] },
  ): Promise<CustomProviderInfo> {
    return getApi().request(`/custom-providers/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
  },

  async deleteCustomProvider(id: number): Promise<void> {
    return getApi().request(`/custom-providers/${id}`, { method: "DELETE" });
  },

  async replaceCustomProviderModels(
    id: number,
    models: CustomProviderModelInput[],
  ): Promise<CustomProviderModelInfo[]> {
    return getApi().request(`/custom-providers/${id}/models`, {
      method: "PUT",
      body: JSON.stringify({ models }),
    });
  },

  async discoverModels(
    data: { api_format: string; base_url: string; api_key: string },
  ): Promise<{ models: DiscoveredModel[] }> {
    return getApi().request("/custom-providers/discover", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async testCustomConnection(
    data: { api_format: string; base_url: string; api_key: string },
  ): Promise<{ success: boolean; message: string }> {
    return getApi().request("/custom-providers/test", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async testCustomConnectionById(
    id: number,
  ): Promise<{ success: boolean; message: string }> {
    return getApi().request(`/custom-providers/${id}/test`, { method: "POST" });
  },
};
