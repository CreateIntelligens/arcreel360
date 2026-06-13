// Claude 預設模型 + 進階模型路由卡片。

import { ChevronDown, Loader2, SlidersHorizontal, X } from "lucide-react";
import type { SystemConfigPatch, SystemConfigSettings } from "@/types";
import { MODEL_ROUTING_FIELDS, cardClassName, inputClassName, smallBtnClassName } from "./constants";
import type { AgentDraft, ClearField, UpdateDraft } from "./types";

export interface ClaudeModelSettingsCardProps {
  draft: AgentDraft;
  settings: SystemConfigSettings;
  updateDraft: UpdateDraft;
  handleClearField: ClearField;
  saving: boolean;
  isBusy: boolean;
  clearingField: string | null;
  modelRoutingExpanded: boolean;
  setModelRoutingExpanded: (next: boolean) => void;
}

export function ClaudeModelSettingsCard({
  draft,
  settings,
  updateDraft,
  handleClearField,
  saving,
  isBusy,
  clearingField,
  modelRoutingExpanded,
  setModelRoutingExpanded,
}: ClaudeModelSettingsCardProps) {
  return (
    <div className={cardClassName}>
      <div className="flex items-center justify-between">
        <label htmlFor="agent-model" className="text-sm font-medium text-gray-100">
          預設模型
        </label>
        {settings.anthropic_model && (
          <button
            type="button"
            onClick={() =>
              void handleClearField(
                "anthropic_model",
                { anthropic_model: "" },
                "ANTHROPIC_MODEL",
              )
            }
            disabled={isBusy}
            className="inline-flex items-center gap-1 rounded text-xs text-gray-600 transition-colors hover:text-rose-400 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:ring-2 focus-visible:ring-indigo-500/60 focus-visible:outline-none"
            aria-label="清除已儲存的模型設定"
          >
            {clearingField === "anthropic_model" ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <X className="h-3 w-3" />
            )}
            清除已儲存
          </button>
        )}
      </div>
      <p className="mt-0.5 text-xs text-gray-500">對應 ANTHROPIC_MODEL，用於覆寫預設模型</p>
      <div className="relative mt-2">
        <input
          id="agent-model"
          value={draft.anthropicModel}
          onChange={(e) => updateDraft("anthropicModel", e.target.value)}
          placeholder="ANTHROPIC_MODEL"
          className={`${inputClassName}${draft.anthropicModel ? " pr-8" : ""}`}
          autoComplete="off"
          spellCheck={false}
          name="anthropic_model"
          disabled={saving}
        />
        {draft.anthropicModel && (
          <button
            type="button"
            onClick={() => updateDraft("anthropicModel", "")}
            className={`absolute right-2 top-1/2 -translate-y-1/2 ${smallBtnClassName}`}
            aria-label="清除模型設定輸入"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      <details
        open={modelRoutingExpanded}
        onToggle={(e) => setModelRoutingExpanded(e.currentTarget.open)}
        className="mt-4 rounded-xl border border-gray-800 bg-gray-950/40 p-4"
      >
        <summary className="flex cursor-pointer list-none items-center justify-between text-sm font-medium text-gray-100">
          <span className="inline-flex items-center gap-2">
            <SlidersHorizontal className="h-4 w-4 text-gray-400" />
            進階模型路由
          </span>
          <span className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-gray-800 bg-gray-900 text-gray-500">
            <ChevronDown
              className={`h-4 w-4 transition-transform duration-200 ${
                modelRoutingExpanded ? "rotate-180 text-gray-200" : ""
              }`}
            />
          </span>
        </summary>
        <p className="mt-2 text-xs text-gray-500">
          Claude Agent SDK 支援依能力等級路由到不同模型。留空時會統一使用上方的預設模型。
        </p>
        <div className="mt-4 grid gap-4">
          {MODEL_ROUTING_FIELDS.map(({ key, label, envVar, hint, patchKey }) => {
            const settingsValue = settings[patchKey as keyof SystemConfigSettings] as string | undefined;
            const draftValue = draft[key] as string;
            return (
              <div key={key}>
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-sm font-medium text-gray-100">{label}</div>
                    <div className="text-xs text-gray-500">{hint}</div>
                  </div>
                  {settingsValue && (
                    <button
                      type="button"
                      onClick={() =>
                        void handleClearField(
                          patchKey,
                          { [patchKey]: "" } as SystemConfigPatch,
                          label,
                        )
                      }
                      disabled={isBusy}
                      className="inline-flex items-center gap-1 text-xs text-gray-600 transition-colors hover:text-rose-400 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:ring-2 focus-visible:ring-indigo-500/60 focus-visible:outline-none rounded"
                      aria-label={`清除已儲存的 ${label}`}
                    >
                      {clearingField === patchKey ? (
                        <Loader2 className="h-3 w-3 animate-spin" />
                      ) : (
                        <X className="h-3 w-3" />
                      )}
                      清除
                    </button>
                  )}
                </div>
                <div className="relative mt-1.5">
                  <input
                    value={draftValue}
                    onChange={(e) => updateDraft(key, e.target.value)}
                    placeholder={envVar}
                    className={`${inputClassName}${draftValue ? " pr-8" : ""}`}
                    autoComplete="off"
                    spellCheck={false}
                    disabled={saving}
                  />
                  {draftValue && (
                    <button
                      type="button"
                      onClick={() => updateDraft(key, "")}
                      className={`absolute right-2 top-1/2 -translate-y-1/2 ${smallBtnClassName}`}
                      aria-label={`清除 ${label} 輸入`}
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </details>
    </div>
  );
}
