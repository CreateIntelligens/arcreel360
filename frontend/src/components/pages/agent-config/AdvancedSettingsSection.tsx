// 共用進階設定：所有 provider 都會用到的會話清理延遲與最大並行會話數。

import { SlidersHorizontal } from "lucide-react";
import { cardClassName, inputClassName } from "./constants";
import type { AgentDraft, UpdateDraft } from "./types";

export interface AdvancedSettingsSectionProps {
  draft: AgentDraft;
  updateDraft: UpdateDraft;
  saving: boolean;
}

export function AdvancedSettingsSection({
  draft,
  updateDraft,
  saving,
}: AdvancedSettingsSectionProps) {
  return (
    <div className={cardClassName}>
      <details>
        <summary className="flex cursor-pointer select-none items-center gap-2 text-sm font-medium text-gray-400 transition-colors hover:text-gray-200">
          <SlidersHorizontal className="h-4 w-4" />
          進階設定
        </summary>
        <div className="mt-4 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-200">
              會話清理延遲（秒）
            </label>
            <p className="mt-0.5 text-xs text-gray-500">
              會話結束後等待此時間再釋放資源，再次對話時會自動恢復
            </p>
            <input
              type="number"
              min={10}
              max={3600}
              value={draft.cleanupDelaySeconds}
              onChange={(e) => updateDraft("cleanupDelaySeconds", e.target.value)}
              className={`${inputClassName} mt-1.5 max-w-[7.5rem]`}
              disabled={saving}
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-200">
              最大並行會話數
            </label>
            <p className="mt-0.5 text-xs text-gray-500">
              同時維持活躍 AI Agent 會話的上限，超出時會自動釋放最久未使用的會話（被清理的會話會持久化，下一次對話時可恢復）
            </p>
            <input
              type="number"
              min={1}
              max={20}
              value={draft.maxConcurrentSessions}
              onChange={(e) => updateDraft("maxConcurrentSessions", e.target.value)}
              className={`${inputClassName} mt-1.5 max-w-[7.5rem]`}
              disabled={saving}
            />
          </div>
        </div>
      </details>
    </div>
  );
}
