import { useCallback, useEffect, useRef, useState } from "react";
import { Bot, Loader2, Terminal } from "lucide-react";
import { useWarnUnsaved } from "@/hooks/useWarnUnsaved";
import { API } from "@/api";
import { useAppStore } from "@/stores/app-store";
import { useConfigStatusStore } from "@/stores/config-status-store";
import type { GetSystemConfigResponse, SystemConfigPatch } from "@/types";
import { TabSaveFooter } from "./TabSaveFooter";
import { AdvancedSettingsSection } from "./agent-config/AdvancedSettingsSection";
import { ClaudeProviderSection } from "./agent-config/ClaudeProviderSection";
import { ProviderSelector } from "./agent-config/ProviderSelector";
import { EMPTY_DRAFT, buildDraft, buildPatch, deepEqual } from "./agent-config/draft-utils";
import type { AgentDraft } from "./agent-config/types";

interface AgentConfigTabProps {
  visible: boolean;
}

export function AgentConfigTab({ visible }: AgentConfigTabProps) {
  const [remoteData, setRemoteData] = useState<GetSystemConfigResponse | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [draft, setDraft] = useState<AgentDraft>(EMPTY_DRAFT);
  const savedRef = useRef<AgentDraft>(EMPTY_DRAFT);
  const [saving, setSaving] = useState(false);
  const [clearingField, setClearingField] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [showKey, setShowKey] = useState(false);
  const [modelRoutingExpanded, setModelRoutingExpanded] = useState(false);

  // Load config on mount
  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const res = await API.getSystemConfig();
      setRemoteData(res);
      const d = buildDraft(res);
      savedRef.current = d;
      setDraft(d);
    } catch (err) {
      setLoadError((err as Error).message);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const isDirty = !deepEqual(draft, savedRef.current);
  useWarnUnsaved(isDirty);

  const updateDraft = useCallback(
    <K extends keyof AgentDraft>(key: K, value: AgentDraft[K]) => {
      setDraft((prev) => ({ ...prev, [key]: value }));
      setSaveError(null);
    },
    [],
  );

  const handleSave = useCallback(async () => {
    const patch = buildPatch(draft, savedRef.current);
    if (Object.keys(patch).length === 0) return;
    setSaving(true);
    setSaveError(null);
    try {
      const res = await API.updateSystemConfig(patch);
      setRemoteData(res);
      const newDraft = buildDraft(res);
      savedRef.current = newDraft;
      setDraft(newDraft);
      useConfigStatusStore.getState().refresh();
      useAppStore.getState().pushToast("ArcReel AI Agent 設定已儲存", "success");
    } catch (err) {
      setSaveError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }, [draft]);

  const handleReset = useCallback(() => {
    setDraft(savedRef.current);
    setSaveError(null);
  }, []);

  // Clear a single field immediately via PATCH
  const handleClearField = useCallback(
    async (fieldId: string, patch: SystemConfigPatch, label: string) => {
      setClearingField(fieldId);
      try {
        const res = await API.updateSystemConfig(patch);
        setRemoteData(res);
        const nextSavedDraft = buildDraft(res);
        savedRef.current = nextSavedDraft;
        setDraft(nextSavedDraft);
        useConfigStatusStore.getState().refresh();
        useAppStore.getState().pushToast(`${label} 已清除`, "success");
      } catch (err) {
        useAppStore.getState().pushToast(`清除失敗：${(err as Error).message}`, "error");
      } finally {
        setClearingField(null);
      }
    },
    [],
  );

  const isBusy = saving || clearingField !== null;

  // Loading / error states
  if (loadError) {
    return (
      <div className={visible ? "px-6 py-8" : "hidden"}>
        <div className="text-sm text-[color:var(--wb-danger)]">載入失敗：{loadError}</div>
        <button
          type="button"
          onClick={() => void load()}
          className="workbench-button-secondary mt-3 inline-flex items-center gap-2 rounded-xl px-3 py-2 text-sm"
        >
          <Loader2 className="h-4 w-4" />
          重試
        </button>
      </div>
    );
  }

  if (!remoteData) {
    return (
      <div className={visible ? "flex items-center gap-2 px-6 py-8 text-[color:var(--wb-text-muted)]" : "hidden"}>
        <Loader2 className="h-4 w-4 animate-spin text-[color:var(--wb-accent)]" />
        載入中…
      </div>
    );
  }

  const settings = remoteData.settings;

  return (
    <div className={visible ? undefined : "hidden"}>
      <div className="space-y-8 px-6 pb-0 pt-6">
        {/* Page intro */}
        <div className="workbench-panel-strong rounded-[1.4rem] px-5 py-5">
          <div className="flex items-center gap-3">
            <div className="rounded-2xl border border-white/6 bg-black/12 p-3 shadow-inner shadow-white/5">
              <Bot className="h-6 w-6 text-[color:var(--wb-accent)]" />
            </div>
            <div>
              <div className="workbench-kicker text-[11px] font-semibold">助理執行階段</div>
              <h2 className="mt-1 text-lg font-semibold text-[color:var(--wb-text-primary)]">ArcReel AI Agent</h2>
              <p className="text-sm text-[color:var(--wb-text-muted)]">
                透過可切換的執行階段供應商，驅動對話式 AI 助手與自動化工作流程
              </p>
            </div>
          </div>
          <div className="mt-4 flex items-start gap-2 rounded-2xl border border-white/6 bg-black/12 px-4 py-3">
            <Terminal className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[color:var(--wb-accent-cyan)]" />
            <p className="text-xs leading-6 text-[color:var(--wb-text-muted)]">
              依目前選擇的供應商套用對應憑證設定；切換供應商後，新建會話會走新供應商。
            </p>
          </div>
        </div>

        <ProviderSelector
          available={remoteData.options.assistant_providers}
          value={draft.assistantProvider}
          onChange={(providerId) => updateDraft("assistantProvider", providerId)}
          saving={saving}
        />

        {/* Claude-only credentials & model routing — 僅當實際選擇 Claude 供應商時才顯示。 */}
        {draft.assistantProvider === "claude" && (
          <ClaudeProviderSection
            draft={draft}
            settings={settings}
            updateDraft={updateDraft}
            handleClearField={handleClearField}
            saving={saving}
            isBusy={isBusy}
            clearingField={clearingField}
            showKey={showKey}
            setShowKey={setShowKey}
            modelRoutingExpanded={modelRoutingExpanded}
            setModelRoutingExpanded={setModelRoutingExpanded}
          />
        )}

        <AdvancedSettingsSection
          draft={draft}
          updateDraft={updateDraft}
          saving={saving}
        />
      </div>

      <TabSaveFooter
        isDirty={isDirty}
        saving={saving}
        disabled={clearingField !== null}
        error={saveError}
        onSave={() => void handleSave()}
        onReset={handleReset}
      />
    </div>
  );
}
