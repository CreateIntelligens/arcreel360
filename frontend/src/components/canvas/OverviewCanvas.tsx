import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, ImagePlus, Trash2, Upload } from "lucide-react";
import type { ProjectData, ProviderInfo } from "@/types";
import { API } from "@/api";
import { providersApi } from "@/api/providers";
import { useProjectsStore } from "@/stores/projects-store";
import { useAppStore } from "@/stores/app-store";
import { useCostStore } from "@/stores/cost-store";
import { PreviewableImageFrame } from "@/components/ui/PreviewableImageFrame";
import { useConfirm } from "@/hooks/useConfirm";
import { formatCost, totalBreakdown } from "@/utils/cost-format";
import { buildMediaModelOptions } from "@/utils/provider-models";
import { sortEpisodesForDisplay } from "@/utils/episodes";
import { STYLE_OPTIONS } from "@/utils/project-style";

import { OverviewSection } from "./OverviewSection";
import { WelcomeCanvas } from "./WelcomeCanvas";

interface OverviewCanvasProps {
  projectName: string;
  projectData: ProjectData | null;
}

export function OverviewCanvas({ projectName, projectData }: OverviewCanvasProps) {
  const confirm = useConfirm();
  const styleImageFp = useProjectsStore(
    (s) => projectData?.style_image ? s.getAssetFingerprint(projectData.style_image) : null,
  );
  const projectTotals = useCostStore((s) => s.costData?.project_totals);
  const getEpisodeCost = useCostStore((s) => s.getEpisodeCost);
  const costLoading = useCostStore((s) => s.loading);
  const costError = useCostStore((s) => s.error);
  const debouncedFetch = useCostStore((s) => s.debouncedFetch);

  useEffect(() => {
    if (!projectName) return;
    debouncedFetch(projectName);
  }, [projectName, projectData?.episodes, debouncedFetch]);

  const [uploadingStyleImage, setUploadingStyleImage] = useState(false);
  const [deletingStyleImage, setDeletingStyleImage] = useState(false);
  const [savingStyleDescription, setSavingStyleDescription] = useState(false);
  const [providers, setProviders] = useState<ProviderInfo[] | null>(null);
  const [styleDescriptionDraft, setStyleDescriptionDraft] = useState(
    projectData?.style_description ?? "",
  );
  const styleInputRef = useRef<HTMLInputElement>(null);

  const refreshProject = useCallback(
    async () => {
      const res = await API.getProject(projectName);
      useProjectsStore.getState().setCurrentProject(
        projectName,
        res.project,
        res.scripts ?? {},
        res.asset_fingerprints,
      );
    },
    [projectName],
  );

  useEffect(() => {
    setStyleDescriptionDraft(projectData?.style_description ?? "");
  }, [projectData?.style_description]);

  useEffect(() => {
    let disposed = false;
    providersApi
      .getProviders()
      .then((res) => {
        if (!disposed) setProviders(res.providers);
      })
      .catch(() => {
        if (!disposed) setProviders([]);
      });
    return () => {
      disposed = true;
    };
  }, []);

  const modelOptions = useMemo(() => buildMediaModelOptions(providers), [providers]);

  const handleUpload = useCallback(
    async (file: File) => {
      try {
        await API.uploadFile(projectName, "source", file);
        useAppStore.getState().pushToast(`來源檔案「${file.name}」上傳成功`, "success");
      } catch (err) {
        useAppStore.getState().pushToast(`上傳失敗: ${(err as Error).message}`, "error");
      }
    },
    [projectName],
  );

  const handleAnalyze = useCallback(async () => {
    await API.generateOverview(projectName);
    await refreshProject();
  }, [projectName, refreshProject]);

  const handleStyleImageChange = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      e.target.value = "";
      if (!file) return;

      setUploadingStyleImage(true);
      try {
        await API.uploadStyleImage(projectName, file);
        await refreshProject();
        useAppStore.getState().pushToast("風格參考圖已更新", "success");
      } catch (err) {
        useAppStore
          .getState()
          .pushToast(`上傳失敗: ${(err as Error).message}`, "error");
      } finally {
        setUploadingStyleImage(false);
      }
    },
    [projectName, refreshProject],
  );

  const handleDeleteStyleImage = useCallback(async () => {
    if (deletingStyleImage || !projectData?.style_image) return;
    const ok = await confirm({
      message: "確定要刪除目前的風格參考圖嗎？",
      danger: true,
    });
    if (!ok) return;

    setDeletingStyleImage(true);
    try {
      await API.deleteStyleImage(projectName);
      await refreshProject();
      useAppStore.getState().pushToast("風格參考圖已刪除", "success");
    } catch (err) {
      useAppStore
        .getState()
        .pushToast(`刪除失敗: ${(err as Error).message}`, "error");
    } finally {
      setDeletingStyleImage(false);
    }
  }, [deletingStyleImage, projectData?.style_image, projectName, refreshProject, confirm]);

  const handleSaveStyleDescription = useCallback(async () => {
    if (savingStyleDescription) return;
    setSavingStyleDescription(true);
    try {
      await API.updateStyleDescription(projectName, styleDescriptionDraft.trim());
      await refreshProject();
      useAppStore.getState().pushToast("風格描述已儲存", "success");
    } catch (err) {
      useAppStore
        .getState()
        .pushToast(`儲存失敗: ${(err as Error).message}`, "error");
    } finally {
      setSavingStyleDescription(false);
    }
  }, [projectName, refreshProject, savingStyleDescription, styleDescriptionDraft]);

  if (!projectData) {
    return (
      <div className="flex h-full items-center justify-center text-gray-500">
        載入專案資料中...
      </div>
    );
  }

  const status = projectData.status;
  const overview = projectData.overview;
  const styleImageUrl = projectData.style_image
    ? API.getFileUrl(projectName, projectData.style_image, styleImageFp)
    : null;
  const styleDescriptionDirty =
    styleDescriptionDraft !== (projectData.style_description ?? "");
  const showWelcome = !overview && (projectData.episodes?.length ?? 0) === 0;
  const focusRing = "focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-1 focus-visible:ring-offset-gray-900";
  const projectStyleCard = (
    <section className="rounded-2xl border border-gray-800 bg-gray-900/90 p-4 sm:p-5">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h3 className="text-sm font-semibold text-gray-200">專案風格</h3>
          <p className="max-w-2xl text-xs leading-5 text-gray-500">
            參考圖會參與後續畫面生成；風格描述用於補充視覺規則，校準整體調性、材質與鏡頭氣質。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label htmlFor="project-style-select" className="text-xs text-gray-500">風格標籤：</label>
          <div className="relative">
            <select
              id="project-style-select"
              value={projectData.style || ""}
              onChange={async (e) => {
                const value = e.target.value;
                try {
                  await API.updateStyle(projectName, value);
                  await refreshProject();
                  useAppStore.getState().pushToast("專案風格已更新", "success");
                } catch (err) {
                  useAppStore.getState().pushToast(`更新失敗: ${(err as Error).message}`, "error");
                }
              }}
              className="appearance-none rounded-lg border border-gray-700 bg-gray-800 py-1.5 pl-3 pr-8 text-xs text-gray-300 outline-none transition-colors hover:border-gray-600 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
            >
              {STYLE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
            <ChevronDown className="pointer-events-none absolute right-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-500" />
          </div>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-[280px_minmax(0,1fr)]">
        <div className="space-y-3">
          {styleImageUrl ? (
            <PreviewableImageFrame src={styleImageUrl} alt="專案風格參考圖">
              <div className="overflow-hidden rounded-xl border border-gray-700 bg-gray-950/70">
                <img
                  src={styleImageUrl}
                  alt="專案風格參考圖"
                  className="aspect-[4/3] w-full object-cover"
                />
              </div>
            </PreviewableImageFrame>
          ) : (
            <button
              type="button"
              onClick={() => styleInputRef.current?.click()}
              disabled={uploadingStyleImage}
              className={`flex aspect-[4/3] w-full flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-gray-700 bg-gray-950/40 px-4 text-sm text-gray-500 transition-colors hover:border-gray-500 hover:text-gray-300 disabled:cursor-not-allowed disabled:opacity-50 ${focusRing}`}
            >
              <Upload className="h-4 w-4" />
              <span>{uploadingStyleImage ? "上傳中..." : "上傳風格參考圖"}</span>
              <span className="text-xs text-gray-600">支援 PNG / JPG / WEBP</span>
            </button>
          )}

          <div className="rounded-xl border border-gray-800 bg-gray-950/40 p-3">
            <p className="text-xs font-medium text-gray-400">使用說明</p>
            <p className="mt-1 text-sm leading-6 text-gray-300">
              {styleImageUrl
                ? "目前參考圖會作為統一視覺基線，用於角色圖、分鏡圖與影片生成。"
                : "目前還沒有繫結專案級參考圖，可以先上傳一張目標風格樣片作為統一基線。"}
            </p>

            <div className="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => styleInputRef.current?.click()}
                disabled={uploadingStyleImage}
                className={`inline-flex items-center gap-1.5 rounded-lg border border-gray-700 px-3 py-2 text-sm text-gray-300 transition-colors hover:border-gray-500 hover:text-white disabled:cursor-not-allowed disabled:opacity-50 ${focusRing}`}
              >
                <ImagePlus className="h-4 w-4" />
                {styleImageUrl ? "替換參考圖" : "上傳參考圖"}
              </button>
              {styleImageUrl && (
                <button
                  type="button"
                  onClick={() => void handleDeleteStyleImage()}
                  disabled={deletingStyleImage}
                  className={`inline-flex items-center gap-1.5 rounded-lg border border-red-500/30 px-3 py-2 text-sm text-red-300 transition-colors hover:border-red-400/50 hover:text-red-200 disabled:cursor-not-allowed disabled:opacity-50 ${focusRing}`}
                >
                  <Trash2 className="h-4 w-4" />
                  {deletingStyleImage ? "刪除中..." : "刪除參考圖"}
                </button>
              )}
            </div>
          </div>

          <input
            ref={styleInputRef}
            type="file"
            accept=".png,.jpg,.jpeg,.webp"
            onChange={handleStyleImageChange}
            className="hidden"
            aria-label="上傳風格參考圖"
          />
        </div>

        <div className="rounded-xl border border-gray-800 bg-gray-950/35 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <label htmlFor="style-description-textarea" className="text-xs font-medium text-gray-400">風格描述</label>
            <span className="text-[11px] text-gray-600">
              {styleDescriptionDraft.trim().length} 字
            </span>
          </div>
          <p className="mt-1 text-xs leading-5 text-gray-500">
            上傳參考圖後系統會自動分析並填入風格描述；你也可以繼續手動校準。
          </p>

          <textarea
            id="style-description-textarea"
            value={styleDescriptionDraft}
            onChange={(e) => setStyleDescriptionDraft(e.target.value)}
            rows={8}
            className={`mt-3 min-h-44 w-full rounded-xl border border-gray-700 bg-gray-800/80 px-4 py-3 text-sm leading-relaxed text-gray-200 placeholder-gray-500 focus:border-indigo-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500`}
            placeholder="上傳風格參考圖後，系統會自動分析並填入風格描述；也可以手動編輯。"
          />

          <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
            <p className="text-xs leading-5 text-gray-500">
              {styleImageUrl
                ? "建議把風格描述用於補充光線、色彩、材質與鏡頭語言。"
                : "沒有參考圖時，也可以先用文字明確畫面風格與審美約束。"}
            </p>
            {styleDescriptionDirty && (
              <button
                type="button"
                onClick={() => void handleSaveStyleDescription()}
                disabled={savingStyleDescription}
                className={`rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50 ${focusRing}`}
              >
                {savingStyleDescription ? "儲存中..." : "儲存風格描述"}
              </button>
            )}
          </div>
        </div>
      </div>
    </section>
  );

  return (
    <div className="h-full overflow-y-auto">
      <div className="space-y-6 p-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-100">{projectData.title}</h1>
          <p className="mt-1 text-sm text-gray-400">
            {projectData.content_mode === "narration"
              ? "說書＋畫面模式"
              : "劇本動畫模式"}{" "}
            · {projectData.style || "未設定風格"}
          </p>
        </div>

        {showWelcome ? (
          <WelcomeCanvas
            projectName={projectName}
            projectTitle={projectData.title}
            onUpload={handleUpload}
            onAnalyze={handleAnalyze}
          />
        ) : (
          <>
            <OverviewSection
              projectName={projectName}
              overview={overview}
              onRefresh={refreshProject}
              textModelOptions={modelOptions.text}
              providerNames={modelOptions.providerNames}
            />

            {status && (
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {(["characters", "clues", "scenes"] as const).map(
                  (key) => {
                    const cat = status[key] as
                      | { total: number; completed: number }
                      | undefined;
                    if (!cat) return null;
                    const pct =
                      cat.total > 0
                        ? Math.round((cat.completed / cat.total) * 100)
                        : 0;
                    const labels: Record<string, string> = {
                      characters: "角色",
                      clues: "道具",
                      scenes: "場景",
                    };
                    return (
                      <div
                        key={key}
                        className="rounded-lg border border-gray-800 bg-gray-900 p-3"
                      >
                        <div className="mb-1 flex justify-between text-xs">
                          <span className="text-gray-400">{labels[key]}</span>
                          <span className="text-gray-300">
                            {cat.completed}/{cat.total}
                          </span>
                        </div>
                        <div
                          className="h-1.5 overflow-hidden rounded-full bg-gray-800"
                          role="progressbar"
                          aria-valuenow={pct}
                          aria-valuemin={0}
                          aria-valuemax={100}
                        >
                          <div
                            className="h-full rounded-full bg-indigo-500"
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                      </div>
                    );
                  },
                )}
              </div>
            )}

            {costLoading && (
              <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
                <p className="text-sm text-gray-500 animate-pulse">正在計算費用...</p>
              </div>
            )}
            {costError && (
              <div className="rounded-xl border border-red-900/50 bg-red-950/30 p-4">
                <p className="text-sm text-red-400">費用估算失敗：{costError}</p>
              </div>
            )}

            {projectTotals && (
              <div className="rounded-xl border border-gray-800 bg-gray-900 p-4 tabular-nums">
                <p className="mb-3 text-sm font-semibold text-gray-300">專案總費用</p>
                <dl className="flex flex-wrap items-start justify-between gap-6">
                  <div className="min-w-0">
                    <dt className="mb-1 text-[11px] text-gray-600">預估</dt>
                    <dd className="text-sm text-gray-400">
                      <span className="text-gray-500">分鏡 </span>
                      <span className="text-gray-200">{formatCost(projectTotals.estimate.image)}</span>
                      <span className="ml-3 text-gray-500">影片 </span>
                      <span className="text-gray-200">{formatCost(projectTotals.estimate.video)}</span>
                      <span className="ml-3 text-gray-500">總計 </span>
                      <span className="font-semibold text-amber-400">{formatCost(totalBreakdown(projectTotals.estimate))}</span>
                    </dd>
                  </div>
                  <div role="separator" className="h-8 w-px bg-gray-800" />
                  <div className="min-w-0">
                    <dt className="mb-1 text-[11px] text-gray-600">實際</dt>
                    <dd className="text-sm text-gray-400">
                      <span className="text-gray-500">分鏡 </span>
                      <span className="text-gray-200">{formatCost(projectTotals.actual.image)}</span>
                      <span className="ml-3 text-gray-500">影片 </span>
                      <span className="text-gray-200">{formatCost(projectTotals.actual.video)}</span>
                      {projectTotals.actual.character_and_clue && (
                        <>
                          <span className="ml-3 text-gray-500">角色／道具 </span>
                          <span className="text-gray-200">{formatCost(projectTotals.actual.character_and_clue)}</span>
                        </>
                      )}
                      <span className="ml-3 text-gray-500">總計 </span>
                      <span className="font-semibold text-emerald-400">{formatCost(totalBreakdown(projectTotals.actual))}</span>
                    </dd>
                  </div>
                </dl>
              </div>
            )}

            <div className="space-y-2">
              <h3 className="text-sm font-semibold text-gray-300">劇本</h3>
              {(projectData.episodes?.length ?? 0) === 0 ? (
                <p className="text-sm text-gray-500">
                  暫無劇本。可使用 AI 助理生成劇本。
                </p>
              ) : (
                sortEpisodesForDisplay(projectData.episodes ?? []).map((ep) => {
                  const epCost = getEpisodeCost(ep.episode);
                  return (
                    <div
                      key={ep.episode}
                      className="flex flex-wrap items-center gap-3 rounded-lg border border-gray-800 bg-gray-900 px-4 py-2.5 tabular-nums"
                    >
                      <span className="text-sm text-gray-200">{ep.title || "（未命名劇集）"}</span>
                      <span className="text-xs text-gray-500">
                        {ep.scenes_count ?? "?"} 片段 · {ep.status ?? "draft"}
                      </span>
                      {epCost && (
                        <span className="ml-auto flex min-w-0 flex-shrink flex-wrap gap-4 text-xs text-gray-400">
                          <span>
                            <span className="text-gray-500">預估 </span>
                            <span className="text-gray-500">分鏡 </span><span className="text-gray-300">{formatCost(epCost.totals.estimate.image)}</span>
                            <span className="ml-2 text-gray-500">影片 </span><span className="text-gray-300">{formatCost(epCost.totals.estimate.video)}</span>
                            <span className="ml-2 text-gray-500">總計 </span><span className="font-medium text-amber-400">{formatCost(totalBreakdown(epCost.totals.estimate))}</span>
                          </span>
                          <span className="text-gray-700">|</span>
                          <span>
                            <span className="text-gray-500">實際 </span>
                            <span className="text-gray-500">分鏡 </span><span className="text-gray-300">{formatCost(epCost.totals.actual.image)}</span>
                            <span className="ml-2 text-gray-500">影片 </span><span className="text-gray-300">{formatCost(epCost.totals.actual.video)}</span>
                            <span className="ml-2 text-gray-500">總計 </span><span className="font-medium text-emerald-400">{formatCost(totalBreakdown(epCost.totals.actual))}</span>
                          </span>
                        </span>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          </>
        )}

        {projectStyleCard}

        <div className="h-8" />
      </div>
    </div>
  );
}
