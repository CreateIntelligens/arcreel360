/**
 * 集中管理 ApiError 的預設訊息。
 *
 * 設計目的：將前端內部錯誤訊息收斂到單一入口，方便日後 i18n。
 * 注意：來自後端的錯誤訊息（payload.detail / payload.message）優先使用，
 * 此處的訊息是「前端自行 throw」或「後端無回應內容」時的預設值。
 */

import type { ApiErrorCode } from "./_http";

export const ERROR_MESSAGES: Record<ApiErrorCode, string> = {
  UNAUTHORIZED: "認證已過期，請重新登入",
  REQUEST_FAILED: "請求失敗",
  PROJECT_CONTENT_MODE_IMMUTABLE: "專案建立後不支援修改 content_mode",
  IMPORT_FAILED: "匯入失敗",
};

/** 取得指定錯誤碼的預設訊息。 */
export function getDefaultMessage(code: ApiErrorCode): string {
  return ERROR_MESSAGES[code];
}

/**
 * 動作別 fallback 訊息：供 `throwIfNotOk(response, ACTION_ERROR_MESSAGES.xxx)` 使用。
 *
 * 這些訊息描述「呼叫端的動作」（上傳、刪除、儲存…），與 ApiErrorCode 正交，
 * 因此單獨存放。後端若有 `detail` 仍會優先採用。
 */
export const ACTION_ERROR_MESSAGES = {
  UPLOAD_FAILED: "上傳失敗",
  FETCH_FILE_FAILED: "取得檔案內容失敗",
  SAVE_FILE_FAILED: "儲存檔案失敗",
  DELETE_FILE_FAILED: "刪除檔案失敗",
  FETCH_DRAFT_FAILED: "取得草稿內容失敗",
  SAVE_DRAFT_FAILED: "儲存草稿失敗",
} as const;
