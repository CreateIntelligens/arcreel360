import { useEffect, useMemo, useRef, useState } from "react";
import { Sliders, Sparkles, AlertTriangle } from "lucide-react";
import { API } from "@/api";
import { providersApi } from "@/api/providers";
import { Popover } from "@/components/ui/Popover";
import { ProviderModelSelect } from "@/components/ui/ProviderModelSelect";
import { useProjectsStore } from "@/stores/projects-store";
import { useAppStore } from "@/stores/app-store";
import { buildMediaModelOptions } from "@/utils/provider-models";
import { useGlobalModelDefaults } from "@/hooks/useGlobalModelDefaults";
import type { EpisodeOverrides, ProviderInfo } from "@/types";

interface EpisodeOverridesPopoverProps {
  projectName: string;
  episode: number;
  overrides?: EpisodeOverrides;
  mediaStage?: "storyboard" | "video";
}

type EpisodeOverrideDraft = {
  image_backend: string;
  video_backend: string;
  video_resolution: string;
  image_size: string;
  duration_seconds: string;
};

const EMPTY_OVERRIDES: EpisodeOverrides = {};
const SELECT_CLASS =
  "w-full rounded border border-gray-700 bg-gray-800 px-2 py-1.5 text-gray-300 outline-none focus:border-indigo-500";

function draftFromOverrides(overrides: EpisodeOverrides): EpisodeOverrideDraft {
  const duration = overrides.duration_seconds;
  return {
    image_backend: overrides.image_backend ?? "",
    video_backend: overrides.video_backend ?? "",
    video_resolution: overrides.video_resolution ?? "",
    image_size: overrides.image_size ?? "",
    duration_seconds: duration === undefined || duration === null ? "" : String(duration),
  };
}

function patchFromDraft(
  draft: EpisodeOverrideDraft,
  mediaStage?: EpisodeOverridesPopoverProps["mediaStage"],
): EpisodeOverrides {
  const patch: EpisodeOverrides = {};
  if (mediaStage !== "video") {
    patch.image_backend = draft.image_backend || null;
    patch.image_size = draft.image_size || null;
  }
  if (mediaStage !== "storyboard") {
    patch.video_backend = draft.video_backend || null;
    patch.video_resolution = draft.video_resolution || null;
    patch.duration_seconds = draft.duration_seconds ? parseInt(draft.duration_seconds, 10) : null;
  }
  return patch;
}

const RESOLUTION_OPTIONS = [
  { value: "", label: "專案預設模型" },
  { value: "720p", label: "720p" },
  { value: "1080p", label: "1080p" },
  { value: "2k", label: "2K" },
  { value: "4k", label: "4K" },
];

const IMAGE_SIZE_OPTIONS = [
  { value: "", label: "專案預設模型" },
  { value: "1k", label: "1K" },
  { value: "2k", label: "2K" },
  { value: "4k", label: "4K" },
];

const DURATION_OPTIONS = [
  { value: "", label: "專案預設模型" },
  { value: "4", label: "4 秒" },
  { value: "5", label: "5 秒" },
  { value: "6", label: "6 秒" },
  { value: "8", label: "8 秒" },
  { value: "10", label: "10 秒" },
  { value: "12", label: "12 秒" },
  { value: "15", label: "15 秒" },
];

export function EpisodeOverridesPopover({
  projectName,
  episode,
  overrides,
  mediaStage,
}: EpisodeOverridesPopoverProps) {
  const anchorRef = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const [providers, setProviders] = useState<ProviderInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [draft, setDraft] = useState<EpisodeOverrideDraft>(() => draftFromOverrides(EMPTY_OVERRIDES));

  const currentOverrides = overrides ?? EMPTY_OVERRIDES;
  const showImageSettings = mediaStage !== "video";
  const showVideoSettings = mediaStage !== "storyboard";

  // Sync draft states when popover opens or overrides change
  useEffect(() => {
    setDraft(draftFromOverrides(currentOverrides));
  }, [currentOverrides, open]);

  // Load providers list once popover is opened
  useEffect(() => {
    if (!open || providers !== null) return;
    let cancelled = false;
    providersApi
      .getProviders()
      .then((res) => {
        if (!cancelled) setProviders(res.providers);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [open, providers]);

  const modelOptions = useMemo(() => buildMediaModelOptions(providers), [providers]);
  const globalDefaults = useGlobalModelDefaults();

  // Determine if overrides are currently active
  const hasActiveOverrides = Object.keys(currentOverrides).length > 0;

  const updateDraft = (field: keyof EpisodeOverrideDraft, value: string) => {
    setDraft((current) => ({ ...current, [field]: value }));
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      await API.updateEpisodeOverrides(projectName, episode, patchFromDraft(draft, mediaStage));

      // Refresh project to update store and UI
      const res = await API.getProject(projectName);
      useProjectsStore.getState().setCurrentProject(
        projectName,
        res.project,
        res.scripts ?? {},
        res.asset_fingerprints,
      );

      useAppStore.getState().pushToast(`E${episode} 覆蓋設定已更新`, "success");
      setOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <button
        ref={anchorRef}
        type="button"
        onClick={() => setOpen(true)}
        aria-label={`編輯第 ${episode} 集模型覆蓋設定`}
        className={`inline-flex items-center justify-center rounded-full border p-1.5 text-xs font-medium transition-all shadow-sm focus-ring ${hasActiveOverrides
            ? "border-amber-500/30 bg-amber-500/10 text-amber-300 hover:bg-amber-500/20"
            : "border-gray-700 bg-gray-800 text-gray-400 hover:border-gray-600 hover:text-gray-200"
          }`}
        title={`編輯第 ${episode} 集模型覆蓋設定`}
      >
        <Sliders className="h-3 w-3" />
      </button>

      <Popover
        open={open}
        onClose={() => setOpen(false)}
        anchorRef={anchorRef}
        className="w-80 rounded-xl border border-gray-800 bg-gray-900/95 p-4 shadow-2xl backdrop-blur-md"
      >
        <div className="space-y-4">
          <div className="flex items-center gap-2 border-b border-gray-800 pb-2">
            <Sparkles className="h-4 w-4 text-indigo-400" />
            <h4 className="text-sm font-semibold text-gray-200">
              第 {episode} 集 模型與生成設定覆蓋
            </h4>
          </div>

          {error && (
            <div className="flex items-start gap-2 rounded-lg bg-red-950/40 border border-red-500/20 p-2.5 text-xs text-red-300">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <div className="space-y-3.5 text-xs">
            {showImageSettings && (
              <div className="space-y-1.5">
                <label className="block text-[11px] font-medium text-gray-400">🖼 圖片生成後端</label>
                <ProviderModelSelect
                  value={draft.image_backend}
                  onChange={(value) => updateDraft("image_backend", value)}
                  options={modelOptions.image}
                  providerNames={modelOptions.providerNames}
                  placeholder="專案預設模型"
                  allowDefault={true}
                  defaultLabel="專案預設模型"
                  defaultModelValue={globalDefaults.image}
                />
              </div>
            )}

            {showVideoSettings && (
              <div className="space-y-1.5">
                <label className="block text-[11px] font-medium text-gray-400">🎬 影片生成後端</label>
                <ProviderModelSelect
                  value={draft.video_backend}
                  onChange={(value) => updateDraft("video_backend", value)}
                  options={modelOptions.video}
                  providerNames={modelOptions.providerNames}
                  placeholder="專案預設模型"
                  allowDefault={true}
                  defaultLabel="專案預設模型"
                  defaultModelValue={globalDefaults.video}
                />
              </div>
            )}

            <div className={showImageSettings && showVideoSettings ? "grid grid-cols-2 gap-3" : "space-y-3"}>
              {showVideoSettings && (
                <SelectField
                  id="video-resolution-select"
                  label="📐 影片解析度"
                  value={draft.video_resolution}
                  options={RESOLUTION_OPTIONS}
                  onChange={(value) => updateDraft("video_resolution", value)}
                />
              )}
              {showImageSettings && (
                <SelectField
                  id="image-size-select"
                  label="🖼 圖片尺寸"
                  value={draft.image_size}
                  options={IMAGE_SIZE_OPTIONS}
                  onChange={(value) => updateDraft("image_size", value)}
                />
              )}
            </div>

            {showVideoSettings && (
              <SelectField
                id="video-duration-select"
                label="⏱ 影片時長"
                value={draft.duration_seconds}
                options={DURATION_OPTIONS}
                onChange={(value) => updateDraft("duration_seconds", value)}
              />
            )}
          </div>

          <div className="text-[10px] text-gray-500 leading-normal">
            💡 本集設定會覆蓋專案層級預設值，但仍可被個別分鏡中已設定的覆蓋值所覆蓋。
          </div>

          <div className="flex justify-end gap-2 border-t border-gray-800 pt-3">
            <button
              type="button"
              onClick={() => setOpen(false)}
              disabled={saving}
              className="rounded-lg px-3 py-1.5 text-xs font-medium text-gray-400 hover:bg-gray-800 hover:text-gray-200 disabled:opacity-50"
            >
              取消
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={saving}
              className="inline-flex items-center justify-center rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 disabled:opacity-50"
            >
              {saving ? "儲存中..." : "確認儲存"}
            </button>
          </div>
        </div>
      </Popover>
    </>
  );
}

function SelectField({
  id,
  label,
  value,
  options,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  options: readonly { value: string; label: string }[];
  onChange: (value: string) => void;
}) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="block text-[11px] font-medium text-gray-400">
        {label}
      </label>
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={SELECT_CLASS}
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </div>
  );
}
