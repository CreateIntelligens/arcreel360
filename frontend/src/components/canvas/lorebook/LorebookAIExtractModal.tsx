import { useState, useMemo, useEffect } from "react";
import { Loader2, Sparkles, AlertCircle, Check, X } from "lucide-react";
import { projectsApi } from "@/api/projects";
import { ProviderModelSelect } from "@/components/ui/ProviderModelSelect";
import { useAppStore } from "@/stores/app-store";

interface LorebookAIExtractModalProps {
  readonly isOpen: boolean;
  readonly onClose: () => void;
  readonly projectName: string;
  readonly entityType: "character" | "clue" | "scene";
  readonly modelOptions: {
    text: string[];
    providerNames: Record<string, string>;
  };
  readonly onImported: () => void;
}

const ENTITY_LABELS = {
  character: "角色",
  clue: "道具",
  scene: "場景",
};

export function LorebookAIExtractModal({
  isOpen,
  onClose,
  projectName,
  entityType,
  modelOptions,
  onImported,
}: LorebookAIExtractModalProps) {
  const [model, setModel] = useState<string>("");
  const [instruction, setInstruction] = useState("");
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 提取出來的結果
  const [extractedItems, setExtractedItems] = useState<any[] | null>(null);
  const [selectedNames, setSelectedNames] = useState<Set<string>>(new Set());

  // 當 modelOptions.text 載入後，預設選取第一個可用模型
  useEffect(() => {
    if (modelOptions.text.length > 0 && !model) {
      setModel(modelOptions.text[0]);
    }
  }, [modelOptions, model]);

  // 重設為初始狀態
  useEffect(() => {
    if (isOpen) {
      setInstruction("");
      setLoading(false);
      setSubmitting(false);
      setError(null);
      setExtractedItems(null);
      setSelectedNames(new Set());
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleExtract = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await projectsApi.extractLorebook(projectName, {
        model: model || null,
        entity_type: entityType,
        instruction: instruction.trim() || undefined,
      });

      let items: any[] = [];
      if (entityType === "character") {
        items = res.data.characters ?? [];
      } else if (entityType === "clue") {
        items = res.data.clues ?? [];
      } else {
        items = res.data.scenes ?? [];
      }

      setExtractedItems(items);
      setSelectedNames(new Set(items.map((item) => item.name)));
    } catch (err) {
      setError((err as Error).message || "AI 提取失敗，請檢查模型配置或重試。");
    } finally {
      setLoading(false);
    }
  };

  const handleToggleSelect = (name: string) => {
    const next = new Set(selectedNames);
    if (next.has(name)) {
      next.delete(name);
    } else {
      next.add(name);
    }
    setSelectedNames(next);
  };

  const handleSelectAll = () => {
    if (!extractedItems) return;
    if (selectedNames.size === extractedItems.length) {
      setSelectedNames(new Set());
    } else {
      setSelectedNames(new Set(extractedItems.map((item) => item.name)));
    }
  };

  const handleUpdateField = (index: number, field: string, value: string) => {
    if (!extractedItems) return;
    const next = [...extractedItems];
    next[index] = { ...next[index], [field]: value };
    setExtractedItems(next);
  };

  const handleImport = async () => {
    if (!extractedItems) return;
    const itemsToImport = extractedItems.filter((item) => selectedNames.has(item.name));
    if (itemsToImport.length === 0) {
      setError("請至少選擇一項進行匯入。");
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      if (entityType === "character") {
        await projectsApi.batchCreateCharacters(projectName, itemsToImport);
      } else if (entityType === "clue") {
        await projectsApi.batchCreateClues(projectName, itemsToImport);
      } else {
        await projectsApi.batchCreateScenes(projectName, itemsToImport);
      }
      useAppStore.getState().pushToast(`成功匯入 ${itemsToImport.length} 個${ENTITY_LABELS[entityType]}`, "success");
      onImported();
      onClose();
    } catch (err) {
      setError((err as Error).message || "批次建立失敗，請重試。");
    } finally {
      setSubmitting(false);
    }
  };

  const placeholderText = {
    character: "例如：撈出故事中登場的 3 位主要女配角，產出她們的性格特徵與說話語氣。",
    clue: "例如：尋找故事中具有神話色彩或重要象徵意義的寶物及道具。",
    scene: "例如：精確撈出故事前段發生的所有重要室內與室外場景。",
  }[entityType];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="relative flex flex-col w-full max-w-3xl max-h-[85dvh] rounded-2xl border border-gray-800 bg-gray-950 p-6 shadow-2xl text-gray-200 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-gray-800 pb-4 mb-4">
          <div className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-indigo-400" />
            <h2 className="text-lg font-semibold tracking-wide">
              AI 批量提取與匯入 — {ENTITY_LABELS[entityType]}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-800 hover:text-gray-100 transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Scrollable Content */}
        <div className="flex-1 overflow-y-auto space-y-4 pr-1">
          {error && (
            <div className="flex items-start gap-2.5 rounded-lg border border-red-950 bg-red-950/20 p-3.5 text-sm text-red-400">
              <AlertCircle className="h-5 w-5 shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          {extractedItems === null ? (
            /* First Step: Input setup */
            <div className="space-y-4 py-2">
              <div className="space-y-1.5">
                <label className="text-xs font-semibold uppercase tracking-wider text-gray-400">
                  AI 文字模型
                </label>
                <ProviderModelSelect
                  value={model}
                  onChange={setModel}
                  options={modelOptions.text}
                  providerNames={modelOptions.providerNames}
                  placeholder="選擇 AI 模型…"
                  className="w-full max-w-sm"
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-semibold uppercase tracking-wider text-gray-400">
                  自訂提取提示詞 (可選)
                </label>
                <textarea
                  value={instruction}
                  onChange={(e) => setInstruction(e.target.value)}
                  placeholder={placeholderText}
                  rows={4}
                  className="w-full rounded-lg border border-gray-800 bg-gray-900/50 px-3.5 py-2.5 text-sm text-gray-200 placeholder-gray-600 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition-all"
                />
                <p className="text-xs text-gray-500">
                  提示：系統會自動提供專案的概述與故事原文。您的提示詞可以用於調整篩選範圍，例如「只要主要人物」或「忽略路人角色」。
                </p>
              </div>
            </div>
          ) : (
            /* Second Step: Confirmation list */
            <div className="space-y-4">
              <div className="flex items-center justify-between border-b border-gray-800/80 pb-2">
                <div className="text-xs text-gray-400">
                  AI 提取出 {extractedItems.length} 個項目。請勾選確認您要匯入的實體，並可在下方直接修改文字。
                </div>
                <button
                  type="button"
                  onClick={handleSelectAll}
                  className="text-xs font-medium text-indigo-400 hover:text-indigo-300 transition-colors"
                >
                  {selectedNames.size === extractedItems.length ? "取消全選" : "全選"}
                </button>
              </div>

              <div className="space-y-3.5">
                {extractedItems.map((item, index) => {
                  const isChecked = selectedNames.has(item.name);
                  return (
                    <div
                      key={index}
                      className={`flex gap-3.5 rounded-xl border p-4 transition-all duration-200 ${
                        isChecked
                          ? "border-indigo-500 bg-indigo-500/5"
                          : "border-gray-800 bg-gray-900/10 hover:border-gray-700"
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={isChecked}
                        onChange={() => handleToggleSelect(item.name)}
                        className="mt-1 h-4 w-4 rounded border-gray-700 text-indigo-600 focus:ring-indigo-500 bg-gray-900"
                      />

                      <div className="flex-1 space-y-3">
                        <div className="grid gap-3 sm:grid-cols-3">
                          <div className="sm:col-span-1">
                            <label className="mb-0.5 block text-[10px] font-semibold tracking-wider text-gray-500 uppercase">
                              名稱
                            </label>
                            <input
                              type="text"
                              value={item.name}
                              onChange={(e) => handleUpdateField(index, "name", e.target.value)}
                              className="w-full rounded border border-gray-800 bg-gray-900/80 px-2.5 py-1 text-sm text-gray-200 focus:border-indigo-500 focus:outline-none"
                            />
                          </div>

                          {entityType === "character" && (
                            <div className="sm:col-span-2">
                              <label className="mb-0.5 block text-[10px] font-semibold tracking-wider text-gray-500 uppercase">
                                說話風格
                              </label>
                              <input
                                type="text"
                                value={item.voice_style ?? ""}
                                onChange={(e) => handleUpdateField(index, "voice_style", e.target.value)}
                                className="w-full rounded border border-gray-800 bg-gray-900/80 px-2.5 py-1 text-sm text-gray-200 focus:border-indigo-500 focus:outline-none"
                              />
                            </div>
                          )}

                          {entityType === "clue" && (
                            <div className="sm:col-span-2">
                              <label className="mb-0.5 block text-[10px] font-semibold tracking-wider text-gray-500 uppercase">
                                重要程度
                              </label>
                              <select
                                value={item.importance ?? "major"}
                                onChange={(e) => handleUpdateField(index, "importance", e.target.value)}
                                className="w-full rounded border border-gray-800 bg-gray-900/80 px-2.5 py-1 text-sm text-gray-200 focus:border-indigo-500 focus:outline-none"
                              >
                                <option value="major">重要 (major)</option>
                                <option value="minor">次要 (minor)</option>
                              </select>
                            </div>
                          )}
                        </div>

                        <div>
                          <label className="mb-0.5 block text-[10px] font-semibold tracking-wider text-gray-500 uppercase">
                            描述提示詞
                          </label>
                          <textarea
                            value={item.description}
                            onChange={(e) => handleUpdateField(index, "description", e.target.value)}
                            rows={2}
                            className="w-full rounded border border-gray-800 bg-gray-900/80 px-2.5 py-1.5 text-xs text-gray-300 focus:border-indigo-500 focus:outline-none"
                          />
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 border-t border-gray-800 pt-4 mt-4">
          {extractedItems === null ? (
            /* First Step Buttons */
            <>
              <button
                type="button"
                onClick={onClose}
                className="rounded-lg px-4 py-2 text-sm font-medium text-gray-400 hover:bg-gray-900 hover:text-gray-200 transition-colors"
              >
                取消
              </button>
              <button
                type="button"
                onClick={handleExtract}
                disabled={loading}
                className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-5 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {loading && <Loader2 className="h-4 w-4 animate-spin" />}
                <span>{loading ? "提取中..." : "開始 AI 提取"}</span>
              </button>
            </>
          ) : (
            /* Second Step Buttons */
            <>
              <button
                type="button"
                onClick={() => setExtractedItems(null)}
                disabled={submitting}
                className="rounded-lg border border-gray-800 px-4 py-2 text-sm font-medium text-gray-400 hover:bg-gray-900 hover:text-gray-200 transition-colors"
              >
                返回重設
              </button>
              <button
                type="button"
                onClick={handleImport}
                disabled={submitting || selectedNames.size === 0}
                className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-5 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {submitting ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    <span>匯入中...</span>
                  </>
                ) : (
                  <>
                    <Check className="h-4 w-4" />
                    <span>確定匯入 ({selectedNames.size} 項)</span>
                  </>
                )}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
