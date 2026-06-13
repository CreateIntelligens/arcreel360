/**
 * 共用 HTTP helpers。
 *
 * 這個模組集中放置所有 fetch wrapper、Authorization 注入、錯誤處理。
 * 各 domain 模組透過 `this.request(...)` 呼叫(由 index.ts 將 method 掛載到 `API`)。
 * 直接的 fetch wrapper 則 export 為 free function 供 domain 模組複用。
 */

import { getToken, clearToken } from "@/utils/auth";
import type {
  ExportDiagnostics,
  ImportFailureDiagnostics,
} from "@/types";
import { ERROR_MESSAGES } from "./error-messages";

export const API_BASE = "/api/v1";

export type ApiErrorCode =
  | "UNAUTHORIZED"
  | "REQUEST_FAILED"
  | "PROJECT_CONTENT_MODE_IMMUTABLE"
  | "IMPORT_FAILED";

interface ApiErrorOptions {
  code: ApiErrorCode;
  message: string;
  status?: number;
  detail?: unknown;
  errors?: string[];
  warnings?: string[];
  conflict_project_name?: string;
  diagnostics?: ImportFailureDiagnostics;
}

export class ApiError extends Error {
  readonly code: ApiErrorCode;
  readonly status?: number;
  readonly detail?: unknown;
  readonly errors: string[];
  readonly warnings: string[];
  readonly conflict_project_name?: string;
  readonly diagnostics?: ImportFailureDiagnostics;

  constructor(options: ApiErrorOptions) {
    super(options.message);
    this.name = "ApiError";
    this.code = options.code;
    this.status = options.status;
    this.detail = options.detail;
    this.errors = options.errors ?? [];
    this.warnings = options.warnings ?? [];
    this.conflict_project_name = options.conflict_project_name;
    this.diagnostics = options.diagnostics;
    Object.setPrototypeOf(this, ApiError.prototype);
  }
}

function getPayloadDetail(payload: unknown): unknown {
  if (!payload || typeof payload !== "object") {
    return undefined;
  }
  return (payload as { detail?: unknown }).detail;
}

function getErrorMessage(payload: unknown, fallbackMsg: string): string {
  const detail = getPayloadDetail(payload);
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail) && detail.length > 0) {
    const message = detail
      .map((item: string | { msg?: string }) => (
        typeof item === "string" ? item : item?.msg
      ))
      .filter(Boolean)
      .join("; ");
    if (message) return message;
  }
  return fallbackMsg;
}

/**
 * 檢查 fetch 響應狀態，丟擲包含後端錯誤資訊的 Error。
 * 用於不經過 request() 的自定義 fetch 呼叫。
 */
export async function throwIfNotOk(response: Response, fallbackMsg: string): Promise<void> {
  if (!response.ok) {
    handleUnauthorized(response);
    const payload = await response
      .json()
      .catch(() => ({ detail: response.statusText }));
    throw new ApiError({
      code: "REQUEST_FAILED",
      message: getErrorMessage(payload, fallbackMsg),
      status: response.status,
      detail: getPayloadDetail(payload),
    });
  }
}

export function handleUnauthorized(response: Response): void {
  if (response.status !== 401) return;

  clearToken();
  globalThis.location.href = "/login";
  throw new ApiError({
    code: "UNAUTHORIZED",
    message: ERROR_MESSAGES.UNAUTHORIZED,
    status: response.status,
  });
}

/** 為 fetch options 注入 Authorization header */
export function withAuth(options: RequestInit = {}): RequestInit {
  const token = getToken();
  if (!token) return options;
  const headers = new Headers(options.headers);
  headers.set("Authorization", `Bearer ${token}`);
  return { ...options, headers };
}

/** 為 URL 追加 token query param（用於 EventSource） */
export function withAuthQuery(url: string): string {
  const token = getToken();
  if (!token) return url;
  const sep = url.includes("?") ? "&" : "?";
  return `${url}${sep}token=${encodeURIComponent(token)}`;
}

/**
 * `request()` 額外可選的選項。
 *
 * - `skipAuth`: 不注入 Authorization header，且 401 不會觸發全域登出/重定向。
 *   專門給「取得 token 的端點本身」(例如 `/auth/token`) 使用，避免登入頁的
 *   錯誤訊息被吞掉、或誤把當前 (null) token 清掉並重導向 `/login`。
 * - `omitJsonContentType`: 不要自動帶上 `Content-Type: application/json`。
 *   當 body 是 `URLSearchParams` 或 `FormData` 時應該關掉，讓 fetch 自行設定。
 */
export interface RequestOptions extends RequestInit {
  skipAuth?: boolean;
  omitJsonContentType?: boolean;
}

/**
 * 通用請求方法。
 *
 * 注意：本函式同時會作為 `API.request` 的 static 實作匯出。
 * domain 模組請透過 `getApi().request(...)` 呼叫，
 * 以便 `vi.spyOn(API, "request")` 能在測試中被攔截。
 */
export async function request<T = unknown>(
  endpoint: string,
  options: RequestOptions = {},
): Promise<T> {
  const url = `${API_BASE}${endpoint}`;
  const { skipAuth, omitJsonContentType, ...fetchOptions } = options;
  const defaultOptions: RequestInit = omitJsonContentType
    ? {}
    : {
      headers: {
        "Content-Type": "application/json",
      },
    };

  const merged: RequestInit = { ...defaultOptions, ...fetchOptions };
  const finalOptions = skipAuth ? merged : withAuth(merged);
  const response = await fetch(url, finalOptions);

  if (!response.ok) {
    if (!skipAuth) {
      handleUnauthorized(response);
    }
    const payload = await response
      .json()
      .catch(() => ({ detail: response.statusText }));
    throw new ApiError({
      code: "REQUEST_FAILED",
      message: getErrorMessage(payload, ERROR_MESSAGES.REQUEST_FAILED),
      status: response.status,
      detail: getPayloadDetail(payload),
    });
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return response.json();
}

// ==================== Diagnostics 正規化 ====================

export function normalizeDiagnosticsBucket(
  value: unknown,
): { code: string; message: string; location?: string }[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .filter(
      (item): item is { code: string; message: string; location?: string } =>
        Boolean(item)
        && typeof item === "object"
        && typeof (item as { code?: unknown }).code === "string"
        && typeof (item as { message?: unknown }).message === "string",
    )
    .map((item) => ({
      code: item.code,
      message: item.message,
      ...(typeof item.location === "string" ? { location: item.location } : {}),
    }));
}

export function normalizeImportFailureDiagnostics(value: unknown): ImportFailureDiagnostics {
  const payload = (value && typeof value === "object") ? value as Record<string, unknown> : {};
  return {
    blocking: normalizeDiagnosticsBucket(payload.blocking),
    auto_fixable: normalizeDiagnosticsBucket(payload.auto_fixable),
    warnings: normalizeDiagnosticsBucket(payload.warnings),
  };
}

export function normalizeExportDiagnostics(value: unknown): ExportDiagnostics {
  const payload = (value && typeof value === "object") ? value as Record<string, unknown> : {};
  return {
    blocking: normalizeDiagnosticsBucket(payload.blocking),
    auto_fixed: normalizeDiagnosticsBucket(payload.auto_fixed),
    warnings: normalizeDiagnosticsBucket(payload.warnings),
  };
}

// ==================== 共用 URL helpers ====================

export function withScriptFileQuery(path: string, scriptFile: string): string {
  return `${path}?script_file=${encodeURIComponent(scriptFile)}`;
}

// ==================== Late-bound API reference ====================

/**
 * 一個僅暴露 `request` 入口的最小介面。
 * domain 模組透過 `getApi().request(...)` 取得實際的 `request`。
 *
 * 預設綁定到本模組內的 `request`；index.ts 會在組裝 `API` class 後呼叫
 * `setApi(API)`，將 reference 替換為 `API` 物件本身，
 * 如此 `vi.spyOn(API, "request")` 才能攔截到所有 domain 方法的呼叫。
 */
export interface ApiClient {
  request<T = unknown>(endpoint: string, options?: RequestOptions): Promise<T>;
}

let activeApi: ApiClient = { request };

export function setApi(client: ApiClient): void {
  activeApi = client;
}

export function getApi(): ApiClient {
  return activeApi;
}
