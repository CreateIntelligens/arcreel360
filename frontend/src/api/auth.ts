/**
 * 認證相關 API。
 *
 * `/auth/token` 是「取得 token」的端點，因此必須繞過 Authorization header 注入，
 * 並且 401 不應觸發全域登出/重導向，否則登入失敗訊息會被吞掉。
 */

import { getApi } from "./_http";

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

export const authApi = {
  /** 使用者登入，成功返回 access_token。 */
  async login(username: string, password: string): Promise<LoginResponse> {
    const body = new URLSearchParams({
      username,
      password,
      grant_type: "password",
    });
    return getApi().request<LoginResponse>("/auth/token", {
      method: "POST",
      body,
      skipAuth: true,
      omitJsonContentType: true,
    });
  },
};
