// Claude API Key + Base URL 卡片。

import { Eye, EyeOff, Loader2, X } from "lucide-react";
import type { SystemConfigSettings } from "@/types";
import { cardClassName, inlineClearClassName, inputClassName, smallBtnClassName } from "./constants";
import type { AgentDraft, ClearField, UpdateDraft } from "./types";

export interface ClaudeCredentialsCardProps {
  draft: AgentDraft;
  settings: SystemConfigSettings;
  updateDraft: UpdateDraft;
  handleClearField: ClearField;
  saving: boolean;
  isBusy: boolean;
  clearingField: string | null;
  showKey: boolean;
  setShowKey: (next: boolean | ((prev: boolean) => boolean)) => void;
}

export function ClaudeCredentialsCard({
  draft,
  settings,
  updateDraft,
  handleClearField,
  saving,
  isBusy,
  clearingField,
  showKey,
  setShowKey,
}: ClaudeCredentialsCardProps) {
  return (
    <div className={`${cardClassName} space-y-4`}>
      <div>
        <div className="flex items-center justify-between">
          <label htmlFor="agent-anthropic-key" className="text-sm font-medium text-gray-100">
            API Key
          </label>
          {settings.anthropic_api_key.is_set && (
            <div className="flex items-center text-xs text-gray-500">
              <span className="truncate">
                目前：{settings.anthropic_api_key.masked ?? "已設定"}
              </span>
              <button
                type="button"
                onClick={() =>
                  void handleClearField(
                    "anthropic_api_key",
                    { anthropic_api_key: "" },
                    "Anthropic API Key",
                  )
                }
                disabled={isBusy}
                className={inlineClearClassName}
                aria-label="清除已儲存的 Anthropic API Key"
              >
                {clearingField === "anthropic_api_key" ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <X className="h-3 w-3" />
                )}
              </button>
            </div>
          )}
        </div>
        <p className="mt-0.5 text-xs text-gray-500">對應環境變數 ANTHROPIC_API_KEY</p>
        <div className="relative mt-2">
          <input
            id="agent-anthropic-key"
            type={showKey ? "text" : "password"}
            value={draft.anthropicKey}
            onChange={(e) => updateDraft("anthropicKey", e.target.value)}
            placeholder="sk-ant-…"
            className={`${inputClassName} pr-10`}
            autoComplete="off"
            spellCheck={false}
            name="anthropic_api_key"
            disabled={saving}
          />
          {draft.anthropicKey && (
            <button
              type="button"
              onClick={() => updateDraft("anthropicKey", "")}
              className={`absolute right-8 top-1/2 -translate-y-1/2 ${smallBtnClassName}`}
              aria-label="清除輸入"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
          <button
            type="button"
            onClick={() => setShowKey((v) => !v)}
            className={`absolute right-2 top-1/2 -translate-y-1/2 ${smallBtnClassName}`}
            aria-label={showKey ? "隱藏金鑰" : "顯示金鑰"}
          >
            {showKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        </div>
      </div>

      <div className="border-t border-gray-800 pt-4">
        <div className="flex items-center justify-between">
          <label htmlFor="agent-base-url" className="text-sm font-medium text-gray-100">
            Base URL
          </label>
          {settings.anthropic_base_url && (
            <button
              type="button"
              onClick={() =>
                void handleClearField(
                  "anthropic_base_url",
                  { anthropic_base_url: "" },
                  "Anthropic Base URL",
                )
              }
              disabled={isBusy}
              className="inline-flex items-center gap-1 rounded text-xs text-gray-600 transition-colors hover:text-rose-400 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:ring-2 focus-visible:ring-indigo-500/60 focus-visible:outline-none"
              aria-label="清除已儲存的 Anthropic Base URL"
            >
              {clearingField === "anthropic_base_url" ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <X className="h-3 w-3" />
              )}
              清除已儲存
            </button>
          )}
        </div>
        <p className="mt-0.5 text-xs text-gray-500">
          對應 ANTHROPIC_BASE_URL，留空時使用官方預設位址
        </p>
        <div className="relative mt-2">
          <input
            id="agent-base-url"
            value={draft.anthropicBaseUrl}
            onChange={(e) => updateDraft("anthropicBaseUrl", e.target.value)}
            placeholder="https://anthropic-proxy.example.com"
            className={`${inputClassName}${draft.anthropicBaseUrl ? " pr-8" : ""}`}
            autoComplete="off"
            spellCheck={false}
            name="anthropic_base_url"
            disabled={saving}
          />
          {draft.anthropicBaseUrl && (
            <button
              type="button"
              onClick={() => updateDraft("anthropicBaseUrl", "")}
              className={`absolute right-2 top-1/2 -translate-y-1/2 ${smallBtnClassName}`}
              aria-label="清除 Base URL 輸入"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
