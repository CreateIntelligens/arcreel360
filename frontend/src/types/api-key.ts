/** API Key 後設資料（列表展示用，不含完整 key）。 */
export interface ApiKeyInfo {
  id: number;
  name: string;
  key_prefix: string;
  created_at: string;
  expires_at: string | null;
  last_used_at: string | null;
}

/** 建立 API Key 的響應（含完整 key，僅在建立時出現）。 */
export interface CreateApiKeyResponse {
  id: number;
  name: string;
  key: string;
  key_prefix: string;
  created_at: string;
  expires_at: string | null;
}
