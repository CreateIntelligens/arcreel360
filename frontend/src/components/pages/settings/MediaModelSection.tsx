import { useState, useEffect, useCallback, useMemo } from "react";
import { useWarnUnsaved } from "@/hooks/useWarnUnsaved";
import { API } from "@/api";
import type { SystemConfigSettings, SystemConfigOptions, SystemConfigPatch } from "@/types/system";
import { ProviderModelSelect } from "@/components/ui/ProviderModelSelect";
import { PROVIDER_NAMES } from "@/components/ui/ProviderIcon";
import { useAppStore } from "@/stores/app-store";
import { useConfigStatusStore } from "@/stores/config-status-store";
import { shouldHideTextModelOption } from "@/utils/provider-models";

const TEXT_MODEL_FIELDS = [
  ["default_text_backend", "助手對話"],
  ["text_backend_script", "劇本生成"],
  ["text_backend_overview", "總覽生成"],
  ["text_backend_style", "風格分析"],
] as const;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function MediaModelSection() {
  const [settings, setSettings] = useState<SystemConfigSettings | null>(null);
  const [options, setOptions] = useState<SystemConfigOptions | null>(null);
  const [draft, setDraft] = useState<SystemConfigPatch>({});
  const [saving, setSaving] = useState(false);

  const isDirty = Object.keys(draft).length > 0;
  useWarnUnsaved(isDirty);

  const allProviderNames = useMemo(
    () => ({ ...PROVIDER_NAMES, ...(options?.provider_names ?? {}) }),
    [options],
  );

  const fetchConfig = useCallback(async () => {
    const res = await API.getSystemConfig();
    setSettings(res.settings);
    setOptions(res.options);
    setDraft({});
  }, []);

  useEffect(() => {
    void fetchConfig();
  }, [fetchConfig]);

  const handleSave = useCallback(async () => {
    if (Object.keys(draft).length === 0) return;
    setSaving(true);
    try {
      await API.updateSystemConfig(draft);
      await fetchConfig();
      void useConfigStatusStore.getState().refresh();
      useAppStore.getState().pushToast("媒體模型設定已儲存", "success");
    } catch (err) {
      useAppStore.getState().pushToast(`儲存失敗：${(err as Error).message}`, "error");
    } finally {
      setSaving(false);
    }
  }, [draft, fetchConfig]);

  const currentBytePlusEndpoint = draft.byteplus_video_endpoint_id ?? settings?.byteplus_video_endpoint_id ?? "";
  const videoBackends = options?.video_backends ?? [];
  const imageBackends: string[] = options?.image_backends ?? [];
  const textBackends: string[] = (options?.text_backends ?? []).filter((value) => !shouldHideTextModelOption(value));

  if (!settings || !options) {
    return <div className="p-6 text-sm text-gray-500">載入中…</div>;
  }

  const currentVideo = draft.default_video_backend ?? settings.default_video_backend ?? "";
  const currentImage = draft.default_image_backend ?? settings.default_image_backend ?? "";
  const currentAudio = draft.video_generate_audio ?? settings.video_generate_audio ?? false;

  return (
    <div className="space-y-6 p-6">
      {/* Section heading */}
      <div>
        <h3 className="text-lg font-semibold text-gray-100">模型選擇</h3>
        <p className="mt-1 text-sm text-gray-500">設定全域預設生成模型，專案內可單獨覆寫</p>
      </div>

      {/* Video backend selector */}
      <div className="rounded-xl border border-gray-800 bg-gray-950/40 p-4">
        <div className="mb-3 text-sm font-medium text-gray-100">預設影片模型</div>
        {videoBackends.length > 0 ? (
          <ProviderModelSelect
            value={currentVideo}
            options={videoBackends}
            providerNames={allProviderNames}
            onChange={(v) => setDraft((prev) => ({ ...prev, default_video_backend: v }))}
            allowDefault
            defaultLabel="自動選擇"
            defaultHint="自動"
          />
        ) : (
          <div className="rounded-lg border border-gray-800 bg-gray-900/60 px-3 py-2 text-sm text-gray-500">
            暫無可用影片供應商，請先在「供應商」頁面設定 API 金鑰
          </div>
        )}

        {/* Audio toggle */}
        <label className="mt-3 flex cursor-pointer items-center gap-2 text-sm text-gray-300">
          <input
            type="checkbox"
            checked={currentAudio}
            onChange={(e) =>
              setDraft((prev) => ({ ...prev, video_generate_audio: e.target.checked }))
            }
            className="rounded border-gray-600 bg-gray-800"
          />
          生成音訊
          <span className="text-xs text-gray-500">（僅部分供應商支援）</span>
        </label>

        <label className="mt-4 block text-sm font-medium text-gray-100">
          BytePlus ModelArk Endpoint ID
          <input
            type="text"
            value={currentBytePlusEndpoint}
            onChange={(e) =>
              setDraft((prev) => ({
                ...prev,
                byteplus_video_endpoint_id: e.target.value,
              }))
            }
            placeholder="ep-..."
            autoCapitalize="none"
            autoCorrect="off"
            spellCheck={false}
            className="mt-2 w-full rounded-lg border border-gray-700 bg-gray-900/80 px-3 py-2 font-mono text-sm text-gray-200 transition-colors placeholder:text-gray-600 hover:border-gray-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-1 focus-visible:ring-offset-gray-900"
          />
        </label>
      </div>

      {/* Image backend selector */}
      <div className="rounded-xl border border-gray-800 bg-gray-950/40 p-4">
        <div className="mb-3 text-sm font-medium text-gray-100">預設圖片模型</div>
        {imageBackends.length > 0 ? (
          <ProviderModelSelect
            value={currentImage}
            options={imageBackends}
            providerNames={allProviderNames}
            onChange={(v) => setDraft((prev) => ({ ...prev, default_image_backend: v }))}
            allowDefault
            defaultLabel="自動選擇"
            defaultHint="自動"
          />
        ) : (
          <div className="rounded-lg border border-gray-800 bg-gray-900/60 px-3 py-2 text-sm text-gray-500">
            暫無可用圖片供應商，請先在「供應商」頁面設定 API 金鑰
          </div>
        )}
      </div>

      {/* Text backend selectors */}
      <div className="rounded-xl border border-gray-800 bg-gray-950/40 p-4">
        <div className="mb-3 text-sm font-medium text-gray-100">文字模型</div>
        <p className="mb-3 text-xs text-gray-500">依任務型別設定文字模型，留空表示自動選擇</p>

        {textBackends.length > 0 ? (
          <div className="space-y-3">
            {TEXT_MODEL_FIELDS.map(([key, label]) => (
              <div key={key}>
                <div className="mb-1 text-xs text-gray-400">{label}</div>
                <ProviderModelSelect
                  value={(draft[key] ?? settings[key] ?? "") as string}
                  options={textBackends}
                  providerNames={allProviderNames}
                  onChange={(v) => setDraft((prev) => ({ ...prev, [key]: v }))}
                  allowDefault
                  defaultHint="自動"
                  aria-label={label}
                />
              </div>
            ))}
          </div>
        ) : (
          <div className="rounded-lg border border-gray-800 bg-gray-900/60 px-3 py-2 text-sm text-gray-500">
            暫無可用文字供應商，請先在「供應商」頁面設定 API 金鑰
          </div>
        )}
      </div>

      {/* Save / reset buttons */}
      {isDirty && (
        <div className="flex gap-3">
          <button
            type="button"
            onClick={() => void handleSave()}
            disabled={saving}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm text-white transition-colors hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:ring-2 focus-visible:ring-indigo-500/60 focus-visible:outline-none"
          >
            {saving ? "儲存中…" : "儲存"}
          </button>
          <button
            type="button"
            onClick={() => setDraft({})}
            className="rounded-lg border border-gray-700 px-4 py-2 text-sm text-gray-300 transition-colors hover:bg-gray-800 focus-visible:ring-2 focus-visible:ring-indigo-500/60 focus-visible:outline-none"
          >
            重設
          </button>
        </div>
      )}
    </div>
  );
}
