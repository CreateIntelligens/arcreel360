import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, FileText, Image as ImageIcon, RotateCcw, Scissors, Sparkles, Wand2 } from "lucide-react";
import { API } from "@/api";
import { useAppStore } from "@/stores/app-store";
import { useProjectsStore } from "@/stores/projects-store";
import { useConfirm } from "@/hooks/useConfirm";
import { useGlobalModelDefaults } from "@/hooks/useGlobalModelDefaults";
import { ProviderModelSelect } from "@/components/ui/ProviderModelSelect";
import type { ProjectOverview } from "@/types/project";
import { UI_LAYERS } from "@/utils/ui-layers";
import { isPreprocessSourceFileName } from "@/utils/source-files";
import { buildStep1DraftRevisionKey } from "@/utils/project-changes";
import {
  RefsPicker,
  defaultRefsValue,
  hasCustomRefs,
  type RefsCatalog,
  type RefsValue,
} from "./RefsPicker";

interface EpisodeActionsBarProps {
  projectName: string;
  episode: number;
  scriptFile?: string;
  hasScript: boolean;
  activeTab?: "preprocessing" | "storyboard" | "video" | "final";
  textModelOptions?: string[];
  providerNames?: Record<string, string>;
}

type Busy = null | "preprocess" | "script" | "storyboards" | "compose";

type SourceFile = { name: string; size: number; url?: string };

const OVERVIEW_FIELDS = ["synopsis", "genre", "theme", "world_setting"] as const;
const NUM_SEGMENTS_STORAGE_PREFIX = "arcreel:num_segments";
const SCRIPT_INSTRUCTION_STORAGE_PREFIX = "arcreel:script_instruction";
const PREPROCESS_INSTRUCTION_STORAGE_PREFIX = "arcreel:preprocess_instruction";

function isSourceTextFile(file: SourceFile) {
  return isPreprocessSourceFileName(file.name);
}

function hasProjectOverview(overview: ProjectOverview | undefined): boolean {
  return !!overview && OVERVIEW_FIELDS.some((field) => ((overview[field] ?? "").trim().length > 0));
}

function numSegmentsStorageKey(projectName: string, episode: number): string {
  return `${NUM_SEGMENTS_STORAGE_PREFIX}:${projectName}:${episode}`;
}

function readStoredNumSegments(storageKey: string): number | undefined {
  const saved = localStorage.getItem(storageKey);
  return saved ? parseInt(saved, 10) : undefined;
}

function persistNumSegments(storageKey: string, value: number | undefined): void {
  if (value !== undefined && !Number.isNaN(value)) {
    localStorage.setItem(storageKey, value.toString());
    return;
  }
  localStorage.removeItem(storageKey);
}

function scriptInstructionStorageKey(projectName: string, episode: number): string {
  return `${SCRIPT_INSTRUCTION_STORAGE_PREFIX}:${projectName}:${episode}`;
}

function persistScriptInstruction(storageKey: string, value: string): void {
  if (value.trim()) {
    localStorage.setItem(storageKey, value);
    return;
  }
  localStorage.removeItem(storageKey);
}

function preprocessInstructionStorageKey(projectName: string, episode: number): string {
  return `${PREPROCESS_INSTRUCTION_STORAGE_PREFIX}:${projectName}:${episode}`;
}

function persistPreprocessInstruction(storageKey: string, value: string): void {
  if (value.trim()) {
    localStorage.setItem(storageKey, value);
    return;
  }
  localStorage.removeItem(storageKey);
}

/**
 * 將上次保留的 refs 用最新 catalog 修剪一遍：
 * - overview 若 catalog.hasOverview=false → 強制取消勾選
 * - characters/clues/scenes：
 *   - catalog 該群為空 → null（沒有可選項目）
 *   - 上次為 null（全帶）→ 維持 null
 *   - 上次為具體清單 → 過濾已不存在的 key,保留 [] 與部分清單語意（[] = 全不勾,非空陣列 = 部分勾）
 *   - 若 catalog 變化導致 valid.length === all.length → 收斂為 null（與 normalizeGroup 一致）
 */
function pruneRefsAgainstCatalog(refs: RefsValue, catalog: RefsCatalog): RefsValue {
  const pruneGroup = (
    value: string[] | null,
    all: string[],
  ): string[] | null => {
    if (all.length === 0) return null;
    if (value === null) return null;
    const valid = value.filter((name) => all.includes(name));
    if (valid.length === all.length) return null;
    return valid;
  };

  return {
    overview: catalog.hasOverview ? refs.overview : false,
    style: refs.style,
    characters: pruneGroup(refs.characters, catalog.characters),
    clues: pruneGroup(refs.clues, catalog.clues),
    scenes: pruneGroup(refs.scenes, catalog.scenes),
  };
}

function preprocessConfirmMessage(hasScript: boolean, selectedCount: number): string {
  if (selectedCount > 0) {
    return hasScript
      ? `生成草稿會覆蓋目前的片段拆分結果。確定要使用選取的 ${selectedCount} 個原文檔案生成劇本草稿？`
      : `確定要使用選取的 ${selectedCount} 個原文檔案生成劇本草稿？`;
  }
  return hasScript
    ? "生成草稿會覆蓋目前的片段拆分結果。確定要自動均分原文生成劇本草稿？"
    : "生成劇本草稿會把這集原文切成片段。確定要自動均分原文生成劇本草稿？";
}

/**
 * Episode-level batch actions: preprocess / regenerate script /
 * batch regenerate storyboards / compose final video.
 */
export function EpisodeActionsBar({
  projectName,
  episode,
  scriptFile,
  hasScript,
  activeTab = "storyboard",
  textModelOptions = [],
  providerNames = {},
}: EpisodeActionsBarProps) {
  const [busy, setBusy] = useState<Busy>(null);
  const [batchDialogOpen, setBatchDialogOpen] = useState(false);
  const [textModel, setTextModel] = useState("");
  const confirm = useConfirm();
  const globalDefaults = useGlobalModelDefaults();

  const toast = (msg: string, kind: "success" | "error" | "info" = "info") =>
    useAppStore.getState().pushToast(msg, kind);
  const preprocessLabel = hasScript ? "生成草稿" : "生成劇本草稿";
  const scriptLabel = "生成劇本";

  const run = async (
    label: Busy,
    description: string,
    fn: () => Promise<string>,
  ) => {
    if (busy) return;
    setBusy(label);
    try {
      const result = await fn();
      toast(`${description}：${result}`, "success");
    } catch (err) {
      toast(`${description}失敗：${(err as Error).message}`, "error");
    } finally {
      setBusy(null);
    }
  };

  const [sources, setSources] = useState<{ name: string; size: number }[]>([]);
  const [loadingSources, setLoadingSources] = useState(false);
  const [selectedSources, setSelectedSources] = useState<string[]>([]);
  const [numSegments, setNumSegments] = useState<number | undefined>(undefined);
  const numSegmentsKey = numSegmentsStorageKey(projectName, episode);

  useEffect(() => {
    setNumSegments(readStoredNumSegments(numSegmentsKey));
  }, [numSegmentsKey]);

  // 生成劇本的自由提示詞（引導 AI 怎麼改編），按專案+集數持久化。
  const [scriptInstruction, setScriptInstruction] = useState("");
  const [scriptPromptOpen, setScriptPromptOpen] = useState(false);
  const scriptInstructionKey = scriptInstructionStorageKey(projectName, episode);

  useEffect(() => {
    const saved = localStorage.getItem(scriptInstructionKey) ?? "";
    setScriptInstruction(saved);
    setScriptPromptOpen(saved.trim().length > 0);
  }, [scriptInstructionKey]);

  const updateScriptInstruction = (value: string) => {
    setScriptInstruction(value);
    persistScriptInstruction(scriptInstructionKey, value);
  };

  // 重新拆段的自由提示詞，按專案+集數持久化。
  const [preprocessInstruction, setPreprocessInstruction] = useState("");
  const preprocessInstructionKey = preprocessInstructionStorageKey(projectName, episode);
  const [preprocessSettingsOpen, setPreprocessSettingsOpen] = useState(false);

  useEffect(() => {
    const saved = localStorage.getItem(preprocessInstructionKey) ?? "";
    setPreprocessInstruction(saved);
  }, [preprocessInstructionKey]);

  const updatePreprocessInstruction = (value: string) => {
    setPreprocessInstruction(value);
    persistPreprocessInstruction(preprocessInstructionKey, value);
  };

  // 拆段時可勾選的「參考來源」清單,來自當前 project。
  const currentProjectData = useProjectsStore((s) => s.currentProjectData);
  const refsCatalog = useMemo<RefsCatalog>(() => {
    const p = currentProjectData;
    return {
      hasOverview: hasProjectOverview(p?.overview),
      characters: p?.characters ? Object.keys(p.characters) : [],
      clues: p?.clues ? Object.keys(p.clues) : [],
      scenes: p?.scenes ? Object.keys(p.scenes) : [],
    };
  }, [currentProjectData]);
  const [refs, setRefs] = useState<RefsValue>(() => defaultRefsValue(refsCatalog));
  // 首次掛載時 currentProjectData 可能還沒載入,refsCatalog 為空 → defaultRefsValue 算出的預設不準。
  // 用 ref 紀錄是否已用「真實 catalog」初始化過,首次開啟下拉時補一次預設。
  const refsInitialized = useRef(false);

  useEffect(() => {
    if (activeTab === "preprocessing") {
      if (!refsInitialized.current && refsCatalog.characters.length > 0) {
        setRefs(defaultRefsValue(refsCatalog));
        refsInitialized.current = true;
      } else {
        setRefs((prev) => pruneRefsAgainstCatalog(prev, refsCatalog));
      }
      void fetchSources();
    }
  }, [activeTab, projectName, episode, refsCatalog]);
  const refsDirty = hasCustomRefs(refs, refsCatalog);

  const sourcesInitialized = useRef(false);

  useEffect(() => {
    sourcesInitialized.current = false;
  }, [projectName, episode]);

  const fetchSources = async () => {
    setLoadingSources(true);
    try {
      const res = await API.listFiles(projectName);
      const sourceFiles = ((res.files.source || []) as SourceFile[]).filter(isSourceTextFile);
      setSources(sourceFiles);
      // 修剪掉已不存在的舊選項,保留仍存在的勾選
      const validNames = new Set(sourceFiles.map((f) => f.name));
      setSelectedSources((prev) => {
        const filtered = prev.filter((name) => validNames.has(name));
        if (filtered.length === 0 && sourceFiles.length > 0 && !sourcesInitialized.current) {
          sourcesInitialized.current = true;
          return sourceFiles.map((f) => f.name);
        }
        return filtered;
      });
    } catch (err) {
      toast(`取得原文列表失敗：${(err as Error).message}`, "error");
    } finally {
      setLoadingSources(false);
    }
  };

  const toggleSourceSelection = (name: string) => {
    setSelectedSources((prev) =>
      prev.includes(name) ? prev.filter((x) => x !== name) : [...prev, name]
    );
  };

  const updateNumSegments = (value: string) => {
    const parsed = value ? parseInt(value, 10) : undefined;
    setNumSegments(parsed);
    persistNumSegments(numSegmentsKey, parsed);
  };

  const handleMultiSourceConfirm = async () => {
    const hasSelectedSources = selectedSources.length > 0;
    const sourceStr = hasSelectedSources ? selectedSources.map((name) => `source/${name}`).join(",") : undefined;
    if (await confirm({ message: preprocessConfirmMessage(hasScript, selectedSources.length) })) {
      void handlePreprocess(sourceStr);
    }
  };

  const handlePreprocess = (source?: string) =>
    run("preprocess", preprocessLabel, async () => {
      const res = await API.preprocessEpisode(
        projectName,
        episode,
        source,
        refsDirty ? refs : undefined,
        numSegments,
        textModel || undefined,
        preprocessInstruction || undefined,
      );
      useAppStore.getState().invalidateEntities([buildStep1DraftRevisionKey(episode)]);
      return res.step1_path;
    });

  const handleScript = () =>
    run("script", scriptLabel, async () => {
      const res = await API.generateEpisodeScript(
        projectName,
        episode,
        textModel || undefined,
        scriptInstruction || undefined,
      );
      return `${res.script_file}（${res.segments_count} 段）`;
    });

  const confirmAndRunScript = async () => {
    const message = hasScript
      ? "生成劇本會覆寫現有劇本。確定？"
      : "生成劇本會根據劇本草稿產生劇本。確定？";
    if (await confirm({ message })) {
      void handleScript();
    }
  };

  const handleBatchStoryboards = (force: boolean) =>
    run("storyboards", force ? "強制重生分鏡" : "批次生圖", async () => {
      if (!scriptFile) throw new Error("找不到劇本檔");
      const res = await API.batchGenerateStoryboards(projectName, {
        script_file: scriptFile,
        force,
      });
      return `已入隊 ${res.enqueued.length} 項，略過 ${res.skipped.length} 項`;
    });

  const runBatchFromDialog = (force: boolean) => {
    setBatchDialogOpen(false);
    void handleBatchStoryboards(force);
  };

  const handleCompose = () =>
    run("compose", "合成成片", async () => {
      const res = await API.composeEpisode(projectName, episode);
      useAppStore.getState().invalidateEntities([`final:episode_${episode}`]);
      return `${res.output_path}（${res.duration_seconds.toFixed(1)}s）`;
    });

  const confirmAndCompose = async () => {
    if (await confirm({ message: "確定要合成成片嗎？（此操作會覆寫之前的成片）" })) {
      void handleCompose();
    }
  };

  const confirmBtnText = selectedSources.length > 0
    ? `確定${preprocessLabel} (${selectedSources.length})`
    : `確定${preprocessLabel} (自動均分)`;
  const textModelSelect = textModelOptions.length > 0 ? (
    <ProviderModelSelect
      value={textModel}
      options={textModelOptions}
      providerNames={providerNames}
      onChange={setTextModel}
      placeholder="文字模型"
      allowDefault
      defaultLabel="專案預設模型"
      defaultModelValue={globalDefaults.text}
      aria-label={activeTab === "preprocessing" ? "預處理文字模型" : "劇本文字模型"}
      className="w-52"
      size="sm"
    />
  ) : null;

  return (
    <>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {activeTab === "preprocessing" ? (
          <div className="flex w-full flex-col gap-2">
            <div className="flex flex-wrap items-center gap-2">
              {textModelSelect}
              <ActionButton
                icon={<Wand2 className="h-3.5 w-3.5" />}
                label={preprocessLabel}
                loading={busy === "preprocess"}
                disabled={busy !== null}
                onClick={() => void handleMultiSourceConfirm()}
                tone="primary"
              />
              <ActionButton
                icon={<Scissors className="h-3.5 w-3.5" />}
                label="生成設定"
                onClick={() => setPreprocessSettingsOpen((v) => !v)}
                tone={preprocessSettingsOpen ? "primary" : "neutral"}
              />
            </div>

            <PreprocessInstructionPanel
              value={preprocessInstruction}
              onChange={updatePreprocessInstruction}
            />

            {preprocessSettingsOpen && (
              <PreprocessOptionsPanel
                loadingSources={loadingSources}
                sources={sources}
                selectedSources={selectedSources}
                onToggleSource={toggleSourceSelection}
                refsCatalog={refsCatalog}
                refs={refs}
                onRefsChange={setRefs}
                numSegments={numSegments}
                onNumSegmentsChange={updateNumSegments}
              />
            )}
          </div>
        ) : activeTab === "final" ? (
          <div className="flex w-full flex-wrap items-center gap-2">
            <ActionButton
              icon={<FileText className="h-3.5 w-3.5" />}
              label="合成成片"
              loading={busy === "compose"}
              disabled={!hasScript || busy !== null}
              onClick={() => void confirmAndCompose()}
              tone="success"
            />
            <span className="text-xs text-gray-500">
              將 videos/ 目錄下的場景影片依序拼接為最終成片
            </span>
          </div>
        ) : (
          <div className="flex w-full flex-col gap-2">
            <div className="flex flex-wrap items-center gap-2">
              {textModelSelect}

              <ActionButton
                icon={<Wand2 className="h-3.5 w-3.5" />}
                label={scriptLabel}
                loading={busy === "script"}
                disabled={busy !== null}
                onClick={() => void confirmAndRunScript()}
                tone="neutral"
              />

              <button
                type="button"
                onClick={() => setScriptPromptOpen((v) => !v)}
                aria-expanded={scriptPromptOpen}
                title="自訂這集劇本的生成提示詞"
                className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/60 ${scriptInstruction.trim()
                  ? "border-indigo-500/50 text-indigo-300 hover:border-indigo-400"
                  : "border-gray-700 text-gray-400 hover:border-gray-500 hover:text-gray-200"
                  }`}
              >
                <Sparkles className="h-3.5 w-3.5" />
                <span>劇本提示詞{scriptInstruction.trim() ? "（已設定）" : ""}</span>
                <ChevronDown
                  className={`h-3 w-3 transition-transform ${scriptPromptOpen ? "rotate-180" : ""}`}
                />
              </button>

              {activeTab === "storyboard" && (
                <>
                  <Divider />
                  <ActionButton
                    icon={<ImageIcon className="h-3.5 w-3.5" />}
                    label="批次生圖"
                    loading={busy === "storyboards"}
                    disabled={!hasScript || !scriptFile || busy !== null}
                    onClick={() => setBatchDialogOpen(true)}
                    tone="primary"
                  />
                </>
              )}
            </div>

            {scriptPromptOpen && (
              <ScriptInstructionPanel
                value={scriptInstruction}
                onChange={updateScriptInstruction}
              />
            )}
          </div>
        )}
      </div>

      {batchDialogOpen && (
        <BatchGenerationDialog
          onSelect={runBatchFromDialog}
          onCancel={() => setBatchDialogOpen(false)}
        />
      )}
    </>
  );
}

function PreprocessInstructionPanel({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="rounded-lg border border-gray-800 bg-gray-950/60 p-2.5">
      <label
        htmlFor="preprocess-instruction"
        className="mb-1.5 block text-[0.6875rem] font-semibold uppercase tracking-wider text-gray-500"
      >
        重新拆段提示詞（引導 AI 怎麼拆段，可留空）
      </label>
      <textarea
        id="preprocess-instruction"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={3}
        placeholder="例如：請著重保留戰鬥場景、把長對話拆成更多短片段、強化環境描寫的細節、著重凸顯重要人物的登場動作..."
        className="w-full resize-y rounded-md border border-gray-700 bg-gray-900 px-2.5 py-2 text-xs leading-relaxed text-gray-200 placeholder-gray-600 outline-none focus:border-indigo-500 focus:ring-0"
      />
      <p className="mt-1.5 text-[0.625rem] leading-snug text-gray-500">
        此提示詞將引導 AI 在分析小說及提取分鏡時更注重哪些層面，按集數自動保存。
      </p>
    </div>
  );
}

function PreprocessOptionsPanel({
  loadingSources,
  sources,
  selectedSources,
  onToggleSource,
  refsCatalog,
  refs,
  onRefsChange,
  numSegments,
  onNumSegmentsChange,
}: {
  loadingSources: boolean;
  sources: SourceFile[];
  selectedSources: string[];
  onToggleSource: (name: string) => void;
  refsCatalog: RefsCatalog;
  refs: RefsValue;
  onRefsChange: (value: RefsValue) => void;
  numSegments: number | undefined;
  onNumSegmentsChange: (value: string) => void;
}) {
  return (
    <div className="w-full rounded-xl border border-gray-800 bg-gray-950/40 p-4 flex flex-col gap-4">
      {/* 原文與參考資源選擇區 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* 左側：原文來源 */}
        <div className="flex flex-col rounded-lg border border-gray-800 bg-gray-900/20 p-3">
          <div className="text-[0.6875rem] font-semibold uppercase tracking-wider text-gray-500">
            選擇原文檔案
          </div>
          <div className="pb-1 pt-0.5 text-[0.625rem] text-gray-500 normal-case leading-snug">
            如果不勾選任何原文檔案，將自動按集數均分整本原文；預設已為您勾選全部檔案。
          </div>
          <div className="my-2 h-px bg-gray-800" />
          {loadingSources ? (
            <div className="flex items-center justify-center py-6 text-xs text-gray-400">
              <span className="mr-2 inline-block h-3.5 w-3.5 animate-spin rounded-full border border-gray-600 border-t-transparent" />
              載入中...
            </div>
          ) : (
            <SourceFilePicker
              sources={sources}
              selectedSources={selectedSources}
              onToggleSource={onToggleSource}
            />
          )}
        </div>

        {/* 右側：參考資源 */}
        <div className="flex flex-col rounded-lg border border-gray-800 bg-gray-900/20 p-3">
          <div className="text-[0.6875rem] font-semibold uppercase tracking-wider text-gray-500">
            參考資源
          </div>
          <div className="pb-1 pt-0.5 text-[0.625rem] text-gray-500 normal-case leading-snug">
            勾選需要 AI 參考的設定集資源
          </div>
          <div className="my-2 h-px bg-gray-800" />
          <RefsPicker catalog={refsCatalog} value={refs} onChange={onRefsChange} />
        </div>
      </div>

      {/* 底部設定列：生成段數 */}
      <div className="flex flex-wrap items-end gap-4">
        <NumSegmentsInput value={numSegments} onChange={onNumSegmentsChange} />
      </div>
    </div>
  );
}

function SourceFilePicker({
  sources,
  selectedSources,
  onToggleSource,
}: {
  sources: SourceFile[];
  selectedSources: string[];
  onToggleSource: (name: string) => void;
}) {
  if (sources.length === 0) {
    return (
      <div className="py-3 text-center text-xs text-gray-500">
        source/ 目錄下無可用文字檔，將自動按集數均分整本原文
      </div>
    );
  }

  return (
    <div className="grid max-h-48 grid-cols-1 gap-0.5 overflow-y-auto sm:grid-cols-2">
      {sources.map((file) => {
        const isSelected = selectedSources.includes(file.name);
        return (
          <button
            key={file.name}
            type="button"
            onClick={() => onToggleSource(file.name)}
            className="flex w-full items-center justify-between rounded-md px-2.5 py-2 text-left text-xs text-gray-300 transition-colors hover:bg-gray-800 hover:text-white"
          >
            <div className="flex items-center gap-2 truncate">
              <input
                type="checkbox"
                checked={isSelected}
                readOnly
                className="h-3.5 w-3.5 rounded border-gray-700 bg-gray-900 text-indigo-600 focus:ring-0 focus:ring-offset-0"
              />
              <span className="truncate font-mono">{file.name}</span>
            </div>
            <span className="shrink-0 ml-2 text-[0.625rem] text-gray-500">
              {(file.size / 1024).toFixed(1)} KB
            </span>
          </button>
        );
      })}
    </div>
  );
}

function NumSegmentsInput({
  value,
  onChange,
}: {
  value: number | undefined;
  onChange: (value: string) => void;
}) {
  return (
    <div className="py-1">
      <label
        title="留空 = LLM 自動判斷"
        className="block text-[0.6875rem] font-semibold uppercase tracking-wider text-gray-500 mb-1 cursor-help"
      >
        指定生成段數 / 場景數
      </label>
      <input
        type="number"
        min={1}
        max={100}
        placeholder="預設自動控制"
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        className="w-full max-w-[12rem] rounded border border-gray-700 bg-gray-900 px-2 py-1 text-xs text-gray-300 placeholder-gray-600 outline-none focus:border-indigo-500 focus:ring-0"
      />
    </div>
  );
}

function ScriptInstructionPanel({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="rounded-lg border border-gray-800 bg-gray-950/60 p-2.5">
      <label
        htmlFor="script-instruction"
        className="mb-1.5 block text-[0.6875rem] font-semibold uppercase tracking-wider text-gray-500"
      >
        劇本生成提示詞（引導 AI 怎麼改編，可留空）
      </label>
      <textarea
        id="script-instruction"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={3}
        placeholder="例如：語氣輕鬆詼諧、強調主角內心戲、每段保留原文金句、避免暴力血腥描寫…"
        className="w-full resize-y rounded-md border border-gray-700 bg-gray-900 px-2.5 py-2 text-xs leading-relaxed text-gray-200 placeholder-gray-600 outline-none focus:border-indigo-500 focus:ring-0"
      />
      <p className="mt-1.5 text-[0.625rem] leading-snug text-gray-500">
        此提示詞只影響改編語氣與取向，不會凌駕段數、片段對應原文等硬性規則；按集數自動保存。
      </p>
    </div>
  );
}

function BatchGenerationDialog({
  onSelect,
  onCancel,
}: {
  onSelect: (force: boolean) => void;
  onCancel: () => void;
}) {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onCancel();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [onCancel]);

  const headingId = "batch-generation-storyboards-title";

  return (
    <div
      role="presentation"
      onClick={onCancel}
      className={`fixed inset-0 ${UI_LAYERS.modal} flex items-center justify-center bg-black/65 px-4`}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={headingId}
        className="w-full max-w-sm rounded-2xl border border-gray-800 bg-gray-900 p-5 shadow-2xl shadow-black/40"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between gap-3">
          <h2 id={headingId} className="text-base font-semibold text-gray-100">
            批次生圖
          </h2>
          <button
            type="button"
            onClick={onCancel}
            className="rounded-md border border-gray-700 px-2 py-1 text-xs text-gray-400 transition-colors hover:border-gray-500 hover:text-gray-100"
          >
            取消
          </button>
        </div>

        <div className="grid gap-2">
          <button
            type="button"
            onClick={() => onSelect(false)}
            className="flex items-center gap-3 rounded-xl border border-indigo-500/40 bg-indigo-500/10 px-3 py-3 text-left text-sm text-indigo-100 transition-colors hover:border-indigo-400 hover:bg-indigo-500/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/60"
          >
            <ImageIcon className="h-4 w-4 shrink-0 text-indigo-300" />
            <span>只生成缺少的分鏡</span>
          </button>
          <button
            type="button"
            onClick={() => onSelect(true)}
            className="flex items-center gap-3 rounded-xl border border-amber-500/40 bg-amber-500/10 px-3 py-3 text-left text-sm text-amber-100 transition-colors hover:border-amber-400 hover:bg-amber-500/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500/60"
          >
            <RotateCcw className="h-4 w-4 shrink-0 text-amber-300" />
            <span>全部重生分鏡</span>
          </button>
        </div>
      </div>
    </div>
  );
}

function Divider() {
  return <span className="h-4 w-px bg-gray-800" aria-hidden />;
}

function ActionButton({
  icon,
  label,
  title,
  onClick,
  loading,
  disabled,
  tone,
}: {
  icon: React.ReactNode;
  label: string;
  title?: string;
  onClick: () => void;
  loading?: boolean;
  disabled?: boolean;
  tone: "neutral" | "primary" | "warning" | "success";
}) {
  const toneClass = {
    neutral: "border-gray-700 text-gray-300 hover:border-gray-500 hover:text-gray-100",
    primary: "border-indigo-500/40 text-indigo-300 hover:border-indigo-400 hover:bg-indigo-500/10",
    warning: "border-amber-600/40 text-amber-400 hover:border-amber-500 hover:bg-amber-500/10",
    success: "border-emerald-500/40 text-emerald-300 hover:border-emerald-400 hover:bg-emerald-500/10",
  }[tone];
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title ?? label}
      className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs transition-colors disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/60 ${toneClass}`}
    >
      {loading ? (
        <span className="inline-block h-3 w-3 animate-spin rounded-full border border-current border-t-transparent" />
      ) : (
        icon
      )}
      <span>{label}</span>
    </button>
  );
}
