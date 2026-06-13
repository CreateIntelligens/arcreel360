import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { useLocation, useSearch } from "wouter";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { API } from "@/api";
import { useAppStore } from "@/stores/app-store";
import { useProjectsStore } from "@/stores/projects-store";
import { SegmentCard } from "./SegmentCard";
import { PreprocessingView } from "./PreprocessingView";
import { FinalVideoCard } from "./FinalVideoCard";
import { EpisodeActionsBar } from "./EpisodeActionsBar";
import { EpisodeSplitPanel } from "./EpisodeSplitPanel";
import { SourceTextPanel } from "./SourceTextPanel";
import { useScrollTarget } from "@/hooks/useScrollTarget";
import { useConfirm } from "@/hooks/useConfirm";
import { useCostStore } from "@/stores/cost-store";
import { resolveEpisodeContentMode } from "@/utils/content-mode";
import { formatCost, totalBreakdown } from "@/utils/cost-format";
import { buildMediaModelOptions } from "@/utils/provider-models";
import { providersApi } from "@/api/providers";
import type {
  EpisodeScript,
  NarrationEpisodeScript,
  DramaEpisodeScript,
  NarrationSegment,
  DramaScene,
  CostByType,
  ProjectData,
  ProviderInfo,
} from "@/types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

type Segment = NarrationSegment | DramaScene;
type SegmentUpdateExtras = Record<string, unknown>;
type TimelineTab = "preprocessing" | "storyboard" | "video" | "final";
const TIMELINE_TAB_STORAGE_PREFIX = "arcreel:timeline_tab:";

function getSegmentId(segment: Segment, mode: "narration" | "drama"): string {
  return mode === "narration"
    ? (segment as NarrationSegment).segment_id
    : (segment as DramaScene).scene_id;
}

function getEpisodeItems(
  episodeScript: EpisodeScript,
  contentMode: "narration" | "drama",
): Segment[] {
  if (contentMode === "narration") {
    return (episodeScript as NarrationEpisodeScript).segments ?? [];
  }
  return (episodeScript as DramaEpisodeScript).scenes ?? [];
}

function getTabButtonClass(active: boolean, disabled: boolean): string {
  let stateClass = "border-transparent text-gray-500 hover:text-gray-300";
  if (active) {
    stateClass = "border-indigo-500 text-indigo-400 font-medium";
  } else if (disabled) {
    stateClass = "border-transparent text-gray-700 cursor-not-allowed";
  }
  return `border-b-2 px-4 py-2 text-sm transition-colors focus-ring rounded-t ${stateClass}`;
}

function isTimelineTab(value: string | null): value is TimelineTab {
  return (
    value === "preprocessing" ||
    value === "storyboard" ||
    value === "video" ||
    value === "final"
  );
}

function getTimelineTabStorageKey(projectName: string): string {
  return `${TIMELINE_TAB_STORAGE_PREFIX}${projectName}`;
}

function isTimelineTabAvailable(tab: TimelineTab, hasScript: boolean): boolean {
  return tab === "preprocessing" || hasScript;
}

function readStoredTimelineTab(projectName: string): TimelineTab | null {
  try {
    const value = window.localStorage.getItem(getTimelineTabStorageKey(projectName));
    return isTimelineTab(value) ? value : null;
  } catch {
    return null;
  }
}

function writeStoredTimelineTab(projectName: string, tab: TimelineTab): void {
  try {
    window.localStorage.setItem(getTimelineTabStorageKey(projectName), tab);
  } catch {
    // 隱私模式或受限嵌入環境可能停用 localStorage。
  }
}

function resolvePreferredTimelineTab(
  projectName: string,
  queryTab: TimelineTab | null,
  hasScript: boolean,
): TimelineTab {
  if (queryTab && isTimelineTabAvailable(queryTab, hasScript)) {
    return queryTab;
  }
  const storedTab = readStoredTimelineTab(projectName);
  if (storedTab && isTimelineTabAvailable(storedTab, hasScript)) {
    return storedTab;
  }
  return "preprocessing";
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface TimelineCanvasProps {
  projectName: string;
  episode: number;
  episodeTitle?: string;
  hasDraft?: boolean;
  episodeScript: EpisodeScript | null;
  scriptFile?: string;
  projectData: ProjectData | null;
  onUpdatePrompt?: (
    segmentId: string,
    field: string,
    value: unknown,
    scriptFile?: string,
    extraUpdates?: SegmentUpdateExtras,
  ) => void;
  onGenerateStoryboard?: (segmentId: string, scriptFile?: string) => void;
  onGenerateVideo?: (segmentId: string, scriptFile?: string) => void;
  videoBackend?: string | null;
  currentVideoResolution?: string | null;
  durationOptions?: number[];
  onRestoreStoryboard?: () => Promise<void> | void;
  onRestoreVideo?: () => Promise<void> | void;
  generatingStoryboardIds?: Set<string>;
  generatingVideoIds?: Set<string>;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Main canvas container that renders a vertical list of SegmentCards for
 * the currently selected episode.
 *
 * Shows episode header (title, segment count, duration), followed by the
 * full timeline of segment cards with spacing.
 */
export function TimelineCanvas({
  projectName,
  episode,
  episodeTitle,
  hasDraft,
  episodeScript,
  scriptFile,
  projectData,
  durationOptions,
  onUpdatePrompt,
  onGenerateStoryboard,
  onGenerateVideo,
  videoBackend,
  currentVideoResolution,
  onRestoreStoryboard,
  onRestoreVideo,
  generatingStoryboardIds,
  generatingVideoIds,
}: TimelineCanvasProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const confirm = useConfirm();
  const contentMode = resolveEpisodeContentMode(episodeScript, projectData?.content_mode);
  const sourceFilesVersion = useAppStore((s) => s.sourceFilesVersion);
  const [sourceFiles, setSourceFiles] = useState<string[]>([]);

  const [location, navigate] = useLocation();
  const search = useSearch();
  const hasScript = Boolean(episodeScript);
  const showTabs = Boolean(hasDraft);

  const queryTab = useMemo<TimelineTab | null>(() => {
    const params = new URLSearchParams(search);
    const t = params.get("tab");
    if (isTimelineTab(t)) {
      return t;
    }
    return null;
  }, [search]);

  const [activeTab, setActiveTab] = useState<TimelineTab>(() => {
    return resolvePreferredTimelineTab(projectName, queryTab, hasScript);
  });

  const [activeSegmentIndex, setActiveSegmentIndex] = useState<number | null>(null);
  const [providers, setProviders] = useState<ProviderInfo[] | null>(null);

  useEffect(() => {
    providersApi
      .getProviders()
      .then((res) => {
        setProviders(res.providers);
      })
      .catch((err) => {
        console.error("Failed to load providers:", err);
      });
  }, []);

  const modelOptions = useMemo(() => buildMediaModelOptions(providers), [providers]);

  // URL 明確指定優先；沒有 URL tab 時回到本專案最後使用的時間線 tab。
  useEffect(() => {
    const nextTab = resolvePreferredTimelineTab(projectName, queryTab, hasScript);
    setActiveTab(nextTab);
    if (queryTab && nextTab === queryTab) {
      writeStoredTimelineTab(projectName, nextTab);
    }
  }, [hasScript, projectName, queryTab]);

  const handleTabChange = useCallback(
    (tab: TimelineTab) => {
      if (!isTimelineTabAvailable(tab, hasScript)) return;
      setActiveTab(tab);
      writeStoredTimelineTab(projectName, tab);
      const params = new URLSearchParams(search);
      params.set("tab", tab);
      navigate(`${location}?${params.toString()}`, { replace: true });
    },
    [hasScript, location, navigate, projectName, search],
  );

  useEffect(() => {
    if (!projectName || (projectData?.episodes?.length ?? 0) > 0) {
      setSourceFiles([]);
      return;
    }

    let cancelled = false;
    (async () => {
      try {
        const result = await API.listFiles(projectName);
        const files = (result.files?.source ?? [])
          .map((file) => `source/${file.name}`)
          .filter((name) => name.endsWith(".txt"));
        if (!cancelled) setSourceFiles(files);
      } catch {
        if (!cancelled) setSourceFiles([]);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [projectName, projectData?.episodes?.length, sourceFilesVersion]);

  const refreshProject = useCallback(async () => {
    const result = await API.getProject(projectName);
    useProjectsStore.getState().setCurrentProject(
      projectName,
      result.project,
      result.scripts ?? {},
      result.asset_fingerprints,
    );
    useAppStore.getState().invalidateSourceFiles();
  }, [projectName]);

  const handleUpdateSceneBackend = useCallback(
    async (
      segmentId: string,
      patch: { image_backend?: string | null; video_backend?: string | null },
    ) => {
      if (!scriptFile) return;
      try {
        await API.updateSceneBackend(projectName, episode, segmentId, scriptFile, patch);
        await refreshProject();
        useAppStore.getState().pushToast("已更新模型設定", "success");
      } catch (err) {
        useAppStore
          .getState()
          .pushToast(`更新模型設定失敗：${(err as Error).message}`, "error");
      }
    },
    [projectName, episode, scriptFile, refreshProject],
  );

  const handleDeleteSegment = useCallback(
    async (segmentId: string) => {
      if (!scriptFile) return;
      const label = contentMode === "narration" ? "片段" : "場景";
      const ok = await confirm({
        message: `確定要刪除${label}「${segmentId}」？此操作無法復原。`,
        danger: true,
      });
      if (!ok) return;
      try {
        if (contentMode === "narration") {
          await API.deleteSegment(projectName, segmentId, scriptFile);
        } else {
          await API.deleteScene(projectName, segmentId, scriptFile);
        }
        await refreshProject();
        useAppStore.getState().pushToast(`已刪除${label}「${segmentId}」`, "success");
      } catch (err) {
        useAppStore
          .getState()
          .pushToast(`刪除失敗：${(err as Error).message}`, "error");
      }
    },
    [projectName, scriptFile, contentMode, refreshProject, confirm],
  );

  const handleUploadStoryboardReference = useCallback(
    async (segmentId: string, file: File) => {
      try {
        await API.uploadFile(projectName, "storyboard_ref", file, segmentId);
        await refreshProject();
        useAppStore.getState().pushToast("分鏡參考圖上傳成功", "success");
      } catch (err) {
        useAppStore
          .getState()
          .pushToast(`分鏡參考圖上傳失敗：${(err as Error).message}`, "error");
      }
    },
    [projectName, refreshProject],
  );

  const handleRemoveStoryboardReference = useCallback(
    async (segmentId: string) => {
      try {
        await API.deleteReferenceImage(projectName, "storyboards", segmentId);
        await refreshProject();
        useAppStore.getState().pushToast("分鏡參考圖已移除", "success");
      } catch (err) {
        useAppStore
          .getState()
          .pushToast(`移除分鏡參考圖失敗：${(err as Error).message}`, "error");
      }
    },
    [projectName, refreshProject],
  );

  const handleResetScript = useCallback(async () => {
    if (!hasScript) return;
    const confirmed = await confirm({
      message:
        "確定要清空這一集的劇本內容嗎？會清掉所有片段／場景與其分鏡、影片提示詞，回到空骨架（預處理草稿保留）。此操作無法復原。",
      danger: true,
    });
    if (!confirmed) return;

    try {
      await API.resetEpisodeScript(projectName, episode);
      await refreshProject();
      useAppStore.getState().pushToast("已清空這一集的劇本", "success");
      setActiveTab("preprocessing");
    } catch (err) {
      useAppStore
        .getState()
        .pushToast(`清空失敗：${(err as Error).message}`, "error");
    }
  }, [projectName, episode, hasScript, refreshProject, confirm]);

  const episodeCost = useCostStore((s) =>
    episodeScript ? s.getEpisodeCost(episode) : undefined,
  );
  const debouncedFetch = useCostStore((s) => s.debouncedFetch);

  useEffect(() => {
    if (!projectName) return;
    debouncedFetch(projectName);
  }, [projectName, episode, debouncedFetch]);

  // Determine aspect ratio — use project config if available, otherwise defaults
  const aspectRatio =
    typeof projectData?.aspect_ratio === "string"
      ? projectData.aspect_ratio
      : projectData?.aspect_ratio?.storyboard ??
        (contentMode === "narration" ? "9:16" : "16:9");
  const styleContext = useMemo(
    () => ({
      style: projectData?.style ?? null,
      styleDescription: projectData?.style_description ?? null,
      styleImage: projectData?.style_image ?? null,
    }),
    [projectData?.style, projectData?.style_description, projectData?.style_image],
  );

  // Pick the correct array (segments for narration, scenes for drama)
  const segments = useMemo<Segment[]>(
    () => (!episodeScript || !projectData ? [] : getEpisodeItems(episodeScript, contentMode)),
    [contentMode, episodeScript, projectData],
  );
  const segmentIndexMap = useMemo(
    () =>
      new Map(
        segments.map((segment, index) => [getSegmentId(segment, contentMode), index]),
      ),
    [contentMode, segments],
  );
  const virtualizer = useVirtualizer({
    count: segments.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => 200,
    overscan: 5,
    measureElement: (element) => element?.getBoundingClientRect().height ?? 200,
  });
  const prepareScrollTarget = useCallback(
    (target: { id: string }) => {
      const index = segmentIndexMap.get(target.id);
      if (index == null) {
        return false;
      }
      virtualizer.scrollToIndex(index, { align: "start" });
      return true;
    },
    [segmentIndexMap, virtualizer],
  );

  // Respond to agent-triggered scroll targets for segments
  useScrollTarget("segment", { prepareTarget: prepareScrollTarget });

  const updatePromptForScript = useMemo(
    () =>
      onUpdatePrompt
        ? (
            id: string,
            field: string,
            value: unknown,
            extraUpdates?: SegmentUpdateExtras,
          ) => onUpdatePrompt(id, field, value, scriptFile, extraUpdates)
        : undefined,
    [onUpdatePrompt, scriptFile],
  );
  const generateStoryboardForScript = useMemo(
    () =>
      onGenerateStoryboard
        ? (id: string) => onGenerateStoryboard(id, scriptFile)
        : undefined,
    [onGenerateStoryboard, scriptFile],
  );
  const generateVideoForScript = useMemo(
    () =>
      onGenerateVideo
        ? (id: string) => onGenerateVideo(id, scriptFile)
        : undefined,
    [onGenerateVideo, scriptFile],
  );

  // Empty state — no episode selected or no content at all
  if (!projectData || (!episodeScript && !hasDraft)) {
    if (projectData && (projectData.episodes?.length ?? 0) === 0) {
      return (
        <div className="h-full overflow-y-auto p-4">
          <EpisodeSplitPanel
            projectName={projectName}
            sourceFiles={sourceFiles.length > 0 ? sourceFiles : ["source/novel.txt"]}
            onSplitDone={refreshProject}
          />
        </div>
      );
    }

    return (
      <div className="flex h-full items-center justify-center text-gray-500">
        請在左側選擇劇集
      </div>
    );
  }

  // Compute total duration from actual segments if available
  const totalDuration =
    episodeScript?.duration_seconds ??
    segments.reduce((sum, s) => sum + s.duration_seconds, 0);
  const showEpisodeImageCost = activeTab !== "video";
  const showEpisodeVideoCost = activeTab !== "storyboard";
  const visibleEpisodeEstimate = useMemo<CostByType>(() => {
    if (!episodeCost) return {};
    return {
      ...(showEpisodeImageCost ? { image: episodeCost.totals.estimate.image } : {}),
      ...(showEpisodeVideoCost ? { video: episodeCost.totals.estimate.video } : {}),
    };
  }, [episodeCost, showEpisodeImageCost, showEpisodeVideoCost]);
  const visibleEpisodeActual = useMemo<CostByType>(() => {
    if (!episodeCost) return {};
    return {
      ...(showEpisodeImageCost ? { image: episodeCost.totals.actual.image } : {}),
      ...(showEpisodeVideoCost ? { video: episodeCost.totals.actual.video } : {}),
    };
  }, [episodeCost, showEpisodeImageCost, showEpisodeVideoCost]);

  // Label depends on content mode
  const segmentLabel = contentMode === "narration" ? "個片段" : "個場景";
  const virtualItems = virtualizer.getVirtualItems();

  // 滾動聯動：當滾動使可見的第一個項目改變時，更新 activeSegmentIndex
  const firstVisibleIndex = virtualItems[0]?.index;
  useEffect(() => {
    if (firstVisibleIndex != null) {
      setActiveSegmentIndex(firstVisibleIndex);
    }
  }, [firstVisibleIndex]);

  const handleSelectSegmentIndex = useCallback(
    (index: number) => {
      setActiveSegmentIndex(index);
      const segment = segments[index];
      if (segment) {
        const segId = getSegmentId(segment, contentMode);
        const targetIndex = segmentIndexMap.get(segId);
        if (targetIndex != null) {
          virtualizer.scrollToIndex(targetIndex, { align: "start" });
        }
      }
    },
    [segments, segmentIndexMap, virtualizer, contentMode],
  );

  return (
    <div className="flex h-full w-full overflow-hidden">
      {/* 左側滾動時間線區域 */}
      <div ref={scrollRef} className="flex-1 h-full overflow-y-auto">
        <div className="p-4">
          {/* ---- Episode header ---- */}
          <div className="mb-4">
            <div className="flex items-center gap-3">
              <EpisodeTitleEditor
                projectName={projectName}
                episode={episode}
                title={episodeScript?.title ?? episodeTitle ?? ""}
              />
            </div>
            {/* ---- Tab bar (only when draft exists) ---- */}
            {showTabs && (
              <div className="mt-3 flex gap-0 border-b border-gray-800">
                <TimelineTabButton tab="preprocessing" activeTab={activeTab} onSelect={handleTabChange}>
                  預處理
                </TimelineTabButton>
                <TimelineTabButton
                  tab="storyboard"
                  activeTab={activeTab}
                  disabled={!hasScript}
                  onSelect={handleTabChange}
                >
                  分鏡時間線
                </TimelineTabButton>
                <TimelineTabButton
                  tab="video"
                  activeTab={activeTab}
                  disabled={!hasScript}
                  onSelect={handleTabChange}
                >
                  影片時間線
                </TimelineTabButton>
                <TimelineTabButton
                  tab="final"
                  activeTab={activeTab}
                  disabled={!hasScript}
                  onSelect={handleTabChange}
                >
                  成品
                </TimelineTabButton>
              </div>
            )}
            {episodeScript && (
              <p className="mt-3 text-xs text-gray-500">
                {segments.length} {segmentLabel} · 約 {totalDuration}s
              </p>
            )}
            {episodeCost && (
              <div className="mt-2 flex items-center gap-4 rounded-lg bg-gray-900 border border-gray-800 px-3 py-2 text-xs tabular-nums">
                <span className="text-gray-600">預估</span>
                {showEpisodeImageCost && (
                  <span className="text-gray-500">分鏡 <span className="text-gray-300">{formatCost(episodeCost.totals.estimate.image)}</span></span>
                )}
                {showEpisodeVideoCost && (
                  <span className="text-gray-500">影片 <span className="text-gray-300">{formatCost(episodeCost.totals.estimate.video)}</span></span>
                )}
                <span className="text-gray-500">總計 <span className="font-medium text-amber-400">{formatCost(totalBreakdown(visibleEpisodeEstimate))}</span></span>
                <span className="text-gray-700">|</span>
                <span className="text-gray-600">實際</span>
                {showEpisodeImageCost && (
                  <span className="text-gray-500">分鏡 <span className="text-gray-300">{formatCost(episodeCost.totals.actual.image)}</span></span>
                )}
                {showEpisodeVideoCost && (
                  <span className="text-gray-500">影片 <span className="text-gray-300">{formatCost(episodeCost.totals.actual.video)}</span></span>
                )}
                <span className="text-gray-500">總計 <span className="font-medium text-emerald-400">{formatCost(totalBreakdown(visibleEpisodeActual))}</span></span>
              </div>
            )}
            <EpisodeActionsBar
              key={`${projectName}:${episode}`}
              projectName={projectName}
              episode={episode}
              scriptFile={scriptFile}
              hasScript={hasScript}
              activeTab={activeTab}
              textModelOptions={modelOptions.text}
              providerNames={modelOptions.providerNames}
            />
          </div>

          {/* ---- Tab content ---- */}
          {activeTab === "preprocessing" && hasDraft ? (
            <PreprocessingView
              projectName={projectName}
              episode={episode}
              contentMode={contentMode}
            />
          ) : activeTab !== "final" && episodeScript ? (
            <>
              <div className="mb-4 flex items-center gap-2">
                <AddSegmentButton
                  projectName={projectName}
                  episode={episode}
                  contentMode={contentMode}
                  onAdded={refreshProject}
                />
                <button
                  type="button"
                  onClick={() => void handleResetScript()}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-red-500/30 px-3 py-1.5 text-sm text-red-300/80 transition-colors hover:border-red-400/60 hover:bg-red-500/10 hover:text-red-300"
                >
                  <Trash2 className="h-4 w-4" />
                  清空劇本
                </button>
              </div>
              {segments.length === 0 && (
                <p className="mb-4 text-sm text-gray-600">
                  這一集還沒有{contentMode === "narration" ? "片段" : "場景"}，點上方按鈕新增。
                </p>
              )}
              <div
                className="relative"
                style={{ height: `${virtualizer.getTotalSize()}px` }}
              >
                {virtualItems.map((virtualItem) => {
                  const segment = segments[virtualItem.index];
                  const segId = getSegmentId(segment, contentMode);
                  return (
                    <div
                      id={`segment-${segId}`}
                      key={segId}
                      data-index={virtualItem.index}
                      ref={virtualizer.measureElement}
                      className="absolute left-0 top-0 w-full"
                      style={{
                        transform: `translateY(${virtualItem.start}px)`,
                        paddingBottom: virtualItem.index === segments.length - 1 ? 0 : 16,
                      }}
                      onMouseEnter={() => {
                        setActiveSegmentIndex(virtualItem.index);
                      }}
                      onFocusCapture={() => {
                        setActiveSegmentIndex(virtualItem.index);
                      }}
                    >
                      <SegmentCard
                        segment={segment}
                        contentMode={contentMode}
                        aspectRatio={aspectRatio}
                        characters={projectData.characters}
                        clues={projectData.clues}
                        scenes={projectData.scenes ?? {}}
                        projectName={projectName}
                        episode={episode}
                        scriptFile={scriptFile}
                        videoBackend={videoBackend}
                        currentResolution={currentVideoResolution}
                        durationOptions={durationOptions}
                        onUpdatePrompt={updatePromptForScript}
                        onGenerateStoryboard={generateStoryboardForScript}
                        onGenerateVideo={generateVideoForScript}
                        onRestoreStoryboard={onRestoreStoryboard}
                        onRestoreVideo={onRestoreVideo}
                        onDelete={() => void handleDeleteSegment(segId)}
                        generatingStoryboard={generatingStoryboardIds?.has(segId) ?? false}
                        generatingVideo={generatingVideoIds?.has(segId) ?? false}
                        onUploadReference={handleUploadStoryboardReference}
                        onRemoveReference={handleRemoveStoryboardReference}
                        stage={activeTab === "storyboard" || activeTab === "video" ? activeTab : undefined}
                        imageModelOptions={modelOptions.image}
                        videoModelOptions={modelOptions.video}
                        textModelOptions={modelOptions.text}
                        providerNames={modelOptions.providerNames}
                        styleContext={styleContext}
                        onUpdateSceneBackend={handleUpdateSceneBackend}
                      />
                    </div>
                  );
                })}
              </div>
              {segments.length > 0 && (
                <div className="mt-4 flex justify-center">
                  <AddSegmentButton
                    projectName={projectName}
                    episode={episode}
                    contentMode={contentMode}
                    onAdded={refreshProject}
                  />
                </div>
              )}
            </>
          ) : null}

          {/* Final composed video */}
          {activeTab === "final" && (
            <FinalVideoCard projectName={projectName} episode={episode} />
          )}

          {/* Bottom spacer for scroll comfort */}
          <div className="h-16" />
        </div>
      </div>

      {/* 右側原文對照側欄 */}
      {activeTab !== "preprocessing" && episodeScript && (
        <SourceTextPanel
          projectName={projectName}
          episode={episode}
          contentMode={contentMode}
          activeSegmentIndex={activeSegmentIndex}
          onSelectSegmentIndex={handleSelectSegmentIndex}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// TimelineTabButton
// ---------------------------------------------------------------------------

function TimelineTabButton({
  tab,
  activeTab,
  disabled = false,
  onSelect,
  children,
}: {
  tab: TimelineTab;
  activeTab: TimelineTab;
  disabled?: boolean;
  onSelect: (tab: TimelineTab) => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={() => {
        if (!disabled) onSelect(tab);
      }}
      disabled={disabled}
      className={getTabButtonClass(activeTab === tab, disabled)}
    >
      {children}
    </button>
  );
}

// ---------------------------------------------------------------------------
// AddSegmentButton — 在劇本末尾新增一個空片段/場景
// ---------------------------------------------------------------------------

function AddSegmentButton({
  projectName,
  episode,
  contentMode,
  onAdded,
}: {
  projectName: string;
  episode: number;
  contentMode: "narration" | "drama";
  onAdded: () => void | Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const label = contentMode === "narration" ? "新增片段" : "新增場景";

  const handleAdd = async () => {
    if (busy) return;
    setBusy(true);
    try {
      if (contentMode === "narration") {
        await API.addEpisodeSegment(projectName, episode);
      } else {
        await API.addEpisodeScene(projectName, episode);
      }
      await onAdded();
      useAppStore.getState().pushToast(`已${label}`, "success");
    } catch (err) {
      useAppStore.getState().pushToast(`${label}失敗：${(err as Error).message}`, "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <button
      type="button"
      onClick={() => void handleAdd()}
      disabled={busy}
      className="inline-flex items-center gap-1.5 rounded-lg border border-indigo-500/40 px-3 py-1.5 text-sm text-indigo-300 transition-colors hover:border-indigo-400 hover:bg-indigo-500/10 disabled:cursor-not-allowed disabled:opacity-50"
    >
      <Plus className="h-4 w-4" />
      {label}
    </button>
  );
}

// ---------------------------------------------------------------------------
// EpisodeTitleEditor — inline-editable episode title with hover pencil icon
// ---------------------------------------------------------------------------

function EpisodeTitleEditor({
  projectName,
  episode,
  title,
}: {
  projectName: string;
  episode: number;
  title: string;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(title);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setDraft(title);
  }, [title]);

  const commit = async () => {
    const trimmed = draft.trim();
    if (!trimmed) {
      setDraft(title);
      setEditing(false);
      return;
    }
    if (trimmed === title) {
      setEditing(false);
      return;
    }
    setSaving(true);
    try {
      await API.updateEpisode(projectName, episode, { title: trimmed });
      const res = await API.getProject(projectName);
      useProjectsStore.getState().setCurrentProject(
        projectName,
        res.project,
        res.scripts ?? {},
        res.asset_fingerprints,
      );
      useAppStore.getState().pushToast(`E${episode} 標題已更新`, "success");
    } catch (err) {
      useAppStore.getState().pushToast(`更新失敗：${(err as Error).message}`, "error");
      setDraft(title);
    } finally {
      setSaving(false);
      setEditing(false);
    }
  };

  if (editing) {
    return (
      <input
        type="text"
        autoFocus
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={() => void commit()}
        onKeyDown={(e) => {
          if (e.nativeEvent.isComposing) return;
          if (e.key === "Enter") {
            e.preventDefault();
            void commit();
          } else if (e.key === "Escape") {
            setDraft(title);
            setEditing(false);
          }
        }}
        disabled={saving}
        className="w-full max-w-md rounded border border-indigo-500 bg-gray-800 px-2 py-0.5 text-lg font-semibold text-gray-100 focus:outline-none disabled:opacity-50"
        aria-label="劇集標題"
      />
    );
  }

  return (
    <button
      type="button"
      onClick={() => setEditing(true)}
      className="group flex items-center gap-2 text-left"
      title="點擊編輯標題"
    >
      <h2 className="text-lg font-semibold text-gray-100">
        {title || "（未命名劇集）"}
      </h2>
      <Pencil className="h-3.5 w-3.5 text-gray-600 opacity-0 transition-opacity group-hover:opacity-100" />
    </button>
  );
}
