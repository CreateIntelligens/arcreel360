// Claude 供應商專屬設定的容器：API 憑證卡 + 模型設定卡。
//
// 僅當 assistant_provider === "claude" 時顯示。其他 provider 透過共用文字後端，不需此區塊。

import type { SystemConfigSettings } from "@/types";
import { ClaudeCredentialsCard } from "./ClaudeCredentialsCard";
import { ClaudeModelSettingsCard } from "./ClaudeModelSettingsCard";
import { SectionHeading } from "./shared";
import type { AgentDraft, ClearField, UpdateDraft } from "./types";

export interface ClaudeProviderSectionProps {
  draft: AgentDraft;
  settings: SystemConfigSettings;
  updateDraft: UpdateDraft;
  handleClearField: ClearField;
  saving: boolean;
  isBusy: boolean;
  clearingField: string | null;
  showKey: boolean;
  setShowKey: (next: boolean | ((prev: boolean) => boolean)) => void;
  modelRoutingExpanded: boolean;
  setModelRoutingExpanded: (next: boolean) => void;
}

export function ClaudeProviderSection({
  draft,
  settings,
  updateDraft,
  handleClearField,
  saving,
  isBusy,
  clearingField,
  showKey,
  setShowKey,
  modelRoutingExpanded,
  setModelRoutingExpanded,
}: ClaudeProviderSectionProps) {
  return (
    <>
      <div>
        <SectionHeading
          title="API 憑證"
          description="Anthropic API 金鑰是 Claude 供應商運作的必要條件"
        />
        <ClaudeCredentialsCard
          draft={draft}
          settings={settings}
          updateDraft={updateDraft}
          handleClearField={handleClearField}
          saving={saving}
          isBusy={isBusy}
          clearingField={clearingField}
          showKey={showKey}
          setShowKey={setShowKey}
        />
      </div>

      <div>
        <SectionHeading
          title="模型設定"
          description="指定 AI Agent 使用的 Claude 模型。留空時會使用 Claude Agent SDK 的預設值。"
        />
        <ClaudeModelSettingsCard
          draft={draft}
          settings={settings}
          updateDraft={updateDraft}
          handleClearField={handleClearField}
          saving={saving}
          isBusy={isBusy}
          clearingField={clearingField}
          modelRoutingExpanded={modelRoutingExpanded}
          setModelRoutingExpanded={setModelRoutingExpanded}
        />
      </div>
    </>
  );
}
