import { useEffect, useMemo, useRef, useState } from "react";
import { Loader2, Scissors } from "lucide-react";
import { API } from "@/api";
import { useAppStore } from "@/stores/app-store";
import type { EpisodeSplitPeekResponse } from "@/api";

interface EpisodeSplitPanelProps {
  projectName: string;
  sourceFiles: string[];
  onSplitDone: () => void | Promise<void>;
}

type BusyState = "peek" | "split" | null;

const DEFAULT_SOURCE_FILE = "source/novel.txt";
const ANCHOR_LENGTH = 16;

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "操作失敗";
}

function getSourceOptions(sourceFiles: string[]): string[] {
  return Array.from(new Set(sourceFiles.length > 0 ? sourceFiles : [DEFAULT_SOURCE_FILE]));
}

function pickAnchorBeforeOffset(peek: EpisodeSplitPeekResponse, offset: number): string {
  const contextStart = peek.target_offset - peek.context_before.length;
  const localCut = offset - contextStart;
  const combinedContext = `${peek.context_before}${peek.context_after}`;
  if (localCut <= 0 || localCut > combinedContext.length) {
    return peek.context_before.slice(-ANCHOR_LENGTH);
  }
  return combinedContext.slice(Math.max(0, localCut - ANCHOR_LENGTH), localCut);
}

export function EpisodeSplitPanel({
  projectName,
  sourceFiles,
  onSplitDone,
}: EpisodeSplitPanelProps) {
  const [source, setSource] = useState(sourceFiles[0] ?? DEFAULT_SOURCE_FILE);
  const [targetChars, setTargetChars] = useState(3000);
  const [episode, setEpisode] = useState(1);
  const [peek, setPeek] = useState<EpisodeSplitPeekResponse | null>(null);
  const [anchor, setAnchor] = useState("");
  const [busy, setBusy] = useState<BusyState>(null);
  const [error, setError] = useState<string | null>(null);

  const sourceOptions = useMemo(() => getSourceOptions(sourceFiles), [sourceFiles]);
  const sourceTouched = useRef(false);

  // sourceFiles 由父層非同步抓取，到貨後（使用者尚未手動改過時）對齊第一個選項。
  useEffect(() => {
    const firstOption = sourceOptions[0];
    if (!sourceTouched.current && firstOption && firstOption !== source) {
      setSource(firstOption);
    }
  }, [source, sourceOptions]);

  const handleSourceChange = (value: string) => {
    sourceTouched.current = true;
    setSource(value);
  };

  const handlePeek = async () => {
    if (busy) return;
    setBusy("peek");
    setError(null);
    setPeek(null);
    setAnchor("");
    try {
      const result = await API.peekEpisodeSplit(projectName, {
        source: source.trim(),
        target_chars: targetChars,
      });
      setPeek(result);
      setAnchor(result.context_before.slice(-ANCHOR_LENGTH));
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusy(null);
    }
  };

  const handlePickBreakpoint = (offset: number) => {
    if (!peek) return;
    setAnchor(pickAnchorBeforeOffset(peek, offset));
  };

  const handleSplit = async () => {
    if (busy || !anchor.trim()) return;
    setBusy("split");
    setError(null);
    try {
      await API.splitEpisode(projectName, {
        source: source.trim(),
        episode,
        target_chars: targetChars,
        anchor: anchor.trim(),
      });
      useAppStore.getState().pushToast(`已切出第 ${episode} 集`, "success");
      await onSplitDone();
      setPeek(null);
      setAnchor("");
    } catch (err) {
      const message = getErrorMessage(err);
      setError(message);
      useAppStore.getState().pushToast(`分集切分失敗：${message}`, "error");
    } finally {
      setBusy(null);
    }
  };

  const canPeek = source.trim().length > 0 && targetChars > 0 && !busy;
  const canSplit = Boolean(peek && anchor.trim() && episode > 0 && targetChars > 0 && !busy);

  return (
    <section className="rounded-lg border border-gray-800 bg-gray-950/60 p-4">
      <div className="mb-3 flex items-center gap-2 text-sm font-medium text-gray-200">
        <Scissors className="h-4 w-4 text-indigo-400" />
        分集切分
      </div>

      <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_7rem_5rem_auto] sm:items-end">
        <label className="block text-xs text-gray-400">
          source 檔案
          <input
            list="episode-split-source-files"
            value={source}
            onChange={(event) => handleSourceChange(event.target.value)}
            className="mt-1 w-full rounded border border-gray-700 bg-gray-900 px-2 py-1.5 text-sm text-gray-100 outline-none focus:border-indigo-500"
          />
          <datalist id="episode-split-source-files">
            {sourceOptions.map((file) => (
              <option key={file} value={file} />
            ))}
          </datalist>
        </label>

        <label className="block text-xs text-gray-400">
          目標字數
          <input
            type="number"
            min={1}
            value={targetChars}
            onChange={(event) => setTargetChars(Number(event.target.value))}
            className="mt-1 w-full rounded border border-gray-700 bg-gray-900 px-2 py-1.5 text-sm text-gray-100 outline-none focus:border-indigo-500"
          />
        </label>

        <label className="block text-xs text-gray-400">
          集數
          <input
            type="number"
            min={1}
            value={episode}
            onChange={(event) => setEpisode(Number(event.target.value))}
            className="mt-1 w-full rounded border border-gray-700 bg-gray-900 px-2 py-1.5 text-sm text-gray-100 outline-none focus:border-indigo-500"
          />
        </label>

        <button
          type="button"
          onClick={() => void handlePeek()}
          disabled={!canPeek}
          className="inline-flex items-center justify-center gap-1.5 rounded border border-gray-700 px-3 py-1.5 text-sm text-gray-200 transition-colors hover:border-gray-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busy === "peek" && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          預覽切點
        </button>
      </div>

      {error && (
        <p className="mt-3 rounded border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
          {error}
        </p>
      )}

      {peek && (
        <div className="mt-4 space-y-3 text-xs text-gray-300">
          <div className="flex flex-wrap gap-3 text-gray-500">
            <span>總字數 {peek.total_chars}</span>
            <span>目標字數 {peek.target_chars}</span>
            <span>目標 offset {peek.target_offset}</span>
          </div>

          <div className="whitespace-pre-wrap rounded border border-gray-800 bg-gray-900 p-3 leading-6 text-gray-300">
            {peek.context_before}
            <span className="mx-1 text-amber-400">▮</span>
            {peek.context_after}
          </div>

          <div>
            <div className="mb-1 text-gray-500">附近斷點</div>
            <div className="space-y-1">
              {peek.nearby_breakpoints.map((breakpoint, index) => (
                <div
                  key={`${breakpoint.offset}-${index}`}
                  className="flex flex-wrap items-center gap-2 rounded border border-gray-800 px-2 py-1.5"
                >
                  <span className="text-gray-300">
                    {breakpoint.type} @ {breakpoint.offset}
                  </span>
                  <span className="text-gray-600">
                    字元 {breakpoint.char}，距離 {breakpoint.distance}
                  </span>
                  <button
                    type="button"
                    onClick={() => handlePickBreakpoint(breakpoint.offset)}
                    className="ml-auto rounded border border-gray-700 px-2 py-0.5 text-gray-300 transition-colors hover:border-gray-500"
                  >
                    選此處
                  </button>
                </div>
              ))}
            </div>
          </div>

          <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
            <label className="block text-xs text-gray-400">
              切點前文字（anchor）
              <input
                value={anchor}
                onChange={(event) => setAnchor(event.target.value)}
                placeholder="切點前 10-20 字的原文片段"
                className="mt-1 w-full rounded border border-gray-700 bg-gray-900 px-2 py-1.5 text-sm text-gray-100 outline-none focus:border-indigo-500"
              />
            </label>
            <button
              type="button"
              onClick={() => void handleSplit()}
              disabled={!canSplit}
              className="inline-flex items-center justify-center gap-1.5 rounded border border-emerald-500/50 px-3 py-1.5 text-sm text-emerald-300 transition-colors hover:border-emerald-400 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {busy === "split" && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              執行切分
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
