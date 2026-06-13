import { useParams, useLocation } from "wouter";
import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { ArrowLeft } from "lucide-react";
import { API } from "@/api";
import { useAppStore } from "@/stores/app-store";
import { ProviderModelSelect } from "@/components/ui/ProviderModelSelect";
import { PROVIDER_NAMES } from "@/components/ui/ProviderIcon";
import { useConfirm } from "@/hooks/useConfirm";
import {
  DEFAULT_IMAGE_SIZES,
  DEFAULT_RESOLUTIONS,
  getProviderModels,
  lookupDefaultResolution,
  lookupSupportedImageSizes,
  lookupSupportedResolutions,
  shouldHideTextModelOption,
} from "@/utils/provider-models";
import { UI_LAYERS } from "@/utils/ui-layers";
import type { ProviderInfo } from "@/types";

export function ProjectSettingsPage() {
  const params = useParams<{ projectName: string }>();
  const projectName = params.projectName || "";
  const [, navigate] = useLocation();
  const confirm = useConfirm();

  const [options, setOptions] = useState<{
    video_backends: string[];
    image_backends: string[];
    text_backends: string[];
    provider_names?: Record<string, string>;
  } | null>(null);
  const [globalDefaults, setGlobalDefaults] = useState<{
    video: string;
    image: string;
  }>({ video: "", image: "" });

  const allProviderNames = useMemo(
    () => ({ ...PROVIDER_NAMES, ...(options?.provider_names ?? {}) }),
    [options],
  );

  // Project-level overrides (from project.json)
  // "" means "follow global default"
  const [videoBackend, setVideoBackend] = useState<string>("");
  const [imageBackend, setImageBackend] = useState<string>("");
  const [audioOverride, setAudioOverride] = useState<boolean | null>(null);
  const [textScript, setTextScript] = useState<string>("");
  const [textOverview, setTextOverview] = useState<string>("");
  const [textStyle, setTextStyle] = useState<string>("");
  const [aspectRatio, setAspectRatio] = useState<string>("");
  const [videoModelSettings, setVideoModelSettings] = useState<Record<string, { resolution?: string | null }>>({});
  const [imageModelSettings, setImageModelSettings] = useState<Record<string, { image_size?: string | null }>>({});
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [saving, setSaving] = useState(false);
  const initialRef = useRef({
    videoBackend: "", imageBackend: "", audioOverride: null as boolean | null,
    textScript: "", textOverview: "", textStyle: "",
    aspectRatio: "",
    videoModelSettings: {} as Record<string, { resolution?: string | null }>,
    imageModelSettings: {} as Record<string, { image_size?: string | null }>,
  });

  useEffect(() => {
    let disposed = false;

    Promise.all([
      API.getSystemConfig(),
      API.getProject(projectName),
      getProviderModels().catch(() => [] as ProviderInfo[]),
    ]).then(([configRes, projectRes, providerList]) => {
      if (disposed) return;

      setOptions({
        video_backends: configRes.options?.video_backends ?? [],
        image_backends: configRes.options?.image_backends ?? [],
        text_backends: (configRes.options?.text_backends ?? []).filter((value) => !shouldHideTextModelOption(value)),
        provider_names: configRes.options?.provider_names,
      });
      setGlobalDefaults({
        video: configRes.settings?.default_video_backend ?? "",
        image: configRes.settings?.default_image_backend ?? "",
      });
      setProviders(providerList);

      const project = projectRes.project as unknown as Record<string, unknown>;
      const vb = (project.video_backend as string | undefined) ?? "";
      const ib = (project.image_backend as string | undefined) ?? "";
      const rawAudio = project.video_generate_audio;
      const ao = typeof rawAudio === "boolean" ? rawAudio : null;
      const ts = (project.text_backend_script as string | undefined) ?? "";
      const to = (project.text_backend_overview as string | undefined) ?? "";
      const tst = (project.text_backend_style as string | undefined) ?? "";

      const ar = typeof project.aspect_ratio === "string"
        ? project.aspect_ratio
        : "";
      const vms = (project.video_model_settings as Record<string, { resolution?: string | null }> | undefined) ?? {};
      const ims = (project.image_model_settings as Record<string, { image_size?: string | null }> | undefined) ?? {};

      setVideoBackend(vb);
      setImageBackend(ib);
      setAudioOverride(ao);
      setTextScript(ts);
      setTextOverview(to);
      setTextStyle(tst);
      setAspectRatio(ar);
      setVideoModelSettings(vms);
      setImageModelSettings(ims);
      initialRef.current = {
        videoBackend: vb, imageBackend: ib, audioOverride: ao,
        textScript: ts, textOverview: to, textStyle: tst,
        aspectRatio: ar,
        videoModelSettings: vms,
        imageModelSettings: ims,
      };
    });

    return () => { disposed = true; };
  }, [projectName]);

  const effectiveVideoBackend = videoBackend || globalDefaults.video;
  const effectiveVideoModelId = effectiveVideoBackend.includes("/")
    ? effectiveVideoBackend.split("/")[1]
    : "";
  const supportedResolutions = useMemo(
    () => lookupSupportedResolutions(providers, effectiveVideoBackend),
    [providers, effectiveVideoBackend],
  );
  const resolutionOptions = supportedResolutions ?? (DEFAULT_RESOLUTIONS as string[]);
  const modelResolution = effectiveVideoModelId
    ? videoModelSettings[effectiveVideoModelId]?.resolution
    : null;
  const effectiveResolution =
    modelResolution && resolutionOptions.includes(modelResolution)
      ? modelResolution
      : (lookupDefaultResolution(effectiveVideoBackend) ?? resolutionOptions[0] ?? "1080p");

  // ---- Image resolution (size) ----
  const effectiveImageBackend = imageBackend || globalDefaults.image;
  const effectiveImageModelId = effectiveImageBackend.includes("/")
    ? effectiveImageBackend.split("/")[1]
    : "";
  const imageSizeOptions = useMemo(
    () => lookupSupportedImageSizes(providers, effectiveImageBackend) ?? (DEFAULT_IMAGE_SIZES as string[]),
    [providers, effectiveImageBackend],
  );
  const modelImageSize = effectiveImageModelId
    ? imageModelSettings[effectiveImageModelId]?.image_size
    : null;
  const effectiveImageSize =
    modelImageSize && imageSizeOptions.includes(modelImageSize)
      ? modelImageSize
      : (imageSizeOptions[0] ?? DEFAULT_IMAGE_SIZES[0]);

  const handleImageSizeChange = useCallback((size: string) => {
    if (!effectiveImageModelId) return;
    setImageModelSettings((prev) => ({
      ...prev,
      [effectiveImageModelId]: {
        ...(prev[effectiveImageModelId] ?? {}),
        image_size: size,
      },
    }));
  }, [effectiveImageModelId]);
  const handleVideoBackendChange = useCallback((value: string) => {
    setVideoBackend(value);
  }, []);

  const handleResolutionChange = useCallback((resolution: string) => {
    if (!effectiveVideoModelId) return;
    setVideoModelSettings((prev) => ({
      ...prev,
      [effectiveVideoModelId]: {
        ...(prev[effectiveVideoModelId] ?? {}),
        resolution,
      },
    }));

  }, [effectiveVideoModelId]);

  const isDirty =
    videoBackend !== initialRef.current.videoBackend ||
    imageBackend !== initialRef.current.imageBackend ||
    audioOverride !== initialRef.current.audioOverride ||
    textScript !== initialRef.current.textScript ||
    textOverview !== initialRef.current.textOverview ||
    textStyle !== initialRef.current.textStyle ||
    aspectRatio !== initialRef.current.aspectRatio ||
    JSON.stringify(videoModelSettings) !== JSON.stringify(initialRef.current.videoModelSettings) ||
    JSON.stringify(imageModelSettings) !== JSON.stringify(initialRef.current.imageModelSettings);

  useEffect(() => {
    if (!isDirty) return;
    const handler = (e: BeforeUnloadEvent) => { e.preventDefault(); };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [isDirty]);

  const guardedNavigate = useCallback(async (path: string) => {
    if (isDirty) {
      const ok = await confirm({
        message: "有未儲存的修改，確定要離開嗎？",
        danger: true,
      });
      if (!ok) return;
    }
    navigate(path);
  }, [isDirty, navigate, confirm]);

  const handleSave = useCallback(async () => {
    setSaving(true);
    try {
      await API.updateProject(projectName, {
        video_backend: videoBackend || null,
        image_backend: imageBackend || null,
        video_generate_audio: audioOverride,
        text_backend_script: textScript || null,
        text_backend_overview: textOverview || null,
        text_backend_style: textStyle || null,
        aspect_ratio: aspectRatio || undefined,
        default_duration: null,
        video_model_settings: videoModelSettings,
        image_model_settings: imageModelSettings,
      } as Record<string, unknown>);
      initialRef.current = {
        videoBackend, imageBackend, audioOverride,
        textScript, textOverview, textStyle,
        aspectRatio,
        videoModelSettings,
        imageModelSettings,
      };
      useAppStore.getState().pushToast("已儲存", "success");
    } catch (e: unknown) {
      useAppStore.getState().pushToast(e instanceof Error ? e.message : "儲存失敗", "error");
    } finally {
      setSaving(false);
    }
  }, [
    videoBackend,
    imageBackend,
    audioOverride,
    textScript,
    textOverview,
    textStyle,
    aspectRatio,
    videoModelSettings,
    imageModelSettings,
    projectName,
  ]);

  return (
    <div className={`fixed inset-0 ${UI_LAYERS.modal} bg-gray-950 overflow-y-auto`}>
      {/* Header */}
      <div className="sticky top-0 z-10 flex items-center gap-3 border-b border-gray-800 bg-gray-950/95 px-6 py-4 backdrop-blur">
        <button
          onClick={() => guardedNavigate(`/app/projects/${projectName}`)}
          className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-800 hover:text-gray-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
          aria-label="返回專案"
        >
          <ArrowLeft className="h-5 w-5" />
        </button>
        <h1 className="text-lg font-semibold text-gray-100">專案設定</h1>
      </div>

      {/* Content */}
      <div className="mx-auto max-w-2xl px-6 py-8 space-y-6">
        <div>
          <h2 className="text-lg font-semibold text-gray-100">模型設定</h2>
          <p className="mt-1 text-sm text-gray-500">
            為此專案單獨選擇生成模型，留空則跟隨全域預設
          </p>
        </div>

        {options && (
          <>
            {/* Video model override */}
            <div className="rounded-xl border border-gray-800 bg-gray-950/40 p-4">
              <div className="mb-3 text-sm font-medium text-gray-100">影片模型</div>
              <ProviderModelSelect
                value={videoBackend}
                options={options.video_backends}
                providerNames={allProviderNames}
                onChange={handleVideoBackendChange}
                allowDefault
                popoverLayer="modalPopover"
                defaultHint={
                  globalDefaults.video ? `目前全域：${globalDefaults.video}` : undefined
                }
              />
            </div>

            {effectiveVideoBackend && (
              <div className="rounded-xl border border-gray-800 bg-gray-950/40 p-4">
                <fieldset>
                  <legend className="mb-3 text-sm font-medium text-gray-100">影片解析度</legend>
                  <div className="flex flex-wrap gap-2">
                    {resolutionOptions.map((resolution) => (
                      <label
                        key={resolution}
                        className={`cursor-pointer rounded-lg border px-3 py-2 text-sm transition-colors has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-indigo-500 ${effectiveResolution === resolution
                            ? "border-indigo-500 bg-indigo-500/10 text-indigo-300"
                            : "border-gray-700 bg-gray-800 text-gray-400 hover:border-gray-600"
                          }`}
                      >
                        <input
                          type="radio"
                          name="videoResolution"
                          value={resolution}
                          checked={effectiveResolution === resolution}
                          onChange={() => handleResolutionChange(resolution)}
                          className="sr-only"
                        />
                        {resolution}
                      </label>
                    ))}
                  </div>
                </fieldset>
              </div>
            )}

            {/* Aspect ratio */}
            <div className="rounded-xl border border-gray-800 bg-gray-950/40 p-4">
              <fieldset>
                <legend className="mb-3 text-sm font-medium text-gray-100">畫面比例</legend>
                <div className="flex gap-3">
                  {(["9:16", "16:9"] as const).map((ar) => (
                    <label
                      key={ar}
                      className={`flex-1 cursor-pointer rounded-lg border px-3 py-2 text-center text-sm transition-colors has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-indigo-500 ${aspectRatio === ar
                          ? "border-indigo-500 bg-indigo-500/10 text-indigo-300"
                          : "border-gray-700 bg-gray-800 text-gray-400 hover:border-gray-600"
                        }`}
                    >
                      <input
                        type="radio"
                        name="aspectRatio"
                        value={ar}
                        checked={aspectRatio === ar}
                        onChange={() => {
                          setAspectRatio(ar);
                          if (initialRef.current.aspectRatio && ar !== initialRef.current.aspectRatio) {
                            useAppStore.getState().pushToast(
                              "已生成的分鏡圖／影片仍為原比例，建議生成",
                              "warning",
                            );
                          }
                        }}
                        className="sr-only"
                      />
                      {ar === "9:16" ? "豎屏 9:16" : "橫屏 16:9"}
                    </label>
                  ))}
                </div>
              </fieldset>
            </div>



            {/* Image model override */}
            <div className="rounded-xl border border-gray-800 bg-gray-950/40 p-4">
              <div className="mb-3 text-sm font-medium text-gray-100">圖片模型</div>
              <ProviderModelSelect
                value={imageBackend}
                options={options.image_backends}
                providerNames={allProviderNames}
                onChange={setImageBackend}
                allowDefault
                popoverLayer="modalPopover"
                defaultHint={
                  globalDefaults.image ? `目前全域：${globalDefaults.image}` : undefined
                }
              />
            </div>

            {effectiveImageBackend && imageSizeOptions.length > 1 && (
              <div className="rounded-xl border border-gray-800 bg-gray-950/40 p-4">
                <fieldset>
                  <legend className="mb-3 text-sm font-medium text-gray-100">圖片解析度</legend>
                  <div className="flex flex-wrap gap-2">
                    {imageSizeOptions.map((size) => (
                      <label
                        key={size}
                        className={`cursor-pointer rounded-lg border px-3 py-2 text-sm transition-colors has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-indigo-500 ${effectiveImageSize === size
                            ? "border-indigo-500 bg-indigo-500/10 text-indigo-300"
                            : "border-gray-700 bg-gray-800 text-gray-400 hover:border-gray-600"
                          }`}
                      >
                        <input
                          type="radio"
                          name="imageSize"
                          value={size}
                          checked={effectiveImageSize === size}
                          onChange={() => handleImageSizeChange(size)}
                          className="sr-only"
                        />
                        {size}
                      </label>
                    ))}
                  </div>
                </fieldset>
              </div>
            )}

            {/* Audio override */}
            <div className="rounded-xl border border-gray-800 bg-gray-950/40 p-4">
              <div className="mb-3 text-sm font-medium text-gray-100">生成音訊</div>
              <fieldset className="flex gap-4">
                <legend className="sr-only">生成音訊設定</legend>
                <label className="flex items-center gap-2 text-sm text-gray-300">
                  <input type="radio" name="audio" value="" checked={audioOverride === null}
                    onChange={() => setAudioOverride(null)} />
                  跟隨全域預設
                </label>
                <label className="flex items-center gap-2 text-sm text-gray-300">
                  <input type="radio" name="audio" value="true" checked={audioOverride === true}
                    onChange={() => setAudioOverride(true)} />
                  開啟
                </label>
                <label className="flex items-center gap-2 text-sm text-gray-300">
                  <input type="radio" name="audio" value="false" checked={audioOverride === false}
                    onChange={() => setAudioOverride(false)} />
                  關閉
                </label>
              </fieldset>
            </div>
            {/* Text model overrides */}
            <div className="rounded-xl border border-gray-800 bg-gray-950/40 p-4">
              <div className="mb-3 text-sm font-medium text-gray-100">文字模型</div>
              <p className="mb-2 text-xs text-gray-500">依任務型別覆寫，留空則跟隨全域預設</p>
              <div className="space-y-3">
                {([
                  [textScript, setTextScript, "劇本生成"] as const,
                  [textOverview, setTextOverview, "總覽生成"] as const,
                  [textStyle, setTextStyle, "風格分析"] as const,
                ]).map(([value, setter, label]) => (
                  <div key={label}>
                    <div className="mb-1 text-xs text-gray-400">{label}</div>
                    <ProviderModelSelect
                      value={value}
                      options={options.text_backends}
                      providerNames={allProviderNames}
                      onChange={setter}
                      allowDefault
                      popoverLayer="modalPopover"
                      defaultHint="跟隨全域預設"
                      aria-label={label}
                    />
                  </div>
                ))}
              </div>
            </div>
          </>
        )}

        {!options && (
          <div className="text-sm text-gray-500">載入設定中…</div>
        )}

        {/* Actions */}
        <div className="flex gap-3">
          <button
            onClick={handleSave}
            disabled={saving}
            className="rounded-lg bg-indigo-600 px-6 py-2 text-sm text-white hover:bg-indigo-500 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 focus-visible:ring-offset-gray-950"
          >
            {saving ? "儲存中…" : "儲存"}
          </button>
          <button
            onClick={() => guardedNavigate(`/app/projects/${projectName}`)}
            className="rounded-lg border border-gray-700 px-6 py-2 text-sm text-gray-300 hover:bg-gray-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 focus-visible:ring-offset-gray-950"
          >
            取消
          </button>
        </div>
      </div>
    </div>
  );
}
