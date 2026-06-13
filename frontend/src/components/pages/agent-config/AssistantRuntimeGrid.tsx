// AssistantRuntimeGrid — provider × 模式 二維選擇器。
//
// 橫向：供應商；縱向：能力等級。不可用的組合顯示為禁用態。

import { Fragment } from "react";

const PROVIDER_BRANDS: Array<{ id: string; label: string }> = [
  { id: "gemini", label: "Gemini" },
  { id: "openai", label: "OpenAI" },
  { id: "claude", label: "Claude" },
];

const RUNTIME_MODES: Array<{ id: "lite" | "full"; label: string; hint: string }> = [
  { id: "lite", label: "對話模式", hint: "純文字交流" },
  { id: "full", label: "工作流模式", hint: "可呼叫工具自動化" },
];

// brand × mode → provider id；null 代表不可用組合
const RUNTIME_MATRIX: Record<string, Record<string, string | null>> = {
  gemini: { lite: "gemini-lite", full: "gemini-full" },
  openai: { lite: "openai-lite", full: "openai-full" },
  claude: { lite: null, full: "claude" },
};

export interface AssistantRuntimeGridProps {
  available: string[];
  value: string;
  onChange: (providerId: string) => void;
  disabled: boolean;
}

export function AssistantRuntimeGrid({
  available,
  value,
  onChange,
  disabled,
}: AssistantRuntimeGridProps) {
  const availableSet = new Set(available);
  return (
    <div>
      <div className="text-sm font-medium text-gray-100">執行時供應商與模式</div>
      <p className="mt-1 text-xs text-[color:var(--wb-text-muted)]">
        橫向：供應商；縱向：能力等級。不可用的組合以禁用態顯示。
      </p>
      <div className="mt-3 overflow-x-auto rounded-xl border border-white/6">
        <div
          data-testid="assistant-runtime-grid"
          className="grid min-w-[35rem] grid-cols-[8rem_repeat(3,minmax(7.5rem,1fr))] text-sm"
        >
          <div className="h-10 bg-black/16" />
          {PROVIDER_BRANDS.map((brand) => (
            <div
              key={brand.id}
              className="flex h-10 items-center justify-center bg-black/16 px-3 text-center text-xs font-medium uppercase tracking-wide text-[color:var(--wb-text-muted)]"
            >
              {brand.label}
            </div>
          ))}
          {RUNTIME_MODES.map((mode) => (
            <Fragment key={mode.id}>
              <div key={`${mode.id}-label`} className="border-t border-white/6 px-3 py-3">
                <div className="font-medium text-[color:var(--wb-text-primary)]">{mode.label}</div>
                <div className="text-xs text-[color:var(--wb-text-muted)]">{mode.hint}</div>
              </div>
              {PROVIDER_BRANDS.map((brand) => {
                const providerId = RUNTIME_MATRIX[brand.id]?.[mode.id] ?? null;
                const isAvailable = providerId !== null && availableSet.has(providerId);
                const isSelected = providerId !== null && providerId === value;
                const buttonLabel = providerId === null ? "未實現" : isSelected ? "✓ 使用中" : "選擇";
                const accessibleState = providerId === null ? "未實現" : isSelected ? "使用中" : "選擇";
                return (
                  <div key={`${mode.id}-${brand.id}`} className="border-t border-white/6 px-3 py-3">
                    <button
                      type="button"
                      disabled={disabled || !isAvailable}
                      onClick={() => providerId && onChange(providerId)}
                      aria-label={`${brand.label} ${mode.label} ${accessibleState}`}
                      title={
                        providerId === null
                          ? `${brand.label} ${mode.label} 暫未實現`
                          : !isAvailable
                            ? "此組合在後端不在合法清單"
                            : ""
                      }
                      className={`inline-flex h-10 w-full items-center justify-center whitespace-nowrap rounded-lg border px-3 text-xs transition-colors ${
                        isSelected
                          ? "border-emerald-400/60 bg-emerald-500/10 text-emerald-100"
                          : isAvailable
                            ? "border-white/8 bg-black/12 text-[color:var(--wb-text-secondary)] hover:bg-black/20 hover:text-[color:var(--wb-text-primary)]"
                            : "cursor-not-allowed border-white/4 bg-black/8 text-[color:var(--wb-text-dim)]"
                      }`}
                    >
                      {buttonLabel}
                    </button>
                  </div>
                );
              })}
            </Fragment>
          ))}
        </div>
      </div>
    </div>
  );
}
