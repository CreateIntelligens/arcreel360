import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ChevronDown, ChevronRight, History } from "lucide-react";
import { API, type VersionInfo } from "@/api";
import { useAppStore } from "@/stores/app-store";
import { useProjectsStore } from "@/stores/projects-store";
import { UI_LAYERS } from "@/utils/ui-layers";
import { PreviewableImageFrame } from "@/components/ui/PreviewableImageFrame";
import { PreviewableVideoFrame } from "@/components/ui/PreviewableVideoFrame";

type ResourceType = "storyboards" | "videos" | "characters" | "clues" | "scenes" | "output";

interface VersionTimeMachineProps {
  projectName: string;
  resourceType: ResourceType;
  resourceId: string;
  onRestore?: (version: number) => void | Promise<void>;
}

function getImagePreviewHeightClass(resourceType: ResourceType): string {
  if (resourceType === "characters") return "h-80";
  if (resourceType === "clues" || resourceType === "scenes") return "h-56";
  return "h-64";
}

function getResourcePath(resourceType: ResourceType, resourceId: string): string {
  switch (resourceType) {
    case "storyboards":
      return `storyboards/scene_${resourceId}.png`;
    case "videos":
      return `videos/scene_${resourceId}.mp4`;
    case "output":
      return `output/episode_${resourceId}_final.mp4`;
    case "characters":
      return `characters/${resourceId}.png`;
    case "scenes":
      return `scenes/${resourceId}.png`;
    case "clues":
      return `clues/${resourceId}.png`;
  }
}

/** v0 是使用者上傳的可替換基底版本；AI 生成版本從 v1 起。 */
function versionLabel(version: number): string {
  return version === 0 ? "使用者上傳" : `v${version}`;
}

/** 從版本資訊組出要顯示的生成參數列（label, value），略過未記錄的欄位。 */
function buildMetaRows(info: VersionInfo): { label: string; value: string }[] {
  const rows: { label: string; value: string }[] = [];
  if (info.aspect_ratio) rows.push({ label: "長寬比", value: info.aspect_ratio });
  if (info.image_size) rows.push({ label: "尺寸", value: info.image_size });
  if (info.resolution) rows.push({ label: "解析度", value: info.resolution });
  if (info.duration_seconds != null)
    rows.push({ label: "時長", value: `${info.duration_seconds}s` });
  if (info.negative_prompt) rows.push({ label: "負向提示", value: info.negative_prompt });
  if (info.reference_images?.length) {
    const names = info.reference_images
      .map((ref) => ref.label || ref.name)
      .filter(Boolean)
      .join("、");
    rows.push({ label: "參考圖", value: names });
  }
  if (info.source_clips?.length) {
    rows.push({ label: "來源影片", value: info.source_clips.join("、") });
  }
  return rows;
}

function versionPillClass(isSelected: boolean, isCurrent: boolean, isBase: boolean): string {
  const baseClass = "rounded-full px-2.5 py-1 text-[10px] font-medium transition-colors ";
  if (isSelected) {
    return baseClass + "bg-indigo-600 text-white ring-1 ring-indigo-400";
  }
  if (isCurrent) {
    return baseClass + "bg-indigo-500/15 text-indigo-300 ring-1 ring-indigo-500/30";
  }
  if (isBase) {
    return baseClass + "bg-emerald-500/10 text-emerald-300 ring-1 ring-emerald-500/30 hover:bg-emerald-500/20";
  }
  return baseClass + "bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-white";
}

function restoreButtonLabel(restoringVersion: number | null, selectedVersion: number): string {
  if (restoringVersion === selectedVersion) return "切換中...";
  if (selectedVersion === 0) return "切換到上傳圖";
  return "切換到此版本";
}

/** Find all scrollable ancestor elements. */
function getScrollParents(el: HTMLElement): HTMLElement[] {
  const parents: HTMLElement[] = [];
  let node: HTMLElement | null = el.parentElement;
  while (node) {
    const s = getComputedStyle(node);
    if (/(auto|scroll)/.test(s.overflow + s.overflowY)) parents.push(node);
    node = node.parentElement;
  }
  return parents;
}

export function VersionTimeMachine({
  projectName,
  resourceType,
  resourceId,
  onRestore,
}: VersionTimeMachineProps) {
  const resourcePath = getResourcePath(resourceType, resourceId);
  const resourceFp = useProjectsStore((s) => s.getAssetFingerprint(resourcePath));
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  const [open, setOpen] = useState(false);
  const [panelPos, setPanelPos] = useState<{ top: number; left: number } | null>(null);
  const [versions, setVersions] = useState<VersionInfo[]>([]);
  const [currentVersion, setCurrentVersion] = useState(0);
  const [loading, setLoading] = useState(false);
  const [loadedOnce, setLoadedOnce] = useState(false);
  const [selectedVersion, setSelectedVersion] = useState<number | null>(null);
  const [restoringVersion, setRestoringVersion] = useState<number | null>(null);

  // Reset version list when the underlying resource changes so it's re-fetched
  // on next open. Do NOT close the panel — if it's open and a new generation
  // completes, the user should stay in context and see the refreshed list.
  useEffect(() => {
    setVersions([]);
    setCurrentVersion(0);
    setLoading(false);
    setLoadedOnce(false);
    setSelectedVersion(null);
    setRestoringVersion(null);
  }, [resourceFp, projectName, resourceId, resourceType]);

  // Fetch versions once when panel first opens
  useEffect(() => {
    if (!open || loadedOnce || !resourceId) return;
    void loadVersions();
  }, [open, loadedOnce, resourceId]);

  async function loadVersions() {
    setLoading(true);
    try {
      const data = await API.getVersions(projectName, resourceType, resourceId);
      setVersions(data.versions);
      setCurrentVersion(data.current_version);
      setLoadedOnce(true);
    } catch {
      setVersions([]);
    } finally {
      setLoading(false);
    }
  }

  async function handleRestore(version: number) {
    setRestoringVersion(version);
    try {
      const result = await API.restoreVersion(projectName, resourceType, resourceId, version);
      if (result.asset_fingerprints) {
        useProjectsStore.getState().updateAssetFingerprints(result.asset_fingerprints);
      }
      await onRestore?.(version);
      await loadVersions();
      setSelectedVersion(version);
      useAppStore
        .getState()
        .pushToast(`已切換到 ${versionLabel(version)}`, "success");
    } catch (err) {
      useAppStore
        .getState()
        .pushToast(`切換版本失敗: ${(err as Error).message}`, "error");
    } finally {
      setRestoringVersion(null);
    }
  }

  // Close the panel
  const close = useCallback(() => setOpen(false), []);

  // Compute ideal top position given the trigger rect and panel height
  const computeTop = useCallback(
    (triggerRect: DOMRect, panelHeight: number) => {
      const GAP = 8;
      return triggerRect.bottom + GAP + panelHeight > window.innerHeight
        ? Math.max(GAP, triggerRect.top - GAP - panelHeight)
        : triggerRect.bottom + GAP;
    },
    [],
  );

  // Re-position panel after it mounts or resizes
  const panelCallbackRef = useCallback(
    (node: HTMLDivElement | null) => {
      panelRef.current = node;
      if (!node || !triggerRef.current) return;
      const rect = triggerRef.current.getBoundingClientRect();
      const top = computeTop(rect, node.offsetHeight);
      setPanelPos((prev) =>
        prev && Math.abs(prev.top - top) > 1 ? { ...prev, top } : prev,
      );
    },
    [computeTop],
  );

  // Position panel & register dismiss listeners
  useEffect(() => {
    if (!open || !triggerRef.current) {
      setPanelPos(null);
      return;
    }
    const rect = triggerRef.current.getBoundingClientRect();
    // Use estimated height for initial placement; panelCallbackRef corrects after mount
    const top = computeTop(rect, 320);
    setPanelPos({ top, left: rect.right });

    // Close on scroll (any scrollable ancestor)
    const scrollParents = getScrollParents(triggerRef.current);
    for (const sp of scrollParents) {
      sp.addEventListener("scroll", close, { passive: true, once: true });
    }

    // Close on click outside
    function onMouseDown(e: MouseEvent) {
      if (
        panelRef.current?.contains(e.target as Node) ||
        triggerRef.current?.contains(e.target as Node)
      )
        return;
      close();
    }
    document.addEventListener("mousedown", onMouseDown);

    return () => {
      for (const sp of scrollParents) sp.removeEventListener("scroll", close);
      document.removeEventListener("mousedown", onMouseDown);
    };
  }, [open, close]);

  if (!resourceId) return null;

  // Derive the selected version's full info from the latest `versions` array
  const selectedInfo =
    selectedVersion != null
      ? versions.find((v) => v.version === selectedVersion) ?? null
      : null;

  return (
    <div>
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium text-gray-400 transition-colors hover:bg-gray-800 hover:text-gray-200"
      >
        <History className="h-3 w-3" />
        <span>版本管理</span>
        {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
      </button>

      {open &&
        panelPos &&
        createPortal(
          <div
            ref={panelCallbackRef}
            style={{
              position: "fixed",
              top: panelPos.top,
              left: panelPos.left,
              transform: "translateX(-100%)",
            }}
            className={`${UI_LAYERS.workspacePopover} w-64 rounded-xl border border-gray-700 bg-gray-900/95 p-3 shadow-2xl shadow-black/40 backdrop-blur`}
          >
            {loading ? (
              <span className="text-xs text-gray-500">載入中...</span>
            ) : versions.length === 0 ? (
              <div className="space-y-1">
                <p className="text-[11px] font-medium text-gray-300">暫無歷史版本</p>
                <p className="text-[11px] leading-5 text-gray-500">
                  生成或還原後，歷史版本會出現在這裡。
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {/* Header */}
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-500">
                    歷史版本
                  </span>
                  {currentVersion > 0 && (
                    <span className="rounded-full border border-indigo-500/30 bg-indigo-500/10 px-2 py-0.5 text-[10px] font-medium text-indigo-200">
                      當前 v{currentVersion}
                    </span>
                  )}
                </div>

                {/* Version pills */}
                <div className="flex flex-wrap gap-1.5">
                  {versions.map((v) => {
                    const isCurrent = v.is_current;
                    const isSelected = selectedVersion === v.version;
                    const isBase = v.version === 0;
                    return (
                      <button
                        key={v.version}
                        type="button"
                        onClick={() =>
                          setSelectedVersion((prev) =>
                            prev === v.version ? null : v.version,
                          )
                        }
                        className={versionPillClass(isSelected, isCurrent, isBase)}
                      >
                        {versionLabel(v.version)}
                      </button>
                    );
                  })}
                </div>

                {!selectedInfo && (
                  <p className="text-[10px] leading-4 text-gray-400">
                    點選版本號預覽，非當前版本可切換。
                  </p>
                )}

                {/* Preview area */}
                {selectedInfo && (
                  <div className="rounded-xl border border-gray-700 bg-gray-950/80 p-2.5">
                    <div className="mb-2 flex items-center justify-between gap-2">
                      <span className="text-[11px] font-medium text-gray-200">
                        {selectedInfo.version === 0 ? (
                          <span className="rounded-full bg-emerald-500/10 px-1.5 py-0.5 text-emerald-300">
                            使用者上傳
                          </span>
                        ) : (
                          `v${selectedInfo.version}`
                        )}
                        <span className="ml-1.5 text-[10px] font-normal text-gray-500">
                          {selectedInfo.created_at}
                        </span>
                      </span>
                      {selectedInfo.is_current ? (
                        <span className="shrink-0 rounded-full bg-indigo-500/10 px-2 py-0.5 text-[10px] font-medium text-indigo-300">
                          當前
                        </span>
                      ) : (
                        <button
                          type="button"
                          disabled={restoringVersion !== null}
                          onClick={() => void handleRestore(selectedInfo.version)}
                          className="shrink-0 rounded-full bg-indigo-600 px-2.5 py-0.5 text-[10px] font-medium text-white transition-colors hover:bg-indigo-500 disabled:opacity-50"
                        >
                          {restoreButtonLabel(restoringVersion, selectedInfo.version)}
                        </button>
                      )}
                    </div>

                    {/* Media preview */}
                    {selectedInfo.file_url &&
                      (resourceType === "videos" || resourceType === "output" ? (
                        <PreviewableVideoFrame src={selectedInfo.file_url} alt={`版本 v${selectedInfo.version} 預覽`}>
                          <video
                            src={selectedInfo.file_url}
                            aria-label={`版本 v${selectedInfo.version} 預覽`}
                            className="mb-2 w-full rounded-lg border border-gray-800 bg-black object-contain"
                            controls
                            playsInline
                            preload="none"
                          />
                        </PreviewableVideoFrame>
                      ) : (
                        <PreviewableImageFrame src={selectedInfo.file_url} alt={`版本 v${selectedInfo.version} 預覽`}>
                          <div
                            className={`mb-2 flex w-full items-center justify-center rounded-lg border border-gray-800 bg-gray-900/70 p-2 ${getImagePreviewHeightClass(resourceType)}`}
                          >
                            <img
                              src={selectedInfo.file_url}
                              alt={`版本 v${selectedInfo.version} 預覽`}
                              className="max-h-full w-full object-contain"
                            />
                          </div>
                        </PreviewableImageFrame>
                      ))}

                    {/* Prompt text */}
                    <p className="line-clamp-4 text-[11px] leading-5 text-gray-400">
                      {selectedInfo.prompt || "該版本沒有記錄額外說明。"}
                    </p>

                    {/* Generation metadata */}
                    {selectedInfo.version !== 0 && (
                      <dl className="mt-2 space-y-0.5 border-t border-gray-800 pt-1.5 text-[10px] leading-5">
                        {selectedInfo.model && (
                          <div className="flex gap-1.5">
                            <dt className="shrink-0 text-gray-500">模型</dt>
                            <dd className="min-w-0 break-words text-gray-300">{selectedInfo.model}</dd>
                          </div>
                        )}
                        {buildMetaRows(selectedInfo).map((row) => (
                          <div key={row.label} className="flex gap-1.5">
                            <dt className="shrink-0 text-gray-500">{row.label}</dt>
                            <dd className="min-w-0 break-words text-gray-400">{row.value}</dd>
                          </div>
                        ))}
                      </dl>
                    )}
                  </div>
                )}

              </div>
            )}
          </div>,
          document.body,
        )}
    </div>
  );
}
